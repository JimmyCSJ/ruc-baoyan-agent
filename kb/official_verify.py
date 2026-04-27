"""Inspectable official PDF KB: per-file counts, samples, and official-only retrieval tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.retrieval import retrieve_documents_with_trace
from kb.manifest import OfficialEntry, load_manifest, repo_root
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


def _sample_chunks_for_entry(entry: OfficialEntry, n: int, base: Path) -> List[Dict[str, Any]]:
    ensure_loaded(base)
    official_chunks, _exp, _meta = REGISTRY.snapshot()
    sub = [c for c in official_chunks if c.provenance.get("manifest_id") == entry.id]
    sub = sorted(sub, key=lambda c: int(c.provenance.get("page") or 0))
    out: List[Dict[str, Any]] = []
    for c in _evenly_spaced(
        [
            {
                "doc_id": c.doc_id,
                "page": c.provenance.get("page"),
                "title": c.title,
                "preview": (c.text[:500] + "…") if len(c.text) > 500 else c.text,
                "char_count": len(c.text),
                "scan_like": ("未提取到文本" in c.text) or bool(c.provenance.get("empty_extract")),
                "extracted_chars": c.provenance.get("extracted_chars"),
                "normalized_chars": c.provenance.get("normalized_chars"),
            }
            for c in sub
        ],
        n,
    ):
        out.append(c)
    return out


def _chunk_count_for_entry(entry: OfficialEntry, base: Path) -> Dict[str, Any]:
    ensure_loaded(base)
    official_chunks, _exp, _meta = REGISTRY.snapshot()
    sub = [c for c in official_chunks if c.provenance.get("manifest_id") == entry.id]
    scan_like = sum(1 for c in sub if ("未提取到文本" in c.text) or bool(c.provenance.get("empty_extract")))
    chars_total = sum(len(c.text) for c in sub)
    return {
        "manifest_id": entry.id,
        "title": entry.title,
        "path": entry.path,
        "chunk_count": len(sub),
        "pages_scan_like_or_empty": scan_like,
        "chars_total": chars_total,
        "quality_hint": "ok"
        if len(sub) > 0 and scan_like == 0 and chars_total / max(1, len(sub)) >= 120
        else "possibly_poor_extract",
    }


def _official_only_retrieval_tests(
    entry: OfficialEntry,
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
        # Filter to this PDF's chunks only (same manifest_id).
        filtered = []
        for d in docs:
            prov = d.get("provenance") or {}
            if isinstance(prov, dict) and prov.get("manifest_id") == entry.id:
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
                    "page": prov.get("page") if isinstance(prov, dict) else None,
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
                "retrieved_chunks_for_this_pdf": rows,
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

    default_q: Dict[str, List[str]] = {
        "sfb-2026-general-exemption": [
            "一般类型免试推荐的基本条件是什么？",
            "推免流程有哪些关键时间节点/截止时间？",
            "需要提交哪些材料（例如成绩、排名、证明）？",
        ],
        "sfb-research-evaluation": [
            "科研能力评价办法的评分维度与分值如何规定？",
            "科研成果/论文/项目如何计分？是否有上限？",
        ],
        "sfb-comprehensive-quality-2025": [
            "综合素质拓展评价的项目类别有哪些？如何认定？",
            "综合素质评价是否有分项上限或计分规则？",
        ],
    }
    qmap = questions_by_manifest_id or default_q

    pdfs: List[Dict[str, Any]] = []
    for entry in sorted(manifest.official_documents, key=lambda e: e.id):
        count = _chunk_count_for_entry(entry, base)
        samples = _sample_chunks_for_entry(entry, sample_chunks_per_pdf, base)
        tests = _official_only_retrieval_tests(entry, qmap.get(entry.id, []), top_k_per_question)
        pdfs.append(
            {
                "meta": count,
                "samples": samples,
                "retrieval_tests": tests,
                "readability_check": {
                    "expectation": "若 preview 中出现连续可读中文条款/编号/表述，且 pages_scan_like_or_empty=0，则解析质量通常可用。",
                    "how_to_judge": [
                        "是否大量乱码/断字/每行只剩 1-2 个字？",
                        "是否整页都是「未提取到文本」提示？",
                        "是否能看到条款关键词：应当/必须/不得/提交/材料/评价/计分等。",
                    ],
                },
            }
        )

    return {
        "kb_group": "official_finance_pdfs",
        "pdf_count": len(pdfs),
        "sample_chunks_per_pdf": sample_chunks_per_pdf,
        "top_k_per_question": top_k_per_question,
        "note_scoring": "当前 official_only 检索为轻量 lexical scorer：query 分词 token 在 chunk(标题+正文) 中出现则计 1 分，按分数降序。",
        "pdfs": pdfs,
    }

