"""Inspectable official brochure KB: per-file counts, samples, and official-only retrieval tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.retrieval import retrieve_documents_with_trace
from kb.manifest import load_manifest, repo_root
from kb.registry import REGISTRY
from kb.service import ensure_loaded
from kb.tokenize import tokenize_query


def _evenly_spaced(items: List[dict], n: int) -> List[dict]:
    if not items or n <= 0:
        return []
    if len(items) <= n:
        return list(items)
    if n == 1:
        return [items[0]]
    out: List[dict] = []
    for i in range(n):
        idx = int(round(i * (len(items) - 1) / (n - 1)))
        out.append(items[idx])
    return out


def _sample_chunks_for_files(files: List[str], n: int, base: Path) -> List[Dict[str, Any]]:
    ensure_loaded(base)
    official_chunks, _exp, _meta = REGISTRY.snapshot()
    wanted = set(files)
    sub = [c for c in official_chunks if str(c.provenance.get("file") or "") in wanted]
    sub = sorted(sub, key=lambda c: str(c.provenance.get("file") or ""))
    out: List[Dict[str, Any]] = []
    for c in _evenly_spaced(
        [
            {
                "doc_id": c.doc_id,
                "title": c.title,
                "preview": (c.text[:500] + "…") if len(c.text) > 500 else c.text,
                "char_count": len(c.text),
                "file": c.provenance.get("file"),
                "truncated": bool(c.provenance.get("truncated")),
            }
            for c in sub
        ],
        n,
    ):
        out.append(c)
    return out


def _chunk_count_for_files(files: List[str], base: Path) -> Dict[str, Any]:
    ensure_loaded(base)
    official_chunks, _exp, _meta = REGISTRY.snapshot()
    wanted = set(files)
    sub = [c for c in official_chunks if str(c.provenance.get("file") or "") in wanted]
    truncated = sum(1 for c in sub if bool(c.provenance.get("truncated")))
    chars_total = sum(len(c.text) for c in sub)
    return {
        "files": files,
        "chunk_count": len(sub),
        "truncated_files": truncated,
        "chars_total": chars_total,
        "quality_hint": "ok" if len(sub) > 0 and chars_total / max(1, len(sub)) >= 120 else "possibly_poor_extract",
    }


def _official_only_retrieval_tests(
    files: List[str],
    questions: List[str],
    top_k: int,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for q in questions:
        docs, trace = retrieve_documents_with_trace(
            q,
            question_type="admission_requirement",
            enable_web_search=False,
            kb_debug=True,
            kb_scope="official_only",
        )
        # Filter to the requested brochure files only.
        wanted = set(files)
        filtered = []
        for d in docs:
            prov = d.get("provenance") or {}
            if isinstance(prov, dict) and str(prov.get("file") or "") in wanted:
                filtered.append(d)
        filtered = filtered[:top_k]
        rows = []
        for d in filtered:
            prov = d.get("provenance") or {}
            preview = str(d.get("content") or "")[:520]
            readable = bool(re.search(r"[\u4e00-\u9fff]{6,}", preview)) if isinstance(preview, str) else False
            rows.append(
                {
                    "doc_id": d.get("doc_id"),
                    "file": prov.get("file") if isinstance(prov, dict) else None,
                    "title": d.get("title"),
                    "match_score": d.get("match_score"),
                    "query_tokens": tokenize_query(q),
                    "content_preview": preview,
                    "readable_chinese_hint": readable,
                }
            )
        results.append(
            {
                "question": q,
                "kb_scope": "official_only",
                "query_tokens": tokenize_query(q),
                "retrieved_chunks_for_these_files": rows,
                "trace_top_stage": trace.get("stages", [None])[0] if isinstance(trace, dict) else None,
            }
        )
    return results


def build_official_pdfs_verify_report(
    *,
    sample_chunks_per_pdf: int = 3,
    top_k_per_question: int = 5,
    questions_by_manifest_id: Optional[Dict[str, List[str]]] = None,
    root: Optional[Path] = None,
) -> Dict[str, Any]:
    base = root or repo_root()
    manifest = load_manifest(base)
    ensure_loaded(base)

    # Use a small set of generic policy queries to sanity-check official_only retrieval.
    default_questions = [
        "招生简章里对申请条件/资格有哪些要求？",
        "需要准备哪些材料？有没有截止时间（DDL）？",
        "面试/考核一般包含哪些环节？",
    ]
    questions = (list(questions_by_manifest_id.values())[0] if questions_by_manifest_id else default_questions)

    # In schema v2, official brochures are a directory; we verify by sampling files.
    from kb.official_brochures import list_brochure_entries

    entries = list_brochure_entries(base, Path(manifest.official_documents_brochures.directory))
    files = [e.file for e in entries]
    sample_files = [e.file for e in entries[: min(len(entries), 12)]]

    count = _chunk_count_for_files(files, base)
    samples = _sample_chunks_for_files(sample_files, sample_chunks_per_pdf, base)
    tests = _official_only_retrieval_tests(sample_files, questions, top_k_per_question)

    return {
        "kb_group": "official_documents_brochures",
        "brochure_files_total": len(files),
        "sample_chunks_per_pdf": sample_chunks_per_pdf,
        "top_k_per_question": top_k_per_question,
        "note_scoring": "当前 official_only 检索为轻量 lexical scorer：query 分词 token 在 chunk(标题+正文) 中出现则计 1 分，按分数降序。",
        "meta": count,
        "samples": samples,
        "retrieval_tests": tests,
    }

