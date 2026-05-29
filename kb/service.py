"""Rebuild, search, and inspect the knowledge base."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from graph.state import RetrievedDoc
from kb.baoyan_basics_md import load_baoyan_basics_md
from kb.experience_excel import load_experience_excel
from kb.manual_stats_txt import load_manual_stats_txt
from tools.credibility import build_credibility_fields
from kb.internal import InternalChunk
from kb.manifest import KBManifest, load_manifest, repo_root
from kb.official_brochures import load_official_brochures, summarize_brochures, write_filenames_txt
from kb.registry import REGISTRY, RebuildMeta, compute_rebuild_digest
from kb.scoring import score_chunks


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def get_hybrid_engine():
    from kb.hybrid_search import get_hybrid_engine as _get_hybrid_engine

    return _get_hybrid_engine()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def rebuild_all(root: Path | None = None) -> Dict[str, Any]:
    base = root or repo_root()
    manifest = load_manifest(base)
    manifest_text = (base / "data/kb/manifest.yaml").read_text(encoding="utf-8")

    # Write a deterministic brochure file catalog for LLM selection.
    write_filenames_txt(base, Path(manifest.official_documents_brochures.directory))

    official = load_official_brochures(
        base,
        Path(manifest.official_documents_brochures.directory),
    )
    official_report = summarize_brochures(official)

    experience_xhs, xlsx_warnings, excel_parse = load_experience_excel(manifest.public_info_xhs, base)
    experience_manual, manual_warnings, manual_parse = load_manual_stats_txt(
        manifest.public_info_manual_stats.txt_path, base
    )
    experience_basics, basics_warnings, basics_parse = load_baoyan_basics_md(
        manifest.public_info_baoyan_basics.md_path, base
    )
    experience = list(experience_xhs) + list(experience_manual) + list(experience_basics)
    warnings = list(xlsx_warnings) + list(manual_warnings) + list(basics_warnings)

    digest = compute_rebuild_digest(official, experience, manifest_text)
    hybrid_enabled = _env_bool("ENABLE_HYBRID_SEARCH", True)
    hybrid_status: Dict[str, Any] = {
        "enabled": hybrid_enabled,
        "built": False,
        "fallback": "lexical",
        "error": "",
    }
    if hybrid_enabled:
        try:
            engine = get_hybrid_engine()
            engine.rebuild(list(official) + list(experience), digest)
            hybrid_status["built"] = True
        except Exception as exc:
            hybrid_status["error"] = f"{type(exc).__name__}: {exc}"
            warnings.append(f"混合检索索引构建失败，已回退关键词检索：{hybrid_status['error']}")

    parse_report: Dict[str, Any] = {
        "excel": excel_parse,
        "manual_stats_txt": manual_parse,
        "baoyan_basics_md": basics_parse,
        "official_documents_brochures": official_report,
        "hybrid_search": hybrid_status,
        "summary": {
            "official_chunks": len(official),
            "experience_chunks": len(experience),
            "official_files": official_report.get("file_count", 0),
        },
    }
    meta = RebuildMeta(
        loaded_at=_utc_now_iso(),
        rebuild_digest=digest,
        manifest_version=manifest.version,
        warnings=tuple(warnings),
        parse_report=parse_report,
    )
    REGISTRY.replace(official, experience, meta)
    return get_legacy_aggregate_status(base)


def ensure_loaded(root: Path | None = None) -> None:
    base = root or repo_root()
    off, exp, meta = REGISTRY.snapshot()
    if meta is None or (not off and not exp):
        rebuild_all(base)


def _to_retrieved_doc(chunk: InternalChunk, match_score: float) -> RetrievedDoc:
    boost = min(5, match_score) * 0.02
    conf = round(min(0.99, chunk.base_confidence + boost), 4)
    text = chunk.text[:4500]
    base: RetrievedDoc = {
        "source": chunk.source_tag,
        "title": chunk.title,
        "content": text,
        "confidence": conf,
        "source_group": chunk.source_group,
        "kb_group": chunk.kb_group,
        "doc_id": chunk.doc_id,
        "provenance": dict(chunk.provenance),
        "match_score": float(match_score),
    }
    meta = build_credibility_fields(
        source_group=chunk.source_group,
        source_tag=chunk.source_tag,
        title=chunk.title,
        text=text,
        provenance=dict(chunk.provenance),
    )
    merged: RetrievedDoc = {**base, **meta}  # type: ignore[misc]
    return merged


def _hybrid_dispatch(
    query: str,
    top_k: int,
    chunks: List[InternalChunk],
) -> List[RetrievedDoc]:
    """Use hybrid search engine to score and order chunks, falling back to lexical."""
    if not _env_bool("ENABLE_HYBRID_SEARCH", True):
        return _lexical_search(query, top_k, chunks)
    try:
        engine = get_hybrid_engine()
        ranked = engine.query(query, top_k, mode="hybrid")
    except Exception:
        return _lexical_search(query, top_k, chunks)
    if not ranked:
        return _lexical_search(query, top_k, chunks)
    chunk_map: Dict[str, InternalChunk] = {c.doc_id: c for c in chunks}
    out: List[RetrievedDoc] = []
    seen: set[str] = set()
    for doc_id, score in ranked:
        ch = chunk_map.get(doc_id)
        if ch is None or doc_id in seen:
            continue
        seen.add(doc_id)
        out.append(_to_retrieved_doc(ch, score))
        if len(out) >= top_k:
            break
    # Pad with lexical results for any remaining slots.
    if len(out) < top_k:
        lex = _lexical_search(query, top_k, [c for c in chunks if c.doc_id not in seen])
        out += lex[: top_k - len(out)]
    return out


def _lexical_search(
    query: str,
    top_k: int,
    chunks: List[InternalChunk],
) -> List[RetrievedDoc]:
    if top_k <= 0:
        return []
    scored = score_chunks(query, chunks, mode="lexical")
    if not scored and chunks:
        scored = [(0, c) for c in chunks[:top_k]]
    out: List[RetrievedDoc] = []
    for score, ch in scored[:top_k]:
        out.append(_to_retrieved_doc(ch, float(score)))
    return out


def search_official(query: str, top_k: int) -> List[RetrievedDoc]:
    ensure_loaded()
    chunks = REGISTRY.official_chunks()
    return _hybrid_dispatch(query, top_k, chunks)


def search_official_in_files(query: str, top_k: int, files: List[str]) -> List[RetrievedDoc]:
    """Search official chunks but restrict to a selected file subset (brochure TXT)."""
    ensure_loaded()
    if top_k <= 0:
        return []
    wanted = [f for f in (files or []) if str(f).strip()]
    if not wanted:
        return []
    suffixes = tuple(wanted)
    chunks = [
        c for c in REGISTRY.official_chunks() if str(c.provenance.get("file") or "").endswith(suffixes)
    ]
    if not chunks:
        return []
    return _hybrid_dispatch(query, top_k, chunks)


def search_experience(query: str, top_k: int) -> List[RetrievedDoc]:
    ensure_loaded()
    chunks = REGISTRY.experience_chunks()
    return _hybrid_dispatch(query, top_k, chunks)


def search_experience_by_kb_groups(query: str, top_k: int, kb_groups: set[str]) -> List[RetrievedDoc]:
    """在经验库子集中检索（如仅小红书 Excel 或仅手工统计 TXT）。"""
    ensure_loaded()
    want = frozenset(str(g) for g in kb_groups)
    chunks = [c for c in REGISTRY.experience_chunks() if str(c.kb_group) in want]
    if top_k <= 0 or not chunks:
        return []
    return _hybrid_dispatch(query, top_k, chunks)


def search_experience_only(query: str, top_k: int) -> List[RetrievedDoc]:
    """Backward-compatible name for Excel-only search used by legacy tools/tests."""
    return search_experience(query, top_k)


def get_legacy_aggregate_status(root: Path | None = None) -> Dict[str, Any]:
    """Shape expected by `/api/kb/status` and legacy tests (experience row_count + global digest)."""
    base = root or repo_root()
    off, exp, meta = REGISTRY.snapshot()
    excel_path = str((base / load_manifest(base).public_info_xhs.excel_path).resolve())
    if meta is None:
        return {
            "loaded": False,
            "row_count": 0,
            "loaded_at": "",
            "checksum": "",
            "path": excel_path,
            "rebuild_digest": "",
            "official_chunk_count": 0,
            "experience_chunk_count": 0,
            "kb_groups": [],
        }
    pr = meta.parse_report or {}
    excel_meta = pr.get("excel") or {}
    brochures_meta = pr.get("official_documents_brochures") or {}
    basics_path = load_manifest(base).public_info_baoyan_basics.md_path
    return {
        "loaded": True,
        "row_count": len(exp),
        "loaded_at": meta.loaded_at,
        "checksum": meta.rebuild_digest[:16],
        "path": excel_path,
        "rebuild_digest": meta.rebuild_digest,
        "official_chunk_count": len(off),
        "experience_chunk_count": len(exp),
        "kb_groups": [
            {
                "kb_group": "official_documents_brochures",
                "label": "官方招生简章（TXT，官方优先）",
                "file_kind": "txt",
                "chunk_count": len(off),
                "file_count": brochures_meta.get("file_count"),
            },
            {
                "kb_group": "public_info_xhs",
                "label": "公众信息库（小红书 Excel）",
                "file_kind": "xlsx",
                "chunk_count": len([c for c in exp if c.kb_group == "public_info_xhs"]),
                "source_rows": excel_meta.get("pandas_rows"),
            },
            {
                "kb_group": "public_info_manual_stats",
                "label": "公众信息库补充（手工统计 TXT）",
                "file_kind": "txt",
                "chunk_count": len([c for c in exp if c.kb_group == "public_info_manual_stats"]),
                "path": str((base / load_manifest(base).public_info_manual_stats.txt_path).resolve()),
            },
            {
                "kb_group": "public_info_baoyan_basics",
                "label": "保研通识库（流程解释，非官方政策）",
                "file_kind": "md",
                "chunk_count": len([c for c in exp if c.kb_group == "public_info_baoyan_basics"]),
                "path": str((base / basics_path).resolve()),
            },
        ],
    }


def get_inspect_snapshot(root: Path | None = None) -> Dict[str, Any]:
    """Verbose multi-source snapshot for admin UI."""
    base = root or repo_root()
    ensure_loaded()
    manifest = load_manifest(base)
    off, exp, meta = REGISTRY.snapshot()

    def samples(chunks: List[InternalChunk], n: int = 2) -> List[Dict[str, Any]]:
        out = []
        for c in sorted(chunks, key=lambda x: x.doc_id)[:n]:
            out.append(
                {
                    "doc_id": c.doc_id,
                    "title": c.title,
                    "preview": (c.text[:280] + "…") if len(c.text) > 280 else c.text,
                    "provenance": c.provenance,
                }
            )
        return out

    sources: List[Dict[str, Any]] = []
    brochures_dir = Path(manifest.official_documents_brochures.directory)
    for c in sorted([c for c in off if c.kb_group == "official_documents_brochures"], key=lambda x: x.doc_id)[:120]:
        rel = str(c.provenance.get("file") or "")
        sources.append(
            {
                "kb_group": "official_documents_brochures",
                "source_group": "official",
                "file_kind": "txt",
                "relative_path": rel,
                "logical_id": rel,
                "title": c.title,
                "chunks": 1,
                "file_exists": (base / rel).exists(),
                "samples": samples([c], 1),
                "dir": str(brochures_dir),
            }
        )

    xlsx_path = manifest.public_info_xhs.excel_path
    manual_txt_path = manifest.public_info_manual_stats.txt_path
    basics_md_path = manifest.public_info_baoyan_basics.md_path
    sources.append(
        {
            "kb_group": "public_info_xhs",
            "source_group": "experience",
            "file_kind": "xlsx",
            "relative_path": xlsx_path,
            "logical_id": "public_info_xhs_excel",
            "title": "公众信息库（小红书 Excel）",
            "chunks": len(exp),
            "file_exists": (base / xlsx_path).exists(),
            "samples": samples(exp, 3),
        }
    )
    sources.append(
        {
            "kb_group": "public_info_manual_stats",
            "source_group": "experience",
            "file_kind": "txt",
            "relative_path": manual_txt_path,
            "logical_id": "public_info_manual_stats_txt",
            "title": "公众信息库补充（手工统计 TXT）",
            "chunks": len([c for c in exp if c.kb_group == "public_info_manual_stats"]),
            "file_exists": (base / manual_txt_path).exists(),
            "samples": samples([c for c in exp if c.kb_group == "public_info_manual_stats"], 3),
        }
    )
    sources.append(
        {
            "kb_group": "public_info_baoyan_basics",
            "source_group": "experience",
            "file_kind": "md",
            "relative_path": basics_md_path,
            "logical_id": "public_info_baoyan_basics_md",
            "title": "保研通识库（流程解释）",
            "chunks": len([c for c in exp if c.kb_group == "public_info_baoyan_basics"]),
            "file_exists": (base / basics_md_path).exists(),
            "samples": samples([c for c in exp if c.kb_group == "public_info_baoyan_basics"], 3),
        }
    )

    return {
        "deterministic": True,
        "manifest_version": manifest.version,
        "loaded_at": meta.loaded_at if meta else "",
        "rebuild_digest": meta.rebuild_digest if meta else "",
        "warnings": list(meta.warnings) if meta else [],
        "parse_verification": dict(meta.parse_report) if meta and meta.parse_report else {},
        "sources": sources,
        "totals": {
            "official_chunks": len(off),
            "experience_chunks": len(exp),
        },
    }
