"""Rebuild, search, and inspect the knowledge base."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from graph.state import RetrievedDoc
from kb.experience_excel import load_experience_excel
from tools.credibility import build_credibility_fields
from kb.internal import InternalChunk
from kb.manifest import KBManifest, load_manifest, repo_root
from kb.official_pdf import load_official_pdf, summarize_official_chunks
from kb.registry import REGISTRY, RebuildMeta, compute_rebuild_digest
from kb.scoring import score_chunks


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def rebuild_all(root: Path | None = None) -> Dict[str, Any]:
    base = root or repo_root()
    manifest = load_manifest(base)
    manifest_text = (base / "data/kb/manifest.yaml").read_text(encoding="utf-8")

    official: List[InternalChunk] = []
    official_reports: List[Dict[str, Any]] = []
    for entry in sorted(manifest.official_documents, key=lambda e: e.id):
        entry_chunks = load_official_pdf(entry, base)
        official.extend(entry_chunks)
        official_reports.append(summarize_official_chunks(entry, entry_chunks))

    experience, xlsx_warnings, excel_parse = load_experience_excel(manifest.experience, base)
    warnings = list(xlsx_warnings)

    digest = compute_rebuild_digest(official, experience, manifest_text)
    parse_report: Dict[str, Any] = {
        "excel": excel_parse,
        "official_documents": official_reports,
        "summary": {
            "official_chunks": len(official),
            "experience_chunks": len(experience),
            "official_files": len(official_reports),
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


def _to_retrieved_doc(chunk: InternalChunk, match_score: int) -> RetrievedDoc:
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


def search_official(query: str, top_k: int) -> List[RetrievedDoc]:
    ensure_loaded()
    chunks = REGISTRY.official_chunks()
    if top_k <= 0:
        return []
    scored = score_chunks(query, chunks)
    if not scored and chunks:
        scored = [(0, c) for c in chunks[:top_k]]
    out: List[RetrievedDoc] = []
    for score, ch in scored[:top_k]:
        out.append(_to_retrieved_doc(ch, score))
    return out


def search_experience(query: str, top_k: int) -> List[RetrievedDoc]:
    ensure_loaded()
    chunks = REGISTRY.experience_chunks()
    if top_k <= 0:
        return []
    scored = score_chunks(query, chunks)
    if not scored and chunks:
        scored = [(0, c) for c in chunks[:top_k]]
    out: List[RetrievedDoc] = []
    for score, ch in scored[:top_k]:
        out.append(_to_retrieved_doc(ch, score))
    return out


def search_experience_only(query: str, top_k: int) -> List[RetrievedDoc]:
    """Backward-compatible name for Excel-only search used by legacy tools/tests."""
    return search_experience(query, top_k)


def get_legacy_aggregate_status(root: Path | None = None) -> Dict[str, Any]:
    """Shape expected by `/api/kb/status` and legacy tests (experience row_count + global digest)."""
    base = root or repo_root()
    off, exp, meta = REGISTRY.snapshot()
    excel_path = str((base / load_manifest(base).experience.excel_path).resolve())
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
                "kb_group": "official_finance_pdfs",
                "label": "学院正式 PDF（政策规则）",
                "file_kind": "pdf",
                "chunk_count": len(off),
                "file_count": len(pr.get("official_documents") or []),
            },
            {
                "kb_group": "xiaohongshu_excel",
                "label": "小红书笔记 Excel（经验轶事）",
                "file_kind": "xlsx",
                "chunk_count": len(exp),
                "source_rows": excel_meta.get("pandas_rows"),
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
    for entry in sorted(manifest.official_documents, key=lambda e: e.id):
        p = (base / entry.path).resolve()
        sub = [c for c in off if c.provenance.get("manifest_id") == entry.id]
        sources.append(
            {
                "kb_group": "official_finance_pdfs",
                "source_group": "official",
                "file_kind": "pdf",
                "relative_path": entry.path,
                "logical_id": entry.id,
                "title": entry.title,
                "chunks": len(sub),
                "file_exists": p.exists(),
                "samples": samples(sub, 3),
            }
        )

    xlsx_path = manifest.experience.excel_path
    sources.append(
        {
            "kb_group": "xiaohongshu_excel",
            "source_group": "experience",
            "file_kind": "xlsx",
            "relative_path": xlsx_path,
            "logical_id": "xiaohongshu_excel",
            "title": "小红书笔记 Excel",
            "chunks": len(exp),
            "file_exists": (base / xlsx_path).exists(),
            "samples": samples(exp, 3),
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
