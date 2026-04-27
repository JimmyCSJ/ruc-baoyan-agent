"""Answer generation module.

Owner: member 3 (answer quality, prompts, output format, tests).
Responsibility: render answer text from state and prompt strategy.
Avoid putting retrieval source-selection logic here.
"""

import os
from typing import Dict, List

from langchain_openai import ChatOpenAI

from config import get_settings
from graph.state import QuestionType, RetrievedDoc


def ensure_triple_heading_answer(answer: str) -> str:
    """Lightweight guard: surface shape issues instead of silent fixes."""
    a = (answer or "").strip()
    if not a:
        return a
    has_o = "【官方结论】" in a
    has_e = "【经验参考】" in a
    has_u = "不确定性" in a and "冲突" in a
    if has_o and has_e and has_u:
        return a
    return (
        "【输出校验】模型回答未完整包含约定的三段标题（官方结论 / 经验参考 / 不确定性/冲突说明）。"
        "以下为原始输出，请优先对照知识库中的正式 PDF 证据人工核对。\n\n" + a
    )


def _group_label(doc: RetrievedDoc) -> str:
    g = doc.get("source_group")
    if g == "official":
        return "official"
    if g == "experience":
        return "experience"
    if g == "web":
        return "web"
    return "other"


def _meta_line(doc: RetrievedDoc) -> str:
    st = doc.get("source_type", "")
    kg = doc.get("kb_group", "")
    cred = doc.get("credibility_level", "")
    ad = doc.get("suspected_ad", False)
    fresh = doc.get("freshness", "")
    role = doc.get("evidence_role", "")
    reasons = doc.get("ad_risk_reasons") or []
    rs = "；".join(reasons) if reasons else "无"
    return (
        f"[kb_group={kg}|source_type={st}|credibility={cred}|suspected_ad={ad}|freshness={fresh}|"
        f"evidence_role={role}|ad_signals={rs}]"
    )


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


def _doc_sort_key(doc: RetrievedDoc) -> tuple[float, float]:
    return (float(doc.get("match_score", 0)), float(doc.get("confidence", 0)))


def _compact_content(doc: RetrievedDoc, max_chars: int) -> str:
    txt = str(doc.get("content", "") or "").strip()
    if len(txt) <= max_chars:
        return txt
    return txt[: max_chars - 1] + "…"


def _select_docs_for_llm(retrieved_docs: List[RetrievedDoc]) -> List[RetrievedDoc]:
    """Large recall → controlled packing for LLM context budget."""
    total_char_budget = max(4000, _env_int("LLM_CONTEXT_MAX_CHARS", 28000))
    per_doc_char_budget = max(200, _env_int("LLM_CONTEXT_DOC_MAX_CHARS", 700))

    group_limits = {
        "official": max(1, _env_int("LLM_CONTEXT_MAX_OFFICIAL_DOCS", 18)),
        "experience": max(1, _env_int("LLM_CONTEXT_MAX_EXPERIENCE_DOCS", 36)),
        "web": max(0, _env_int("LLM_CONTEXT_MAX_WEB_DOCS", 8)),
        "other": max(0, _env_int("LLM_CONTEXT_MAX_OTHER_DOCS", 6)),
    }

    buckets: Dict[str, List[RetrievedDoc]] = {"official": [], "experience": [], "web": [], "other": []}
    for doc in retrieved_docs:
        buckets[_group_label(doc)].append(doc)
    for g in buckets:
        buckets[g].sort(key=_doc_sort_key, reverse=True)

    selected: List[RetrievedDoc] = []
    used_chars = 0
    idx = {g: 0 for g in buckets}
    picked = {g: 0 for g in buckets}
    order = ("official", "experience", "web", "other")

    while True:
        progressed = False
        for g in order:
            if picked[g] >= group_limits[g]:
                continue
            if idx[g] >= len(buckets[g]):
                continue
            cand = buckets[g][idx[g]]
            idx[g] += 1
            piece = _compact_content(cand, per_doc_char_budget)
            est = len(piece) + 220
            if selected and used_chars + est > total_char_budget:
                continue
            selected.append(cand)
            used_chars += est
            picked[g] += 1
            progressed = True
        if not progressed:
            break

    if not selected and retrieved_docs:
        # Always pass at least one doc, even under strict budget.
        selected.append(max(retrieved_docs, key=_doc_sort_key))

    return selected


def format_context_for_llm(retrieved_docs: List[RetrievedDoc]) -> str:
    """Order: official → experience → web; explicit headers for policy priority."""
    packed_docs = _select_docs_for_llm(retrieved_docs)
    buckets = {"official": [], "experience": [], "web": [], "other": []}
    for doc in packed_docs:
        buckets[_group_label(doc)].append(doc)

    lines: List[str] = []
    lines.append(f"【上下文打包】retrieved={len(retrieved_docs)} packed={len(packed_docs)}")
    lines.append("")

    def emit_block(header: str, docs: List[RetrievedDoc]) -> None:
        if not docs:
            return
        lines.append(header)
        for doc in docs:
            did = doc.get("doc_id", "")
            prov = doc.get("provenance") or {}
            prov_s = ""
            if prov:
                prov_s = f"|prov={prov}"
            ms = doc.get("match_score", 0)
            meta = _meta_line(doc)
            lines.append(
                f"- {meta} [doc_id={did}|{doc['source']}|{doc['title']}|match={ms}|conf={doc['confidence']}{prov_s}] "
                f"{_compact_content(doc, max(200, _env_int('LLM_CONTEXT_DOC_MAX_CHARS', 700)))}"
            )
        lines.append("")

    emit_block(
        "【正式文件 / indexed official — 规则与政策以本节为准；经验与网页不得否定本节】",
        buckets["official"],
    )
    emit_block(
        "【经验帖 / supplementary experience — 仅为学长学姐主观经验，可能过时；不得覆盖正式文件】",
        buckets["experience"],
    )
    emit_block(
        "【联网网页 / web — 未经验证，可能含推广或过时信息；仅作线索】",
        buckets["web"],
    )
    emit_block("【其他 / other】", buckets["other"])
    return "\n".join(lines).strip()


def generate_llm_answer(user_query: str, question_type: QuestionType, retrieved_docs: List[RetrievedDoc]) -> str:
    settings = get_settings()
    if not settings.deepseek_api_key:
        raise ValueError("DEEPSEEK_API_KEY is not set.")

    context = format_context_for_llm(retrieved_docs)
    prompt = (
        "你是中国人民大学学生的保研规划与研究助手。\n"
        "每条资料行前带有可信度与推广风险标签（credibility、suspected_ad、freshness 等），必须遵守。\n"
        "硬性规则：\n"
        "1. 「正式文件」中的制度、资格、时间节点为「官方结论」的唯一依据。\n"
        "2. 标注 suspected_ad=true 或 ad_signals 非空的资料不得在「官方结论」中当作事实；"
        "仅可在「经验参考」中谨慎转述并提示核实。\n"
        "3. freshness=possibly_outdated 或 web_unverified 的内容须提示「可能过时或未验证」。\n"
        "4. 若正式文件与经验/网页冲突，只采信正式文件，并在「不确定性」中说明冲突。\n"
        "\n"
        "输出格式（必须严格使用以下三级标题，即使某节无内容也写一行「暂无。」）：\n"
        "### 【官方结论】\n"
        "（仅基于正式文件与 high 可信度政策信息；不写推广性经验）\n"
        "### 【经验参考】\n"
        "（学长学姐流程、心态、准备技巧；标注信息可能过时；遇 suspected_ad 须提醒警惕营销）\n"
        "### 【不确定性 / 冲突说明】\n"
        "（资料缺口、版本不明、与经验矛盾之处、需向学院确认的要点）\n"
        "\n"
        f"问题分类：{question_type}\n"
        f"用户问题：{user_query}\n"
        f"资料（已按来源分组）：\n{context}\n"
    )

    llm = ChatOpenAI(
        model=settings.deepseek_model,
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        default_headers={"X-Failover-Enabled": str(settings.failover_enabled).lower()},
        temperature=settings.llm_temperature,
        top_p=settings.llm_top_p,
        max_tokens=settings.llm_max_tokens,
        frequency_penalty=settings.llm_frequency_penalty,
        extra_body={"top_k": settings.llm_top_k},
    )
    return ensure_triple_heading_answer(str(llm.invoke(prompt).content or ""))


def generate_mock_answer(user_query: str, question_type: QuestionType, retrieved_docs: List[RetrievedDoc]) -> str:
    ctx = format_context_for_llm(retrieved_docs)
    return ensure_triple_heading_answer(
        (
            f"基于你的问题“{user_query}”，这是一个 mock 测试回答。\n"
            f"问题分类：{question_type}\n"
            "### 【官方结论】\n"
            "（演示模式：请启用真实大模型以生成完整分层回答。）\n"
            "### 【经验参考】\n"
            "暂无。\n"
            "### 【不确定性 / 冲突说明】\n"
            "mock 模式下未调用模型，以下为检索分组资料：\n"
            f"{ctx}\n"
        )
    )
