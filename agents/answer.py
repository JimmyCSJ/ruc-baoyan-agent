"""Answer generation module.

Owner: member 3 (answer quality, prompts, output format, tests).
Responsibility: render answer text from state and prompt strategy.
Avoid putting retrieval source-selection logic here.
"""

import os
import re
from datetime import datetime
from typing import Any, Dict, List, Tuple

from openai import OpenAI

from config import get_settings
from graph.state import QuestionType, RetrievedDoc

_COLD_COLLEGES = [
    "哲学学院",
    "历史学院",
    "马克思主义学院",
    "文学院",
    "生态环境学院",
    "信息资源管理学院",
    "国学院",
    "统计与大数据研究院",
    "化学与生命资源学院",
    "数学学院",
    "社会学院（专业学位）",
    "物理学院",
    "社会学院",
    "教育学院",
    "中共党史党建学院",
    "艺术学院",
    "人口与健康学院",
    "纪检监察学院",
    "国际文化交流学院",
    "心理学系",
    "和平与发展学院",
    "体育部",
    "国际学院",
]

LQ = "“"  # left curly double quote
RQ = "”"  # right curly double quote


def current_date_cn() -> str:
    """Return the current local date for prompts."""
    return datetime.now().strftime("%Y年%m月%d日")


def ensure_three_section_answer(answer: str) -> str:
    """Guarantee answer has Summary + Uncertainty sections.

    Retrieval process section is prepended by graph/nodes.py.
    """
    a = (answer or "").strip()
    if not a:
        return "### 【总结回答】\n暂无。\n\n### 【不确定性 / 冲突说明】\n暂无。"
    has_s = "【总结回答】" in a
    has_u = "不确定性" in a and "冲突" in a
    if has_s and has_u:
        return a
    if has_s and not has_u:
        return a.rstrip() + "\n\n### 【不确定性 / 冲突说明】\n暂无。"
    # No summary heading: wrap original content as summary.
    return f"### 【总结回答】\n{a}\n\n### 【不确定性 / 冲突说明】\n暂无。"


def _looks_truncated_answer(answer: str, finish_reason: str = "") -> bool:
    a = (answer or "").strip()
    if finish_reason == "length":
        return True
    if not a:
        return False
    tail = a[-240:]
    if re.search(r"(本周你可以|本周可执行|立即着手|动作清单)", a) and len(
        re.findall(r"动作|目标|时间点|核验|整理|模拟|复盘", tail)
    ) <= 2:
        return True
    return bool(re.search(r"[/：:、，,；;和并及]$", tail))


def _fallback_actions_for_query(user_query: str) -> str:
    q = user_query or ""
    if "财政金融" in q or "财金" in q:
        return (
            "| 动作 | 目标 | 时间点 / 条件 |\n"
            "|---|---|---|\n"
            "| 做财政金融学院方向对比表 | 把金融、金融科技、保险、税务的官方文件、经验题型、名额线索分列，避免把不同方向混在一起判断 | 今天完成第一版 |\n"
            "| 核对官方口径 | 逐项标出哪些来自招生简章、哪些来自推免办法、哪些只是经验或手工统计 | 本周内复核一次学院官网 |\n"
            "| 按目标方向补短板 | 金融重点补数理与投资/银行；金科补编程与数据结构；税务/保险补政策热点和实务案例 | 本周每天 1 个模块 |\n"
            "| 做一次笔面试模拟 | 用目标方向问题测试自己能否解释原理、联系现实案例并回答追问 | 周末前完成一次复盘 |\n"
        )
    return (
        "| 动作 | 目标 | 时间点 / 条件 |\n"
        "|---|---|---|\n"
        "| 建目标学院材料表 | 区分官方要求、经验线索和待核验信息 | 今天完成第一版 |\n"
        "| 核验最新通知 | 避免用过时经验替代学院当年通知 | 本周内检查学院官网 |\n"
        "| 做一次模拟问答 | 检验材料、笔试和面试准备是否能说清楚 | 周末前完成复盘 |\n"
    )


def ensure_answer_completion(
    answer: str,
    user_query: str = "",
    *,
    force: bool = False,
    finish_reason: str = "",
) -> str:
    """Repair common model truncation around action lists and uncertainty section."""
    a = ensure_three_section_answer(answer)
    truncated = force or _looks_truncated_answer(answer, finish_reason)
    action_hits = len(re.findall(r"\|\s*动作\s*\||本周可执行动作|目标\s*\|\s*时间点|^\s*[-*]\s*", a, re.M))
    needs_actions = truncated or ("本周" in a and action_hits < 2)
    if needs_actions and "本周可执行动作" not in a:
        insert = "\n\n### 【本周可执行动作】\n" + _fallback_actions_for_query(user_query).strip() + "\n"
        m = re.search(r"\n###\s*【不确定性\s*/\s*冲突说明】", a)
        if m:
            a = a[: m.start()] + insert + a[m.start():]
        else:
            a = a.rstrip() + insert

    if truncated:
        repaired_uncertainty = (
            "模型原始输出疑似在行动清单附近被截断；上方“本周可执行动作”为系统根据问题类型补齐的保守行动建议。"
            "涉及具体名额、考核安排和方向调整，仍需以财政金融学院及中国人民大学当年正式通知为准。"
        )
        a = re.sub(
            r"(###\s*【不确定性\s*/\s*冲突说明】\s*)(暂无。?|无。?)",
            r"\1" + repaired_uncertainty,
            a,
            count=1,
        )
        if "### 【不确定性 / 冲突说明】" not in a:
            a = a.rstrip() + "\n\n### 【不确定性 / 冲突说明】\n" + repaired_uncertainty
    return a


def _summary_is_placeholder(answer: str) -> bool:
    m = re.search(r"###\s*【总结回答】\s*\n([\s\S]*?)(?:\n###\s*【|$)", answer or "")
    if not m:
        return True
    s = re.sub(r"\s+", "", (m.group(1) or ""))
    return (not s) or s in {"暂无。", "暂无", "无", "无。", "未命中", "未命中。"}


def _non_official_fallback(user_query: str, retrieved_docs: List[RetrievedDoc]) -> str:
    exp_docs = [d for d in retrieved_docs if d.get("source_group") == "experience"]
    web_docs = [d for d in retrieved_docs if d.get("source_group") == "web"]
    if not exp_docs and not web_docs:
        return ""

    exp_docs.sort(key=_doc_sort_key, reverse=True)
    web_docs.sort(key=_doc_sort_key, reverse=True)
    lines: List[str] = [
        "### 【总结回答】",
        "这次没从已读取的官方文件里抽到可直接回答的明确条款；先给你一版基于经验帖和联网线索的可执行参考：",
    ]
    idx = 1
    for d in (exp_docs[:3] + web_docs[:2]):
        title = str(d.get("title") or "（无标题）").strip()
        snippet = _compact_content(d, 120).replace("\n", " ").strip()
        if snippet:
            lines.append(f"{idx}. {title}：{snippet}")
            idx += 1

    lines.extend(
        [
            "",
            "### 【不确定性 / 冲突说明】",
            "- 上述信息来自经验帖/网页，可能过时或带有个体偏差，不能替代学院正式通知。",
            f"- 关于{LQ}{user_query}{RQ}的最终结论，建议你以目标学院当年招生简章、学院官网和最新通知为准。",
        ]
    )
    return "\n".join(lines)


def _cold_college_rule(user_query: str) -> str:
    q = user_query or ""
    hit = [x for x in _COLD_COLLEGES if x in q]
    if not hit:
        return ""
    names = "、".join(hit)
    return (
        "附加规则（冷门学院提问命中）：\n"
        f"- 用户问题涉及 {names} 时，优先输出 2026/2025 录取规模、扩缩招和培养类型结构。\n"
        f"- 不展开到{LQ}具体专业如何准备{RQ}的长建议，除非用户明确追问准备方法。\n"
    )


def _tone_rule(question_type: QuestionType, user_query: str) -> str:
    policy_like = question_type in {"admission_requirement", "eligibility_evaluation"}
    planning_like = question_type in {"experience_reference", "general_info", "major_info"}
    if policy_like:
        return (
            "语气与表达要求（本题偏政策/资格）：\n"
            "- 语气严谨、边界清楚，优先给规则与口径，不要口语化过度。\n"
            f"- 对时间点、材料、资格条件要写明确；不确定项要显式标注{LQ}需以学院通知核实{RQ}。\n"
        )
    if planning_like:
        return (
            "语气与表达要求（本题偏咨询/规划）：\n"
            f"- 保持亲切、有人味，像学长学姐给建议；可用{LQ}你可以/建议你先{RQ}这类表达。\n"
            "- 在亲切语气下保持高信息密度，每条建议都要能落地执行（动作+时间/条件）。\n"
            f"- 避免生硬术语或{LQ}投研简报{RQ}腔调，优先学生能直接照做的表达。\n"
        )
    return ""


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
    quality = doc.get("evidence_quality_label", "")
    model_label = doc.get("evidence_model_label", "")
    model_stars = doc.get("evidence_model_stars", "")
    model_review = doc.get("evidence_model_review") if isinstance(doc.get("evidence_model_review"), dict) else {}
    model_usage = str(model_review.get("usage_guidance") or "")
    model_truth = model_review.get("truthfulness_judgment") if isinstance(model_review.get("truthfulness_judgment"), dict) else {}
    model_truth_level = str(model_truth.get("level") or "")
    notes = doc.get("credibility_notes") or []
    reasons = doc.get("ad_risk_reasons") or []
    rs = "；".join(reasons) if reasons else "无"
    ns = "；".join(str(x) for x in notes[:2]) if notes else "无"
    return (
        f"[kb_group={kg}|source_type={st}|credibility={cred}|suspected_ad={ad}|freshness={fresh}|"
        f"evidence_role={role}|quality={quality}|model_label={model_label}|model_stars={model_stars}|"
        f"model_truth={model_truth_level}|model_usage={model_usage}|credibility_notes={ns}|ad_signals={rs}]"
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
    """Large recall -> controlled packing for LLM context budget."""
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


def _build_citation_map(packed_docs: List[RetrievedDoc]) -> Tuple[str, Dict[int, RetrievedDoc]]:
    """Build [N] citation mapping table and return (map_text, {idx: doc})."""
    if not packed_docs:
        return "", {}
    lines: List[str] = ["【引用编号映射 — 请在回答中用 [N] 标注引用的来源编号】"]
    cmap: Dict[int, RetrievedDoc] = {}
    for i, doc in enumerate(packed_docs, 1):
        sg = doc.get("source_group", "other")
        sg_label = {"official": "正式文件", "experience": "经验帖", "web": "联网网页"}.get(sg, "其他")
        title = (doc.get("title") or "无标题").strip()
        url = ""
        prov = doc.get("provenance") or {}
        if isinstance(prov, dict):
            url = str(prov.get("url", ""))
        extra = f" URL={url}" if url else ""
        lines.append(f"[{i}] {sg_label} | {title}{extra}")
        cmap[i] = doc
    lines.append("")
    return "\n".join(lines), cmap


def format_context_for_llm(retrieved_docs: List[RetrievedDoc]) -> Tuple[str, Dict[int, RetrievedDoc]]:
    """Order: official -> experience -> web; explicit headers for policy priority.
    Returns (context_text, citation_map).
    """
    packed_docs = _select_docs_for_llm(retrieved_docs)
    buckets = {"official": [], "experience": [], "web": [], "other": []}
    for doc in packed_docs:
        buckets[_group_label(doc)].append(doc)

    lines: List[str] = []
    lines.append(f"【上下文打包】retrieved={len(retrieved_docs)} packed={len(packed_docs)}")
    lines.append("")

    # Citation mapping table
    map_text, citation_map = _build_citation_map(packed_docs)
    if map_text:
        lines.append(map_text)

    def emit_block(header: str, docs: List[RetrievedDoc]) -> None:
        if not docs:
            return
        lines.append(header)
        for idx, doc in enumerate(docs):
            # Find this doc's citation index in packed_docs
            cit_idx = None
            for ci, cd in enumerate(packed_docs, 1):
                if cd is doc:
                    cit_idx = ci
                    break
            ctag = f"[{cit_idx}] " if cit_idx else ""
            did = doc.get("doc_id", "")
            prov = doc.get("provenance") or {}
            prov_s = ""
            if prov:
                prov_s = f"|prov={prov}"
            ms = doc.get("match_score", 0)
            meta = _meta_line(doc)
            lines.append(
                f"- {ctag}{meta} [doc_id={did}|{doc['source']}|{doc['title']}|match={ms}|conf={doc['confidence']}{prov_s}] "
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
    return "\n".join(lines).strip(), citation_map


def _build_references_section(
    answer_text: str,
    citation_map: Dict[int, RetrievedDoc],
) -> Tuple[str, List[Dict[str, Any]]]:
    """Extract [N] citations from answer and append GB/T 7714 references section."""
    used = sorted(set(
        int(m) for m in re.findall(r"\[(\d+)\]", answer_text)
        if int(m) in citation_map
    ))
    if not used:
        return answer_text, []

    refs: List[Dict[str, Any]] = []
    ref_lines = ["", "### 【参考文献】"]
    for idx in used:
        doc = citation_map[idx]
        entry = _format_gbt7714(idx, doc)
        refs.append(entry)
        ref_lines.append(f"[{idx}] {entry['entry']}")

    return answer_text + "\n" + "\n".join(ref_lines), refs


def _format_gbt7714(idx: int, doc: RetrievedDoc) -> Dict[str, Any]:
    """Format a single reference entry in GB/T 7714 style."""
    sg = doc.get("source_group", "")
    title = (doc.get("title") or "无标题").strip()
    url = ""
    prov = doc.get("provenance") or {}
    if isinstance(prov, dict):
        url = str(prov.get("url", ""))
    kb_group = doc.get("kb_group", "")

    if sg == "official":
        org = "中国人民大学"
        entry = f"{org}{kb_group}. {title}[EB/OL]. 中国人民大学研究生招生网, 2026."
    elif sg == "web":
        if url:
            today = datetime.now().strftime("%Y-%m-%d")
            entry = f"{title}[EB/OL]. ({today})[{today}]. {url}."
        else:
            entry = f"{title}[EB/OL]. 网络来源, 2026."
    elif sg == "experience":
        entry = f"{title}[EB/OL]. 小红书/知乎保研经验分享, 2025-2026."
    else:
        entry = f"{title}[EB/OL]."

    return {"index": idx, "entry": entry, "url": url, "title": title, "source_group": sg}


def _has_web_sources(retrieved_docs: List[RetrievedDoc]) -> bool:
    return any(doc.get("source_group") == "web" for doc in retrieved_docs)


DISCLAIMER_WEB = (
    "注：带有网络溯源的内容提取自过往经验分享，仅供参考。"
    "最新招生要求请以人大陆续发布的官方文件为准。"
)


def generate_llm_answer(
    user_query: str,
    question_type: QuestionType,
    retrieved_docs: List[RetrievedDoc],
    data_agent_result: str = "",
) -> Tuple[str, List[Dict[str, Any]]]:
    settings = get_settings()
    if not settings.moark_api_key:
        raise RuntimeError(
            "请先设置 MOARK_API_KEY 或 DEEPSEEK_API_KEY（二选一），并设置 ENABLE_REAL_LLM=true；"
            "BASE_URL 可用 MOARK_BASE_URL 或 DEEPSEEK_BASE_URL。请确认 .env 位于项目根目录且已重启服务。"
        )

    context, citation_map = format_context_for_llm(retrieved_docs)
    # Prepend structured data results as high-credibility context.
    if data_agent_result.strip():
        context = data_agent_result.strip() + "\n\n" + context
    cold_rule = _cold_college_rule(user_query)
    tone_rule = _tone_rule(question_type, user_query)
    today_cn = current_date_cn()
    prompt = (
        "你是中国人民大学学生的保研规划与研究助手。\n"
        f"当前日期：{today_cn}。凡涉及{LQ}今年{RQ}{LQ}当年{RQ}{LQ}最新{RQ}，都必须以这个日期作为时间锚点；"
        "若资料年份早于当前日期，需说明可能过时。\n"
        "每条资料行前带有模型逐条复核结果（model_label、model_stars、model_truth、model_usage），必须优先遵守。\n"
        "模型复核标签含义：官方依据=5星，可作规则依据；高价值经验=4星，可作准备建议；"
        "经验线索=3星，只能辅助归纳；待核验线索=2星，必须提示核验；低可信线索=1星，不得支撑关键结论。\n"
        "执行作风：高主动性、反偷懒。先穷尽证据再下结论，不允许敷衍式回答。\n"
        "在内部思考中必须完成：\n"
        "A) 证据盘点：官方/公众/联网各自是否覆盖、是否有冲突；\n"
        f"B) 结论门槛：若结论无法被证据支持，明确写{LQ}暂不能下最终结论{RQ}并给核验路径；\n"
        "C) 行动闭环：至少给出 3 条本周可执行动作（动作 + 目标 + 时间点/条件）。\n"
        f"禁止行为：空话、复述问题、只写{LQ}暂无{RQ}后结束。\n"
        "硬性规则：\n"
        f"1. {LQ}正式文件{RQ}中的制度、资格、时间节点为{LQ}官方结论{RQ}的唯一依据。\n"
        f"2. 标注 suspected_ad=true 或 ad_signals 非空的资料不得在{LQ}官方结论{RQ}中当作事实；"
        f"仅可在{LQ}经验参考{RQ}中谨慎转述并提示核实。\n"
        f"3. model_stars<=2 的内容须提示{LQ}需要核验{RQ}，不得写成确定事实。\n"
        f"4. 若正式文件与经验/网页冲突，只采信正式文件，并在{LQ}不确定性{RQ}中说明冲突。\n"
        f"5. 知识库中的{LQ}正式文件{RQ}多为各学院发布的研究生招生/考研考核说明（初试、复试科目等）。"
        f"回答保研/推免问题时必须区分：哪些是{LQ}全国统考/考研复试{RQ}口径、哪些是{LQ}推免/夏令营{RQ}口径；"
        f"若资料主要为考研简章，须在回答中明确写出{LQ}本节依据为考研招生材料，推免考核请以当年推免/夏令营通知为准{RQ}，"
        "并综合 kb_group=public_info_xhs 的小红书经验摘录与联网结果，归纳推免侧常见准备要点（标注为经验归纳，非官方承诺）。\n"
        f"6. 若资料含{LQ}手工统计数据{RQ}（标题或来源含 public_info_manual_stats / 手工统计），"
        "介绍项目或学院时可引用其中的历史录取与结构数据，并注明为手工整理、年份与口径以文件为准。\n"
        f"7. 当官方条文对当前问题覆盖不足时，须在{LQ}总结回答{RQ}中基于小红书经验库与联网摘要做有条理的经验归纳，"
        f"并明确{LQ}以下为学长学姐经验归纳{RQ}，不得把经验写成官方结论。\n"
        "8. 衔接与连贯性要求（强制）：\n"
        "   - 同时引用官方文件与经验帖/网页时，必须使用自然过渡句式将多源信息融合为连贯论证。\n"
        f"     示例：{LQ}官方简章规定了X，而结合往届学长学姐的经验，实操中还需要注意Y{RQ}\n"
        f"   - 禁止机械罗列{LQ}根据资料A...根据资料B...{RQ}这种生硬分段。\n"
        "   - 文风专业、连贯、自然，像经验丰富的学长学姐在提供系统性建议，而非拼凑资料。\n"
        "9. 引用标注要求（强制）：\n"
        "   - 关键结论和数据后必须标注来源编号，如 [1]、[2]、[3]。\n"
        f"   - 编号对应上文{LQ}引用编号映射{RQ}表格中的 [N]。只引用映射表中存在的编号。\n"
        "   - 官方文件优先引用，经验帖和网页作为补充。\n"
        "\n"
        "输出格式（必须严格使用以下标题，即使某节无内容也写一行「暂无。」）：\n"
        "### 【总结回答】\n"
        "（对用户问题给出清晰、可执行且高信息密度的回答；结论以官方文件为准，公众信息仅作补充）\n"
        "写作要求（在本节内部尽量覆盖，缺信息可省略并写明）：\n"
        "- 先给 1 句话结论，再给 4-8 条要点，避免空话。\n"
        "- 要点优先覆盖：考察维度/评价口径、准备动作与时间线、材料与证据、项目/专业与名额、常见误区。\n"
        "- 每条尽量包含可执行动作、条件或范围，不要只给原则。\n"
        f"- 若缺少官方明确数据（如名额），要明确标注{LQ}官方未明确披露/以当年通知为准{RQ}，并给可行核验路径。\n"
        f"- 若问题是咨询/规划类，至少给出 3 条{LQ}本周可执行动作{RQ}（例如：准备材料、模拟面试、联系学院核验）。\n"
        "- 标注信息来源编号如 [1]、[2]，让读者能追溯每条结论的依据。\n"
        "### 【不确定性 / 冲突说明】\n"
        "（资料缺口、版本不明、与经验矛盾之处、需向学院确认的要点）\n"
        "不要在正文末尾自行添加参考文献列表；系统会单独生成参考文献。正文只保留 [1] 这类引用编号。\n"
        "\n"
        f"问题分类：{question_type}\n"
        f"用户问题：{user_query}\n"
        f"{cold_rule}\n"
        f"{tone_rule}\n"
        f"资料（已按来源分组）：\n{context}\n"
    )

    client = OpenAI(
        base_url=settings.moark_base_url,
        api_key=settings.moark_api_key,
    )
    resp = client.chat.completions.create(
        model=settings.moark_model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=min(settings.llm_max_tokens, 8192),
        temperature=settings.llm_temperature,
        top_p=settings.llm_top_p,
        frequency_penalty=settings.llm_frequency_penalty,
        **({"extra_body": settings.llm_extra_body} if settings.llm_extra_body else {}),
    )
    content = (resp.choices[0].message.content or "").strip()
    finish_reason = str(getattr(resp.choices[0], "finish_reason", "") or "")
    answer = ensure_answer_completion(content, user_query=user_query, finish_reason=finish_reason)
    if _summary_is_placeholder(answer):
        fb = _non_official_fallback(user_query, retrieved_docs)
        if fb:
            return fb, []
    # Build references section from citation markers in answer
    answer, refs = _build_references_section(answer, citation_map)
    return answer, refs


def generate_exam_tutoring_answer(
    user_query: str,
    retrieved_docs: List[RetrievedDoc],
) -> Tuple[str, List[Dict[str, Any]]]:
    """Generate a stricter, exam-focused answer from experience-first evidence."""
    settings = get_settings()
    if not settings.moark_api_key:
        raise RuntimeError(
            "请先设置 MOARK_API_KEY 或 DEEPSEEK_API_KEY（二选一），并设置 ENABLE_REAL_LLM=true；"
            "BASE_URL 可用 MOARK_BASE_URL 或 DEEPSEEK_BASE_URL。请确认 .env 位于项目根目录且已重启服务。"
        )

    context, citation_map = format_context_for_llm(retrieved_docs)
    today_cn = current_date_cn()
    prompt = (
        "你是人大保研笔试辅导助手，专门回答夏令营/预推免/推免笔试怎么准备。\n"
        f"当前日期：{today_cn}。回答中的{LQ}今年{RQ}{LQ}最新{RQ}必须以该日期为准；"
        "若证据不是当年官方通知，要明确写为经验归纳。\n"
        "资料行中的 model_label、model_stars、model_truth、model_usage 是逐条模型可信度判断，必须遵守。"
        "疑似推广或低可信资料仍可作为线索，但必须降级表述并提示核验。\n"
        "证据优先级：官方通知 > 小红书/知乎等经验库 > 联网网页线索。"
        "官方没有明说的内容，不得写成官方结论。\n"
        "\n"
        "输出必须结构化、短句、可直接阅读，严格使用以下标题：\n"
        "### 【一句话结论】\n"
        "用 1 句话回答用户最关心的问题。\n"
        "### 【可能考什么】\n"
        "分点列出经验库中提到的科目、题型、重点；每点都尽量标注引用编号。\n"
        "### 【怎么准备】\n"
        "给 4-6 条可执行准备动作，写清动作和目的。\n"
        "### 【需要核验】\n"
        "列出哪些内容官方未确认、哪些年份或方向可能变化，以及去哪里核验。\n"
        "不要在正文末尾自行添加参考文献列表；系统会单独生成参考文献。正文只保留 [1] 这类引用编号。\n"
        "\n"
        f"用户问题：{user_query}\n"
        f"资料（已按来源分组）：\n{context}\n"
    )

    client = OpenAI(
        base_url=settings.moark_base_url,
        api_key=settings.moark_api_key,
    )
    resp = client.chat.completions.create(
        model=settings.moark_model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=min(settings.llm_max_tokens, 8192),
        temperature=settings.llm_temperature,
        top_p=settings.llm_top_p,
        frequency_penalty=settings.llm_frequency_penalty,
        **({"extra_body": settings.llm_extra_body} if settings.llm_extra_body else {}),
    )
    content = (resp.choices[0].message.content or "").strip()
    if "【一句话结论】" not in content:
        content = "### 【一句话结论】\n" + content
    answer, refs = _build_references_section(content, citation_map)
    return answer, refs


def generate_mock_answer(
    user_query: str, question_type: QuestionType, retrieved_docs: List[RetrievedDoc]
) -> Tuple[str, List[Dict[str, Any]]]:
    ctx, citation_map = format_context_for_llm(retrieved_docs)
    raw = ensure_three_section_answer(
        (
            f"基于你的问题{LQ}{user_query}{RQ}，这是一个 mock 测试回答。\n"
            f"问题分类：{question_type}\n"
            "### 【总结回答】\n"
            "（演示模式：请启用真实大模型以生成完整分层回答。）\n"
            "### 【不确定性 / 冲突说明】\n"
            "mock 模式下未调用模型，以下为检索分组资料：\n"
            f"{ctx}\n"
        )
    )
    answer, refs = _build_references_section(raw, citation_map)
    return answer, refs
