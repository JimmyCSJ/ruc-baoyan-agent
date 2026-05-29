"""Staged retrieval: official KB → public info KB → optional web (traceable)."""

from __future__ import annotations

import hashlib
import os
import re
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from graph.state import KBScope, QuestionType, RetrievedDoc, RetrievalTrace, TraceStage
from openai import OpenAI

from config import get_settings
from kb.manifest import load_manifest, repo_root
from kb.official_brochures import read_brochure_text_by_filename
from kb.service import ensure_loaded, search_experience, search_experience_by_kb_groups, search_official
from kb.tokenize import tokenize_query
from tools.credibility import build_credibility_fields, enrich_experience_against_official, merge_credibility_into_doc
from tools.web_access_bridge import search_web_via_web_access
from tools.web_search import search_web_baidu, search_web_vertical


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
    "KB groups: official_documents_brochures (TXT) vs public_info_xhs (Excel), ingested separately. "
    "kb_scope=hybrid: stage 1 = official index, stage 2 = public index; merged official-first for generation. "
    "Policy-like queries use larger official top_k and cap public. "
    "Public chunks may be annotated with conflict hints vs retrieved official text (inspectable). "
    "Stage 3 = optional web. Web retrieval prefers Web Access (CDP) as primary path; "
    "legacy tools/web_search.py is fallback only. Official conclusions in prompts always precede public; "
    "public cannot override official brochures."
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


def _experience_top_k_public_only(question_type: QuestionType) -> int:
    # Large recall window for multi-thousand public notes.
    default = max(120, _experience_top_k(question_type))
    return max(1, _env_int("KB_PUBLIC_TOP_K_PUBLIC_ONLY", _env_int("KB_EXPERIENCE_TOP_K_XHS_ONLY", default)))


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


_PROGRAM_STATS_KEYS = (
    "项目",
    "专硕",
    "学硕",
    "直博",
    "博士",
    "硕士",
    "夏令营",
    "预推免",
    "九推",
    "推免",
    "学院",
    "财金",
    "经济",
    "金融",
    "会计",
    "商学",
    "法学院",
    "录取",
    "招生",
    "考核",
    "面试",
    "笔试",
    "简章",
    "专业",
)

_COLLEGE_ALIASES: Dict[str, str] = {
    "财金": "财政金融学院",
    "财政金融": "财政金融学院",
    "商学院": "商学院",
    "经济学院": "经济学院",
    "智慧治理": "智慧治理学院",
    "智治": "智慧治理学院",
    "高瓴": "高瓴人工智能学院",
    "信息学院": "信息学院",
    "统计": "统计学院",
    "统计学院": "统计学院",
    "统计与大数据": "统计与大数据研究院",
    "法学院": "法学院",
    "劳人": "劳动人事学院",
    "劳动人事": "劳动人事学院",
    "公管": "公共管理学院",
    "公共管理": "公共管理学院",
    "国关": "国际关系学院",
    "国际关系": "国际关系学院",
    "新闻": "新闻学院",
    "新闻学院": "新闻学院",
    "人大": "中国人民大学",
}

_PROGRAM_ALIASES: Dict[str, str] = {
    "金专": "金融专硕 金融",
    "金融专硕": "金融专硕 金融",
    "证投": "证券投资方向 证券管理与投资方向",
    "证券投资": "证券投资方向 证券管理与投资方向",
    "金融科技": "金融科技 金科 编程 计算机基础",
    "国金": "国际金融 国际金融高级学院",
    "会计": "会计 专业硕士",
    "税务": "税务 专业硕士",
    "保险": "保险 专业硕士",
    "数字经济": "数字经济",
    "人工智能": "人工智能 电子信息",
}

_INTENT_TERMS: Dict[str, Tuple[str, ...]] = {
    "exam": ("笔试", "科目", "题型", "考什么", "专业课", "数学", "闭卷"),
    "interview": ("面试", "自我介绍", "英文面", "专业面", "压力面", "追问"),
    "materials": ("材料", "简历", "个人陈述", "推荐信", "成绩单", "排名证明"),
    "recommendation": ("推免资格", "学院推荐", "综合成绩", "排名", "加分", "免试推荐"),
    "receiving": ("夏令营", "预推免", "九推", "接收", "优秀营员", "拟录取"),
    "mentor": ("导师", "联系导师", "邮件", "导师考核"),
    "process": ("保研", "推免", "夏令营", "预推免", "九推", "接收录取", "推免资格"),
}


def _stage_label(stage: str) -> str:
    return {
        "recommendation_and_receiving": "推免资格与目标院校接收",
        "recommendation": "本校推免资格",
        "receiving": "目标学院接收",
        "general_process": "保研流程与项目判断",
    }.get(stage, stage)


def _intent_label(intent: str) -> str:
    return {
        "exam": "笔试",
        "interview": "面试",
        "materials": "材料",
        "recommendation": "推免资格",
        "receiving": "夏令营/预推免/九推",
        "mentor": "导师联系",
        "process": "流程判断",
    }.get(intent, intent)


def _build_query_plan(user_query: str, question_type: QuestionType) -> Dict[str, Any]:
    q = (user_query or "").strip()
    colleges = [name for alias, name in _COLLEGE_ALIASES.items() if alias in q]
    # Keep order while deduping.
    colleges = list(dict.fromkeys(colleges))
    program_terms: List[str] = []
    for alias, expanded in _PROGRAM_ALIASES.items():
        if alias in q:
            program_terms.extend(expanded.split())
    program_terms = list(dict.fromkeys(program_terms))

    intents: List[str] = []
    for intent, terms in _INTENT_TERMS.items():
        if any(t in q for t in terms):
            intents.append(intent)
    if question_type == "experience_reference" and "receiving" not in intents:
        intents.append("receiving")
    if not intents:
        intents.append("process")

    if "recommendation" in intents and "receiving" in intents:
        baoyan_stage = "recommendation_and_receiving"
    elif "recommendation" in intents:
        baoyan_stage = "recommendation"
    elif "receiving" in intents or any(x in intents for x in ("exam", "interview")):
        baoyan_stage = "receiving"
    else:
        baoyan_stage = "general_process"

    expansion_terms: List[str] = []
    expansion_terms.extend(colleges)
    expansion_terms.extend(program_terms)
    for intent in intents:
        expansion_terms.extend(_INTENT_TERMS.get(intent, ()))
    if "保研" in q or "推免" in q or question_type in {"general_info", "experience_reference"}:
        expansion_terms.extend(_INTENT_TERMS["process"])

    expansion_terms = [x for x in dict.fromkeys(expansion_terms) if x and x not in q]
    expanded_query = " ".join([q] + expansion_terms)

    return {
        "original_query": q,
        "expanded_query": expanded_query,
        "detected_colleges": colleges,
        "detected_program_terms": program_terms,
        "intents": intents,
        "baoyan_stage": baoyan_stage,
        "needs_college_depth": bool(colleges or program_terms or any(k in q for k in ("学院", "专业", "方向", "人大"))),
        "needs_basics": baoyan_stage in {"general_process", "recommendation_and_receiving"} or any(
            k in q for k in ("是什么", "区别", "流程", "夏令营", "预推免", "九推", "导师", "推荐信", "个人陈述")
        ),
        "needs_experience_depth": any(i in intents for i in ("exam", "interview", "receiving", "materials", "mentor")),
        "needs_official_policy": any(i in intents for i in ("recommendation", "materials")) or _policy_like_query(q),
    }


def _rank_docs_for_plan(docs: List[RetrievedDoc], plan: Dict[str, Any]) -> List[RetrievedDoc]:
    colleges = [str(x) for x in plan.get("detected_colleges") or []]
    program_terms = [str(x) for x in plan.get("detected_program_terms") or []]
    intents = set(str(x) for x in plan.get("intents") or [])

    def score(doc: RetrievedDoc) -> float:
        sg = str(doc.get("source_group") or "")
        kg = str(doc.get("kb_group") or "")
        title = str(doc.get("title") or "")
        content = str(doc.get("content") or "")
        blob = f"{title}\n{content}"
        s = float(doc.get("confidence") or 0) + float(doc.get("match_score") or 0) * 0.05
        if sg == "official":
            s += 1.0
        if kg == "public_info_manual_stats" and plan.get("needs_college_depth"):
            s += 0.55
        if kg == "public_info_xhs" and plan.get("needs_experience_depth"):
            s += 0.5
        if kg == "public_info_baoyan_basics" and plan.get("needs_basics"):
            s += 0.48
        if kg == "public_info_baoyan_basics" and plan.get("needs_college_depth") and "general_process" != plan.get("baoyan_stage"):
            s -= 0.22
        for term in colleges + program_terms:
            if term and term in blob:
                s += 0.38
        for intent in intents:
            for term in _INTENT_TERMS.get(intent, ()):
                if term in blob:
                    s += 0.08
        if doc.get("suspected_ad"):
            s -= 0.45
        if doc.get("credibility_level") == "low":
            s -= 0.22
        return s

    return sorted(docs, key=score, reverse=True)


def _query_wants_program_stats(user_query: str) -> bool:
    q = (user_query or "").strip()
    return any(k in q for k in _PROGRAM_STATS_KEYS)


def _evidence_is_weak(docs: List[RetrievedDoc]) -> bool:
    """命中条数少或匹配分整体偏低时，扩大小红书经验召回。"""
    if len(docs) <= 3:
        return True
    scores = [float(d.get("match_score") or 0) for d in docs]
    mx = max(scores) if scores else 0.0
    exp_like = sum(1 for d in docs if str(d.get("source_group")) == "experience")
    if mx < 2.0 and exp_like < 6 and len(docs) < 14:
        return True
    return False


def _apply_manual_stats_and_weak_xhs_boost(
    q: str,
    question_type: QuestionType,
    kb_scope: KBScope,
    merged: List[RetrievedDoc],
    execution_steps: List[str],
) -> List[RetrievedDoc]:
    """并入 ruc_2026_manual_stats.txt；命中弱时扩大 public_info_xhs 召回。"""
    out = list(merged)

    # official_only 不含公众库。手工统计 / 小红书扩召回仅在 hybrid、public_only 下执行。
    boost_manual = kb_scope in ("hybrid", "public_only") and (
        _query_wants_program_stats(q)
        or question_type
        in (
            "major_info",
            "admission_requirement",
            "eligibility_evaluation",
            "experience_reference",
            "general_info",
        )
    )
    if boost_manual:
        mk = _env_int("KB_MANUAL_STATS_TOP_K", 14)
        manual = search_experience_by_kb_groups(q, mk, {"public_info_manual_stats"})
        if manual:
            execution_steps.append(f"检索补强：并入手工录取/专业结构统计（{len(manual)} 条）")
            out = _dedupe(out + manual)

    if kb_scope in ("hybrid", "public_only") and _evidence_is_weak(out):
        xk = _env_int("KB_WEAK_FALLBACK_XHS_TOP_K", 64)
        xhs = search_experience_by_kb_groups(q, xk, {"public_info_xhs"})
        if xhs:
            execution_steps.append(f"检索补强：命中偏少，扩大小红书经验库召回（{len(xhs)} 条）作归纳参考")
            out = _dedupe(out + xhs)

    return out


def _read_filenames_txt() -> List[str]:
    base = repo_root()
    manifest = load_manifest(base)
    brochures_dir = Path(manifest.official_documents_brochures.directory)
    path = (base / brochures_dir / "filenames.txt").resolve()
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8", errors="ignore")
    return [
        ln.strip()
        for ln in raw.splitlines()
        if ln.strip()
        and (ln.strip().lower().endswith(".txt") or ln.strip().lower().endswith(".pdf"))
        and ln.strip().lower() != "filenames.txt"
    ]


def _select_official_files_via_llm(query: str, *, max_files: int = 6) -> List[str]:
    """LLM picks which official brochure TXT files to read based on query + filenames.txt."""
    settings = get_settings()
    if not settings.enable_real_llm or not settings.moark_api_key:
        import logging as _logging
        _logging.warning(
            "LLM file selector skipped: enable_real_llm=%s has_api_key=%s",
            settings.enable_real_llm, bool(settings.moark_api_key),
        )
        return []

    filenames = _read_filenames_txt()
    if not filenames:
        import logging as _logging
        _logging.warning("LLM file selector skipped: filenames.txt empty or missing")
        return []

    # Keep prompt bounded; the file list can be large.
    preview = filenames[:1200]
    file_list_text = "\n".join(f"- {name}" for name in preview)
    if len(filenames) > len(preview):
        file_list_text += f"\n（其余 {len(filenames) - len(preview)} 个文件名省略）"

    prompt = (
        "你是一个文件选择器。给定用户问题和可读的官方文件名列表，请选择最相关的文件名。\n"
        "要求：\n"
        f"- 最多返回 {max_files} 个文件名\n"
        "- 只能从给定列表中选择，必须完全一致（区分大小写按原样返回）\n"
        "- 只输出 JSON，格式：{\"files\":[\"a.txt\",...],\"reason\":\"...\"}\n\n"
        f"用户问题：{query}\n\n"
        f"可选官方文件名列表：\n{file_list_text}\n"
    )

    client = OpenAI(base_url=settings.moark_base_url, api_key=settings.moark_api_key)
    try:
        resp = client.chat.completions.create(
            model=settings.moark_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=512,
            temperature=0.2,
        )
        text = (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        # Never break retrieval pipeline due to selector model/network failures.
        import logging as _logging
        _logging.warning("LLM file selector failed: %s (model=%s base_url=%s)", exc, settings.moark_model, settings.moark_base_url)
        return []
    try:
        m = re.search(r"\{[\s\S]*\}", text)
        obj = json.loads(m.group(0) if m else text)
        files = obj.get("files") or []
        if not isinstance(files, list):
            import logging
            logging.getLogger("ruc_baoyan").warning("LLM file selector: files not a list, got %s", type(files).__name__)
            return []
        picked = [str(x).strip() for x in files if str(x).strip()]
    except Exception as exc2:
        import logging as _logging
        _logging.warning("LLM file selector JSON parse failed: %s, raw text: %.200s", exc2, text)
        return []

    allowed = set(filenames)
    out: List[str] = []
    for f in picked:
        if f in allowed and f not in out:
            out.append(f)
        if len(out) >= max_files:
            break
    if not out and picked:
        import logging as _logging
        _logging.warning(
            "LLM file selector: all %d picked names rejected by allowed set. picked=%.300s",
            len(picked), picked,
        )
    return out


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
            "evidence_quality_tier": d.get("evidence_quality_tier", ""),
            "evidence_quality_label": d.get("evidence_quality_label", ""),
            "credibility_notes": list(d.get("credibility_notes") or []),
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
        file = prov.get("file") or ""
        page = prov.get("page")
        if file and page is not None:
            return f"file={file} page={page}"
        if file:
            return f"file={file}"
        mid = prov.get("manifest_id", "")
        return f"manifest_id={mid}" if mid else "official"
    if source_group == "experience":
        file = prov.get("file")
        section = prov.get("section_title")
        if file and section:
            return f"file={file} section={section}"
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
    *,
    disable_web_stage: bool = False,
) -> Tuple[List[RetrievedDoc], RetrievalTrace]:
    ensure_loaded()
    q = user_query.strip()
    query_plan = _build_query_plan(q, question_type)
    retrieval_query = str(query_plan.get("expanded_query") or q)
    execution_steps: List[str] = []
    official_files_read: List[str] = []
    stage_text = _stage_label(str(query_plan.get("baoyan_stage") or ""))
    intent_text = "、".join(_intent_label(str(x)) for x in (query_plan.get("intents") or []))
    execution_steps.append(
        f"理解问题：先判断这是“{stage_text}”问题，重点关注{intent_text or '学院项目信息'}，再拆成官方政策、历史规模和经验考核三条线。"
    )
    if retrieval_query != q:
        execution_steps.append("扩展检索：补充目标学院、专业方向、推免/夏令营/预推免等关键词，避免只按原句做表面匹配。")
    force_comprehensive = _env_bool("FORCE_COMPREHENSIVE_SEARCH", True)
    ok = _official_top_k(question_type)
    ek = _experience_top_k(question_type)
    policy_like = bool(query_plan.get("needs_official_policy")) or _policy_like_query(q)
    if policy_like:
        ok = max(ok, 14)
        ek = min(ek, 4)

    if kb_scope == "official_only":
        ek = 0
    elif kb_scope == "public_only":
        ok = 0
        ek = _experience_top_k_public_only(question_type)

    if force_comprehensive:
        # Platform policy: always run broad cross-source retrieval for more complete judgments.
        execution_steps.append("证据策略：同步检索官方材料、公众经验和联网线索；最终结论仍以正式文件为准。")
        if kb_scope != "official_only":
            ek = max(ek, 12)

    official_docs: List[RetrievedDoc] = []
    if ok > 0:
        execution_steps.append("官方材料检索：优先定位目标学院、目标专业和推免相关的正式文件。")
        execution_steps.append("材料筛选：从官方材料中挑选与招生规模、专业方向、推免规则最相关的内容。")
        selected = _select_official_files_via_llm(retrieval_query, max_files=min(10, ok))
        if selected:
            official_files_read = list(selected)
            execution_steps.append("官方依据提取：读取入选官方材料的关键条款，并用于限定回答边界。")
            base = repo_root()
            manifest = load_manifest(base)
            brochures_dir = Path(manifest.official_documents_brochures.directory)
            # Read raw brochure texts (AI-selected) and pass them directly to the answering model.
            for idx, fname in enumerate(selected[:ok]):
                try:
                    info = read_brochure_text_by_filename(base, brochures_dir, fname, max_chars=18000)
                except Exception:
                    continue
                title = str(info.get("title") or fname)
                content = str(info.get("text") or "")
                prov = {"file": info.get("file"), "chunk_kind": "brochure_txt", "truncated": bool(info.get("truncated"))}
                meta = build_credibility_fields(
                    source_group="official",
                    source_tag="official_brochure",
                    title=title,
                    text=content,
                    provenance=prov,
                )
                official_docs.append(
                    {
                        "source": "official_brochure",
                        "title": title,
                        "content": content,
                        "confidence": 0.94,
                        "source_group": "official",
                        "kb_group": "official_documents_brochures",
                        "doc_id": f"official:brochure:{prov.get('file')}",
                        "provenance": prov,
                        "match_score": float(max(1, ok - idx)),
                        **meta,
                    }
                )
            # If reading failed or resulted empty, fallback to legacy scoring.
            if not official_docs:
                official_docs = search_official(retrieval_query, ok)
        else:
            execution_steps.append("官方依据提取：未能完成精确筛选时，改用官方库常规检索补齐依据。")
            official_docs = search_official(retrieval_query, ok)
    experience_docs = search_experience(retrieval_query, ek) if ek > 0 else []

    basics_docs: List[RetrievedDoc] = []
    if kb_scope in ("hybrid", "public_only") and query_plan.get("needs_basics"):
        basics_docs = search_experience_by_kb_groups(
            retrieval_query,
            _env_int("KB_BAOYAN_BASICS_TOP_K", 8),
            {"public_info_baoyan_basics"},
        )
        if basics_docs:
            execution_steps.append(f"检索补强：并入保研通识库（{len(basics_docs)} 条），用于解释流程和概念。")

    if kb_scope == "hybrid" and official_docs and experience_docs:
        enrich_experience_against_official(experience_docs, official_docs)

    merged = _dedupe(list(official_docs) + list(experience_docs) + list(basics_docs))
    merged = _apply_manual_stats_and_weak_xhs_boost(retrieval_query, question_type, kb_scope, merged, execution_steps)

    stages: List[TraceStage] = [
        _trace_stage("1-official-index", "official", ok, official_docs, kb_debug=kb_debug),
        _trace_stage("2-experience-index", "experience", ek, experience_docs, kb_debug=kb_debug),
    ]
    if basics_docs:
        stages.append(
            _trace_stage(
                "2b-baoyan-basics",
                "experience",
                len(basics_docs),
                basics_docs,
                kb_debug=kb_debug,
            )
        )

    if disable_web_stage:
        web_allowed = False
    else:
        web_allowed = enable_web_search or _web_trigger(q)
        if force_comprehensive:
            web_allowed = True
        if kb_scope == "public_only":
            web_allowed = enable_web_search
        elif kb_scope == "official_only":
            web_allowed = enable_web_search
        if force_comprehensive and kb_scope in {"public_only", "official_only"}:
            web_allowed = True

    # KB 不足自动兜底：本地召回为空或信息量不足时，强制开启联网
    _kb_insufficient = (
        len(merged) == 0
        or (
            len(merged) <= 2
            and max((float(d.get("match_score", 0)) for d in merged), default=0) < 1.5
        )
    )
    if _kb_insufficient and not web_allowed:
        web_allowed = True
        execution_steps.append(
            f"检索兜底：本地 KB 召回不足（共 {len(merged)} 条），自动触发联网搜索补充"
        )

    web_access_used = False
    web_fallback_used = False
    web_failure_reason = ""
    web_primary_source = "web_access_bridge"
    if web_allowed:
        web_raw, web_meta = search_web_via_web_access(retrieval_query)
        web_access_used = bool(web_meta.get("used", False))
        web_failure_reason = str(web_meta.get("failure_reason", "") or "")
        fallback_enabled = _env_bool("WEB_ACCESS_FALLBACK_ENABLED", True)
        if not web_raw and fallback_enabled:
            web_fallback_used = True
            web_raw = search_web_vertical(retrieval_query)
            if not web_failure_reason:
                web_failure_reason = "web_access_no_results"
        if not web_raw:
            # Baidu as last-resort fallback when DDGS is blocked in China
            web_raw = search_web_baidu(retrieval_query)
            web_failure_reason = web_failure_reason or "web_access_and_ddgs_failed"
        if not web_raw and not fallback_enabled and not web_fallback_used:
            web_failure_reason = web_failure_reason or "web_access_failed_and_fallback_disabled"
        web_docs = _enrich_web_docs(web_raw)
        merged = _dedupe(merged + web_docs)
        stages.append(
            _trace_stage("3-web", "web", len(web_docs), web_docs, kb_debug=kb_debug),
        )

    # Reranker: cross-encoder rescore on the full candidate pool.
    if _env_bool("ENABLE_RERANKER", False):
        from kb.reranker import get_reranker

        try:
            reranker = get_reranker()
            pre_count = len(merged)
            merged = reranker.rerank(retrieval_query, merged)
            execution_steps.append(
                f"重排序：交叉编码器重新打分（{pre_count} 条 → top-{len(merged)}）"
            )
        except Exception as exc:
            execution_steps.append(f"重排序跳过（{type(exc).__name__}: {exc}）")

    merged = _rank_docs_for_plan(merged, query_plan)
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
        "query_plan": query_plan,
    }
    trace["execution_steps"] = execution_steps
    trace["official_files_read"] = official_files_read
    if kb_debug:
        trace["query"] = q
        trace["expanded_query"] = retrieval_query
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
                "evidence_quality_tier": d.get("evidence_quality_tier", ""),
                "evidence_quality_label": d.get("evidence_quality_label", ""),
                "credibility_notes": list(d.get("credibility_notes") or []),
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
        disable_web_stage=False,
    )
    return docs
