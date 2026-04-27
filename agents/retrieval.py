"""Staged retrieval: official KB → experience KB → optional web (traceable)."""

from __future__ import annotations

import hashlib
import os
import re
from typing import Dict, List, Tuple

from graph.state import KBScope, QuestionType, RetrievedDoc, RetrievalTrace, TraceStage
from kb.service import ensure_loaded, search_experience, search_official
from kb.tokenize import tokenize_query
from tools.credibility import enrich_experience_against_official, merge_credibility_into_doc
from tools.web_access_bridge import search_web_via_web_access
from tools.web_search import search_web_vertical


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None:
        return default
    try:
        return int(v.strip())
    except ValueError:
        return default

_POLICY = (
    "KB groups: official_finance_pdfs (PDF) vs xiaohongshu_excel (Excel), ingested separately. "
    "kb_scope=hybrid: stage 1 = official index, stage 2 = experience index; merged official-first for generation. "
    "Policy-like queries use larger official top_k and cap experience. "
    "Experience chunks may be annotated with conflict hints vs retrieved official text (inspectable). "
    "Stage 3 = optional web. Web retrieval prefers Web Access (CDP) as primary path; "
    "legacy tools/web_search.py is fallback only. Official conclusions in prompts always precede experience; "
    "experience cannot override PDFs."
)


def _content_preview(doc: RetrievedDoc, limit: int = 280) -> str:
    c = (doc.get("content") or "").replace("\n", " ").strip()
    if len(c) <= limit:
        return c
    return c[: limit - 1] + "…"


def _official_top_k(question_type: QuestionType) -> int:
    if question_type == "experience_reference":
        return 4
    return 12


def _experience_top_k(question_type: QuestionType) -> int:
    if question_type == "experience_reference":
        return 12
    if question_type in {"admission_requirement", "eligibility_evaluation", "major_info"}:
        return 6
    return 8


def _experience_top_k_xiaohongshu_only(question_type: QuestionType) -> int:
    # Large recall window for multi-thousand experience notes.
    default = max(120, _experience_top_k(question_type))
    return max(1, _env_int("KB_EXPERIENCE_TOP_K_XHS_ONLY", default))


def _policy_like_query(user_query: str) -> bool:
    q = user_query.strip()
    ql = q.lower()
    keys = (
        "政策",
        "规定",
        "办法",
        "细则",
        "通知",
        "材料",
        "截止",
        "ddl",
        "推荐信",
        "资格",
        "推免",
        "综合素质",
        "科研",
        "免试",
        "评价",
    )
    return any(k in q for k in keys) or "ddl" in ql


def _web_trigger(user_query: str) -> bool:
    return any(k in user_query for k in ("搜索", "网上", "知乎", "小红书", "公众号", "微信"))


def _trace_stage(
    stage: str,
    source_group: str,
    top_k: int,
    docs: List[RetrievedDoc],
    *,
    kb_debug: bool = False,
) -> TraceStage:
    matched: List[Dict[str, object]] = []
    for d in docs:
        row: Dict[str, object] = {
            "doc_id": d.get("doc_id", ""),
            "title": d["title"],
            "match_score": float(d.get("match_score", 0)),
            "confidence": float(d["confidence"]),
            "source": d["source"],
            "kb_group": d.get("kb_group", ""),
            "provenance": dict(d.get("provenance") or {}),
            "source_type": d.get("source_type", ""),
            "credibility_level": d.get("credibility_level", ""),
            "suspected_ad": bool(d.get("suspected_ad", False)),
            "freshness": d.get("freshness", ""),
            "evidence_role": d.get("evidence_role", ""),
            "ad_risk_reasons": list(d.get("ad_risk_reasons") or []),
        }
        if kb_debug:
            row["content_preview"] = _content_preview(d)
            prov = row["provenance"]
            if isinstance(prov, dict):
                row["locator"] = _human_locator(source_group, prov)
        matched.append(row)
    return TraceStage(stage=stage, source_group=source_group, top_k=top_k, matched=matched)


def _human_locator(source_group: str, prov: Dict[str, object]) -> str:
    if source_group == "official":
        page = prov.get("page")
        mid = prov.get("manifest_id", "")
        return f"pdf page={page} manifest_id={mid}" if page is not None else str(mid)
    if source_group == "experience":
        row = prov.get("excel_row")
        return f"excel_row={row} (1-based sheet row)" if row is not None else "excel"
    if source_group == "web":
        url = prov.get("url", "")
        return f"web url={url}" if url else "web"
    return ""


def _dedupe(docs: List[RetrievedDoc]) -> List[RetrievedDoc]:
    seen: set[str] = set()
    out: List[RetrievedDoc] = []
    for d in docs:
        key = str(d.get("doc_id") or f"{d['source']}:{d['title']}")
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out


def _enrich_web_docs(docs: List[RetrievedDoc]) -> List[RetrievedDoc]:
    enriched: List[RetrievedDoc] = []
    for idx, raw in enumerate(docs):
        d: RetrievedDoc = dict(raw)  # type: ignore[misc]
        href_m = re.search(r"链接：(https?://\S+)", d.get("content", ""))
        href = href_m.group(1) if href_m else ""
        key = f"{d.get('source', '')}|{d.get('title', '')}|{idx}|{href}"
        hid = hashlib.sha256(key.encode("utf-8")).hexdigest()[:14]
        d["doc_id"] = f"web:{hid}"
        d["source_group"] = "web"
        d["kb_group"] = "web"
        if href:
            d.setdefault("provenance", {})
            prov = dict(d.get("provenance") or {})
            prov["url"] = href
            d["provenance"] = prov
        d["match_score"] = float(d.get("match_score", d.get("confidence", 0)))
        enriched.append(merge_credibility_into_doc(d))
    return enriched


def retrieve_documents_with_trace(
    user_query: str,
    question_type: QuestionType,
    enable_web_search: bool = False,
    kb_debug: bool = False,
    kb_scope: KBScope = "hybrid",
) -> Tuple[List[RetrievedDoc], RetrievalTrace]:
    ensure_loaded()
    q = user_query.strip()
    ok = _official_top_k(question_type)
    ek = _experience_top_k(question_type)
    policy_like = _policy_like_query(q)
    if policy_like:
        ok = max(ok, 14)
        ek = min(ek, 4)

    if kb_scope == "official_only":
        ek = 0
    elif kb_scope == "xiaohongshu_only":
        ok = 0
        ek = _experience_top_k_xiaohongshu_only(question_type)

    official_docs = search_official(q, ok) if ok > 0 else []
    experience_docs = search_experience(q, ek) if ek > 0 else []

    if kb_scope == "hybrid" and official_docs and experience_docs:
        enrich_experience_against_official(experience_docs, official_docs)

    merged = _dedupe(list(official_docs) + list(experience_docs))

    stages: List[TraceStage] = [
        _trace_stage("1-official-index", "official", ok, official_docs, kb_debug=kb_debug),
        _trace_stage("2-experience-index", "experience", ek, experience_docs, kb_debug=kb_debug),
    ]

    web_allowed = enable_web_search or _web_trigger(q)
    if kb_scope == "xiaohongshu_only":
        web_allowed = enable_web_search
    elif kb_scope == "official_only":
        web_allowed = enable_web_search

    web_access_used = False
    web_fallback_used = False
    web_failure_reason = ""
    web_primary_source = "web_access_bridge"
    if web_allowed:
        web_raw, web_meta = search_web_via_web_access(q)
        web_access_used = bool(web_meta.get("used", False))
        web_failure_reason = str(web_meta.get("failure_reason", "") or "")
        fallback_enabled = _env_bool("WEB_ACCESS_FALLBACK_ENABLED", True)
        if not web_raw and fallback_enabled:
            web_fallback_used = True
            web_raw = search_web_vertical(q)
            if not web_failure_reason:
                web_failure_reason = "web_access_no_results"
        elif not web_raw and not fallback_enabled:
            web_failure_reason = web_failure_reason or "web_access_failed_and_fallback_disabled"
        web_docs = _enrich_web_docs(web_raw)
        merged = _dedupe(merged + web_docs)
        stages.append(
            _trace_stage("3-web", "web", len(web_docs), web_docs, kb_debug=kb_debug),
        )

    merged_ids = [str(d.get("doc_id") or f"{d['source']}:{d['title']}") for d in merged]

    trace: RetrievalTrace = {
        "policy": _POLICY,
        "stages": stages,
        "merged_for_generation": merged_ids,
        "kb_scope": kb_scope,
        "web_primary_source": web_primary_source,
        "web_access_used": web_access_used,
        "web_fallback_used": web_fallback_used,
        "web_failure_reason": web_failure_reason,
    }
    if kb_debug:
        trace["query"] = q
        trace["query_tokens"] = tokenize_query(q)
        trace["question_type"] = question_type
        trace["policy_like_query"] = policy_like
        trace["docs_passed_to_generation"] = [
            {
                "order": i + 1,
                "doc_id": d.get("doc_id", ""),
                "source_group": d.get("source_group", ""),
                "kb_group": d.get("kb_group", ""),
                "source": d["source"],
                "title": d["title"],
                "match_score": float(d.get("match_score", 0)),
                "credibility_level": d.get("credibility_level", ""),
                "suspected_ad": bool(d.get("suspected_ad", False)),
                "freshness": d.get("freshness", ""),
                "evidence_role": d.get("evidence_role", ""),
                "ad_risk_reasons": list(d.get("ad_risk_reasons") or []),
                "provenance": dict(d.get("provenance") or {}),
                "locator": _human_locator(str(d.get("source_group") or ""), dict(d.get("provenance") or {})),
                "content_preview": _content_preview(d),
            }
            for i, d in enumerate(merged)
        ]
    return merged, trace


def retrieve_documents(
    user_query: str,
    question_type: QuestionType,
    enable_web_search: bool = False,
    kb_scope: KBScope = "hybrid",
) -> List[RetrievedDoc]:
    docs, _trace = retrieve_documents_with_trace(
        user_query,
        question_type,
        enable_web_search,
        kb_scope=kb_scope,
    )
    return docs
