"""Long-plan graph nodes: hydrate → KB retrieval → 五段分块生成 → 合并 Markdown。"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from urllib.parse import quote

from agents.answer import _build_citation_map, _build_references_section, _format_gbt7714
from agents.long_plan import (
    assemble_long_plan_report,
    build_kb_context_from_docs,
    build_long_plan_retrieval_evidence_blocks,
    generate_long_plan_section,
    report_json_to_markdown,
    _long_plan_citation_doc_limit,
    _prior_context_for_part,
    review_and_repair_long_plan_report,
    _web_snippets,
    _web_snippets_per_program,
)
from agents.retrieval import retrieve_documents_with_trace
from agents.router import classify_question
from graph.long_plan_state import LongPlanState
from graph.state import QuestionType


def _long_plan_reference_for_doc(idx: int, doc: dict) -> dict:
    ref = _format_gbt7714(idx, doc)
    if ref.get("url"):
        return ref
    prov = doc.get("provenance") or {}
    if doc.get("source_group") == "official" and isinstance(prov, dict) and prov.get("file"):
        ref["url"] = f"/api/source/official?file={quote(str(prov.get('file')), safe='')}"
    return ref

_BEIJING_TZ = timezone(timedelta(hours=8))


def _beijing_iso() -> str:
    return datetime.now(_BEIJING_TZ).isoformat(timespec="seconds")


def hydrate_long_plan(state: LongPlanState) -> dict:
    intake = state.get("intake") or {}
    school = str(intake.get("current_school") or "").strip()
    target = str(intake.get("target_destination") or "").strip()
    major = str(intake.get("major") or "").strip()
    college = str(intake.get("college") or "").strip()
    parts = [
        "中国人民大学",
        "保研",
        target or school,
        major,
        college,
        "夏令营 预推免 考核",
    ]
    q = " ".join(p for p in parts if p).strip() or "中国人民大学 保研 硕士 博士"
    return {
        "generated_at_iso": _beijing_iso(),
        "retrieval_query": q,
        "error": "",
        "part_generation_errors": {},
    }


def retrieve_long_plan_kb(state: LongPlanState) -> dict:
    q = state.get("retrieval_query") or ""
    qt: QuestionType = classify_question(q)
    use_web = bool(state.get("use_web"))
    docs, trace = retrieve_documents_with_trace(
        user_query=q,
        question_type=qt,
        enable_web_search=use_web,
        kb_debug=False,
        kb_scope="hybrid",
        disable_web_stage=not use_web,
    )
    extra_queries = _long_plan_followup_queries(state.get("intake") or {})
    if extra_queries:
        seen = {
            (
                str(d.get("source_group") or ""),
                str(d.get("title") or "")[:120],
                str(d.get("content") or "")[:180],
            )
            for d in docs
        }
        for extra_q in extra_queries[:5]:
            try:
                more_docs, _more_trace = retrieve_documents_with_trace(
                    user_query=extra_q,
                    question_type=classify_question(extra_q),
                    enable_web_search=False,
                    kb_debug=False,
                    kb_scope="hybrid",
                    disable_web_stage=True,
                )
            except Exception:
                continue
            for d in more_docs[:12]:
                key = (
                    str(d.get("source_group") or ""),
                    str(d.get("title") or "")[:120],
                    str(d.get("content") or "")[:180],
                )
                if key in seen:
                    continue
                seen.add(key)
                docs.append(d)
        trace = dict(trace or {})
        trace["long_plan_followup_queries"] = extra_queries[:5]
    ctx = build_kb_context_from_docs(docs)
    ev_prompt, ev_md = build_long_plan_retrieval_evidence_blocks(docs, trace)

    # Build citation map so each part can reference sources with [N]
    citation_limit = _long_plan_citation_doc_limit()
    citation_map_text, _cmap = _build_citation_map(docs[:citation_limit])
    if citation_map_text:
        ev_prompt = ev_prompt + "\n\n" + citation_map_text
        ev_md = ev_md + "\n\n" + citation_map_text

    return {
        "retrieved_docs": docs,
        "retrieval_trace": trace,
        "kb_context_text": ctx,
        "retrieval_evidence_prompt": ev_prompt,
        "retrieval_evidence_md": ev_md,
    }


def _long_plan_followup_queries(intake: dict) -> list[str]:
    target = " ".join(
        str(intake.get(k) or "")
        for k in ("target_destination", "target_school", "target_college", "major", "college")
    )
    queries: list[str] = []
    if any(x in target for x in ("财政金融", "财金", "证券投资", "金融专硕")):
        queries.extend(
            [
                "人大财金金融专硕保研笔试考什么 投资学 商业银行 数学",
                "中国人民大学财政金融学院金融专硕夏令营笔面经 证券投资方向",
                "人大财金证券投资方向保研 预推免 面试经验 小红书",
                "人大财金保研 商业银行 投资学 数学 笔试 面试",
                "中国人民大学财政金融学院金融专硕保研经验 证投方向",
            ]
        )
    if any(x in target for x in ("信息学院", "电子信息", "人工智能")):
        queries.extend(["人大信息学院电子信息人工智能保研机试面试经验", "人大信息学院保研电子信息人工智能夏令营笔试"])
    if any(x in target for x in ("商学院", "会计")):
        queries.extend(["人大商学院会计保研笔试面试经验", "中国人民大学商学院会计夏令营预推免经验"])
    if any(x in target for x in ("法学院", "法律硕士")):
        queries.extend(["人大法学院法律硕士保研面试经验", "中国人民大学法学院法律硕士预推免经验"])
    return list(dict.fromkeys(queries))


def _run_section(state: LongPlanState, part: int, state_key: str) -> dict:
    intake = state.get("intake") or {}
    kb = state.get("kb_context_text") or ""
    ev = state.get("retrieval_evidence_prompt") or ""
    web = _web_snippets(intake, bool(state.get("use_web")))
    # Part 5: append per-program targeted web search (zhihu/xiaohongshu)
    if part == 5 and bool(state.get("use_web")):
        programs = (state.get("part1_target") or {}).get("programs") or []
        per_prog_web = _web_snippets_per_program(programs)
        if per_prog_web:
            web = (web + "\n\n" + per_prog_web).strip()
    iso = state.get("generated_at_iso") or _beijing_iso()
    prior = _prior_context_for_part(dict(state), part)
    data, err = generate_long_plan_section(part, intake, kb, ev, web, iso, prior)
    errs = dict(state.get("part_generation_errors") or {})
    if err:
        errs[str(part)] = err
    return {state_key: data, "part_generation_errors": errs}


def generate_long_plan_part1(state: LongPlanState) -> dict:
    return _run_section(state, 1, "part1_target")


def generate_long_plan_part2(state: LongPlanState) -> dict:
    return _run_section(state, 2, "part2_diagnosis")


def generate_long_plan_part3(state: LongPlanState) -> dict:
    return _run_section(state, 3, "part3_timeline")


def generate_long_plan_part4(state: LongPlanState) -> dict:
    return _run_section(state, 4, "part4_action")


def generate_long_plan_part5(state: LongPlanState) -> dict:
    return _run_section(state, 5, "part5_prep")


def merge_long_plan(state: LongPlanState) -> dict:
    try:
        report = assemble_long_plan_report(
            state.get("part1_target") or {},
            state.get("part2_diagnosis") or {},
            state.get("part3_timeline") or {},
            state.get("part4_action") or {},
            state.get("part5_prep") or {},
            state.get("intake") or {},
            state.get("generated_at_iso") or _beijing_iso(),
            state.get("retrieval_evidence_md") or "",
            state.get("part_generation_errors") or {},
        )
        report = review_and_repair_long_plan_report(
            report,
            state.get("intake") or {},
            state.get("retrieved_docs") or [],
        )
        md = report_json_to_markdown(report)

        # Build citation references from retrieved docs (like quick Q&A)
        docs = state.get("retrieved_docs") or []
        lpr_refs: list = []
        if docs:
            from agents.long_plan import build_kb_context_from_docs as _ctx
            # Use citation map from the answer system
            map_text, cmap = _build_citation_map(docs[:_long_plan_citation_doc_limit()])
            md, lpr_refs = _build_references_section(md, cmap)
            # HTML 报告展示完整资料清单；Markdown 正文仍只追加已引用条目。
            lpr_refs = [_long_plan_reference_for_doc(i, doc) for i, doc in enumerate(docs[:_long_plan_citation_doc_limit()], 1)]
            report["_references"] = lpr_refs

        return {
            "report": report,
            "report_markdown": md,
            "error": "",
            "references": lpr_refs,
            "retrieved_docs": docs,
            "retrieval_trace": state.get("retrieval_trace"),
        }
    except Exception as exc:
        return {"error": str(exc), "report": {}, "report_markdown": "", "references": []}
