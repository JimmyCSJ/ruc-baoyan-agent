"""长程规划：一次性表单 intake → LangGraph 状态 → 五段式报告 JSON / Markdown / PDF."""

from __future__ import annotations

import json
import os
import re
import html as html_lib
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from openai import OpenAI

from config import Settings, get_settings
from graph.state import RetrievedDoc
from tools.web_search import search_web_vertical


REQUIRED_KEYS = (
    "current_school",
    "grade_year",
    "college",
    "major",
    "gpa",
    "major_rank_percentile",
    "target_destination",
    "english_scores",
)

OPTIONAL_KEYS = (
    "research_and_competitions",
    "internships",
    "region_preference",
    "student_work_clubs",
    "career_path_3_5y",
    "expected_roles_or_industry",
    "admission_prep_stage",
    "main_concerns",
)


def long_plan_intake_template() -> Dict[str, Any]:
    """前端表单对应的空模板（JSON 字段名与表单一致）。"""
    req = {k: "" for k in REQUIRED_KEYS}
    opt = {k: "" for k in OPTIONAL_KEYS}
    return {"required": req, "optional": opt}


def long_plan_report_skeleton() -> Dict[str, Any]:
    """LLM 输出骨架（五段式）。"""
    return {
        "generated_at_iso": "",
        "target_destination_line": "",
        "direction_summary": "",
        "programs": [],
        "advantages": "",
        "weaknesses": "",
        "positioning_by_program": [],
        "timeline": [],
        "action_guidelines": [],
        "program_prep": [],
        "references_note": "请以中国人民大学各学院官网、研究生招生网及当年最新通知为准；经验内容仅供参考。",
    }


def validate_intake(body: Dict[str, Any]) -> Tuple[bool, List[str], Dict[str, Any]]:
    """校验必填项非空，返回 (ok, errors, normalized_flat_dict)。

    支持两种请求体：1) `{ \"required\": {...}, \"optional\": {...} }`；2) 扁平字典（前端表单 JSON）。
    """
    errors: List[str] = []
    flat: Dict[str, Any] = {}
    nested_required = isinstance(body.get("required"), dict)
    nested_optional = isinstance(body.get("optional"), dict)
    req_in = body["required"] if nested_required else body
    opt_src = body["optional"] if nested_optional else body

    for k in REQUIRED_KEYS:
        v = req_in.get(k) if isinstance(req_in, dict) else None
        s = str(v or "").strip()
        if not s:
            errors.append(f"缺少或为空：{k}")
        flat[k] = s

    for k in OPTIONAL_KEYS:
        v = opt_src.get(k) if isinstance(opt_src, dict) else None
        flat[k] = str(v or "").strip()

    return (len(errors) == 0, errors, flat)


def normalize_intake_for_graph(body: Dict[str, Any]) -> Dict[str, Any]:
    """组装为图模型使用的 intake（单层字典）。"""
    ok, _, flat = validate_intake(body)
    if not ok:
        raise ValueError("intake validation failed")
    return flat


def _long_plan_kb_context_max_chars(default: int = 50000) -> int:
    """长程规划喂给模型的知识库摘录预算。"""
    try:
        v = int(os.getenv("LONG_PLAN_KB_CONTEXT_MAX_CHARS", str(default)).strip())
    except ValueError:
        v = default
    return max(12000, min(120000, v))


def _long_plan_citation_doc_limit(default: int = 60) -> int:
    """长程规划引用映射最多保留多少条资料。"""
    try:
        v = int(os.getenv("LONG_PLAN_CITATION_DOC_LIMIT", str(default)).strip())
    except ValueError:
        v = default
    return max(24, min(120, v))


def build_kb_context_from_docs(docs: List[RetrievedDoc], limit_chars: int | None = None) -> str:
    if limit_chars is None:
        limit_chars = _long_plan_kb_context_max_chars()
    lines: List[str] = []
    n = 0
    for d in docs:
        title = str(d.get("title") or "")
        sg = str(d.get("source_group") or "")
        content = str(d.get("content") or "").strip()
        chunk = f"[{sg}] {title}\n{content}"
        if n + len(chunk) > limit_chars:
            break
        lines.append(chunk)
        n += len(chunk)
    return "\n\n---\n\n".join(lines)


def build_long_plan_retrieval_evidence_blocks(
    docs: List[RetrievedDoc],
    trace: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    """与快问快答「检索过程」对齐：给模型可信度分层提示；第二返回值用于 Markdown 附录。"""
    trace = trace or {}
    official_files = list(trace.get("official_files_read") or [])
    official_titles: List[str] = []
    official_count = 0
    public_count = 0
    web_count = 0
    for d in docs:
        sg = d.get("source_group")
        if sg == "official":
            official_count += 1
            t = str(d.get("title") or "").strip()
            if t and t not in official_titles:
                official_titles.append(t)
        elif sg == "experience":
            public_count += 1
        elif sg == "web":
            web_count += 1

    lines: List[str] = []
    lines.append(
        "【检索与证据概况】撰写「三、时间轴」「五、项目准备」时必须分层使用证据："
        "官方索引（official）可信度最高；公众经验（experience）为样本参考；联网（web）为未核实线索。"
    )
    lines.append(
        f"- 召回条数：合计 {len(docs)}｜官方索引 {official_count}｜公众经验 {public_count}｜联网 {web_count}"
    )
    if official_files:
        shown = official_files[:12]
        tail = (
            f"（其余 {len(official_files) - len(shown)} 份省略）"
            if len(official_files) > len(shown)
            else ""
        )
        lines.append("- 本次读取/关联的官方文件名：" + "；".join(shown) + tail)
    elif official_titles:
        shown = official_titles[:8]
        tail = f"（共 {len(official_titles)} 份）" if len(official_titles) > len(shown) else ""
        lines.append("- 命中官方材料标题：" + "；".join(f"「{x}」" for x in shown) + tail)
    else:
        lines.append("- 官方材料：本次未命中或仅有公众/联网来源（须在报告中写明信息缺口，勿虚构简章条款）")

    if web_count > 0:
        lines.append(f"- 联网通道：通过搜索引擎获取了 {web_count} 条最新参考信息")
    elif trace.get("web_access_used") is True:
        lines.append("- 联网通道：已通过浏览器代理抓取网页正文")
    elif trace.get("web_fallback_used"):
        wfail = str(trace.get("web_failure_reason") or "").strip()
        if wfail and "disabled" not in wfail.lower():
            lines.append(f"- 联网通道：主路径不可用，已使用搜索引擎兜底")
        else:
            lines.append("- 联网通道：通过搜索引擎查询公开网页")
    if web_count == 0 and not trace.get("web_access_used") and not trace.get("web_fallback_used"):
        lines.append("- 联网通道：本次未触发联网检索")

    prompt_block = "\n".join(lines).strip()
    md_block = "## 附录：检索与证据概况\n\n" + "\n".join(lines).strip()
    return prompt_block, md_block


def _strip_markdown_fences(text: str) -> str:
    t = (text or "").strip()
    if not t.startswith("```"):
        return t
    lines = t.split("\n")
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    while lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _balanced_json_slice(s: str) -> str | None:
    """从首个 `{` 起按括号深度截取完整 JSON 子串（避免贪婪正则吞掉无效尾部）。"""
    s = _strip_markdown_fences(s)
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return None


def _extract_json_object(text: str) -> Dict[str, Any]:
    """解析模型输出中的 JSON；优先括号平衡切片，其次整条贪婪匹配。"""
    raw = (text or "").strip()
    if not raw:
        raise ValueError("empty model output")

    candidates: List[str] = []
    bal = _balanced_json_slice(raw)
    if bal:
        candidates.append(bal)
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        g = m.group(0)
        if g not in candidates:
            candidates.append(g)

    last_err: Exception | None = None
    for cand in candidates:
        try:
            return json.loads(cand)
        except json.JSONDecodeError as e:
            last_err = e
            continue
    raise ValueError(f"invalid json in model output: {last_err}")


def _llm_json_chat(
    system: str,
    user: str,
    temperature: float = 0.28,
    *,
    max_tokens: int | None = None,
    json_mode: bool = False,
) -> str:
    settings = get_settings()
    if not settings.moark_api_key or not settings.enable_real_llm:
        raise RuntimeError("LLM unavailable")

    cap = max_tokens if max_tokens is not None else settings.llm_max_tokens
    cap = max(256, min(8192, int(cap)))

    client = _long_plan_openai_client(settings)
    kwargs: Dict[str, Any] = {
        "model": settings.moark_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": cap,
        "temperature": temperature,
        "top_p": settings.llm_top_p,
        "frequency_penalty": settings.llm_frequency_penalty,
        "extra_body": {"top_k": settings.llm_top_k, "failover_enabled": settings.failover_enabled},
    }
    if json_mode or os.getenv("LONG_PLAN_RESPONSE_JSON", "").strip().lower() in ("1", "true", "yes", "on"):
        kwargs["response_format"] = {"type": "json_object"}

    if kwargs.get("response_format"):
        try:
            resp = client.chat.completions.create(**kwargs)
        except Exception:
            kwargs.pop("response_format", None)
            resp = client.chat.completions.create(**kwargs)
    else:
        resp = client.chat.completions.create(**kwargs)
    return (resp.choices[0].message.content or "").strip()


def _web_snippets(intake: Dict[str, Any], use_web: bool) -> str:
    if not use_web:
        return ""
    if os.getenv("LONG_PLAN_SKIP_WEB", "").strip().lower() in ("1", "true", "yes", "on"):
        return ""
    target = str(intake.get("target_destination") or "")
    major = str(intake.get("major") or "")
    q = f"中国人民大学 保研 {target} {major}"[:400]
    timeout_s = float(os.getenv("LONG_PLAN_WEB_TIMEOUT_S", "28"))
    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(search_web_vertical, q, lite=True)
            docs = fut.result(timeout=timeout_s)[:8]
    except FuturesTimeout:
        return ""
    except Exception:
        return ""
    if not docs:
        return ""
    return "\n".join(f"- [{d['source']}] {d['title']}: {d['content'][:450]}" for d in docs)


def _web_snippets_per_program(programs: list, timeout_s: float = 25) -> str:
    """For each program in Part 1, do a targeted zhihu/xiaohongshu search for experience posts."""
    if not programs:
        return ""
    from tools.web_search import search_web_vertical

    all_snippets: list[str] = []
    seen: set[str] = set()
    for prog in programs[:6]:  # max 6 programs to avoid overwhelming
        if not isinstance(prog, dict):
            continue
        pname = (prog.get("program_name") or "").strip()
        college = (prog.get("college") or "").strip()
        if not pname:
            continue
        # Build targeted query
        q = f'site:zhihu.com OR site:xiaohongshu.com "中国人民大学" "{pname}" 保研 (经验 OR 面试 OR 考核)'
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(search_web_vertical, q, lite=True)
                docs = fut.result(timeout=timeout_s)[:3]
        except (FuturesTimeout, Exception):
            docs = []
        for d in docs:
            title = (d.get("title") or "").strip()
            content = (d.get("content") or "").strip()[:400]
            dedup_key = title or content[:60]
            if dedup_key not in seen:
                seen.add(dedup_key)
                all_snippets.append(
                    f"[{college}·{pname}] {title}: {content}"
                )
    if not all_snippets:
        return ""
    return "【以下为针对各项目的定向网搜经验帖（知乎/小红书）】\n" + "\n".join(
        f"- {s}" for s in all_snippets[:20]
    )


def _long_plan_llm_read_timeout_s() -> float:
    """长 JSON 生成耗时长；默认 900s。可用 LONG_PLAN_LLM_TIMEOUT_S 覆盖（60～1800）。"""
    try:
        v = float(os.getenv("LONG_PLAN_LLM_TIMEOUT_S", "900").strip())
    except ValueError:
        v = 900.0
    return max(60.0, min(1800.0, v))


def _long_plan_openai_client(settings: Settings) -> OpenAI:
    """独立客户端：放宽读超时、关闭 SDK 重试；httpx 不信任环境代理，避免死掉的 HTTP_PROXY 劫持 LLM 请求。"""
    read_s = _long_plan_llm_read_timeout_s()
    timeout = httpx.Timeout(connect=45.0, read=read_s, write=120.0, pool=10.0)
    # httpx 0.28+：用 proxy=None + trust_env=False，等价于「不走系统/环境变量里的代理」
    custom_http_client = httpx.Client(proxy=None, trust_env=False, timeout=timeout)
    return OpenAI(
        base_url=settings.moark_base_url,
        api_key=settings.moark_api_key,
        http_client=custom_http_client,
        max_retries=0,
    )


def _long_plan_part_max_tokens() -> int:
    """分块生成时每段输出上限；默认 8192。环境变量 LONG_PLAN_PART_MAX_TOKENS。"""
    try:
        v = int(os.getenv("LONG_PLAN_PART_MAX_TOKENS", "8192").strip())
    except ValueError:
        v = 8192
    return max(512, min(8192, v))


def _part_output_ceiling_tokens() -> int:
    """分段单次输出的硬顶；默认 8192。"""
    try:
        v = int(os.getenv("LONG_PLAN_PART_OUTPUT_CEILING", "8192").strip())
    except ValueError:
        v = 8192
    return max(512, min(8192, v))


def _part_skeleton(part: int) -> Dict[str, Any]:
    if part == 1:
        return {"direction_summary": "", "programs": []}
    if part == 2:
        return {"advantages": "", "weaknesses": "", "positioning_by_program": []}
    if part == 3:
        return {"timeline": []}
    if part == 4:
        return {"action_guidelines": []}
    if part == 5:
        return {"program_prep": []}
    raise ValueError(f"invalid part {part}")


def _fallback_slice_for_part(part: int, intake: Dict[str, Any], generated_at_iso: str) -> Dict[str, Any]:
    fb = _fallback_report(intake, generated_at_iso)
    if part == 1:
        return {"direction_summary": fb["direction_summary"], "programs": fb["programs"]}
    if part == 2:
        return {
            "advantages": fb["advantages"],
            "weaknesses": fb["weaknesses"],
            "positioning_by_program": fb["positioning_by_program"],
        }
    if part == 3:
        return {"timeline": fb["timeline"]}
    if part == 4:
        return {"action_guidelines": fb["action_guidelines"]}
    if part == 5:
        return {"program_prep": fb["program_prep"]}
    raise ValueError(f"invalid part {part}")


def _filter_part_keys(part: int, data: Dict[str, Any]) -> Dict[str, Any]:
    sk = _part_skeleton(part)
    out: Dict[str, Any] = {}
    for k in sk:
        if k in data:
            out[k] = data[k]
    return out


def _part_system_prompt(part: int, sk: Dict[str, Any], kb_has: bool) -> str:
    base = (
        "你是中国人民大学保研规划顾问。只输出一个合法 JSON 对象，键名必须与骨架完全一致，禁止增删键、禁止 Markdown、禁止代码围栏。\n"
        f"骨架：\n{json.dumps(sk, ensure_ascii=False)}\n"
        f"知识库摘录是否非空：{'是' if kb_has else '否'}。勿虚构官方简章条款；考研与推免须区分表述。\n"
        "引用标注规则（强制）：在所有文字类字段（direction_summary/advantages/weaknesses/rationale/core_tasks/"
        "action_guidelines/exam_focus/preferences_from_alumni/official_pointers 等）中，"
        "每当你引用检索资料中的具体事实或数据，必须用 [N] 标注来源编号。"
        "编号对应上文「检索与证据概况」中「引用编号映射」表格的 [N]。"
        "禁止使用描述性词语（如「根据官方文件」「有经验帖提到」）代替 [N] 编号标注。\n"
    )
    extras = {
        1: (
            "本段对应报告「一、目标院校可选择项目」。\n"
            "你必须输出一个 programs 列表，每一项包含四个字段：\n"
            '  {"college":"学院全称","program_name":"专业全称","degree_type_note":"专业硕士/学术硕士/直博","why_relevant":"为什么适合该用户"}\n'
            '  JSON 示例（务必模仿）：\n'
            '  {"programs":[{"college":"财政金融学院","program_name":"金融（证券管理与投资方向）","degree_type_note":"专业硕士",'
            '"why_relevant":"本院王牌专硕，与用户金融背景高度匹配"}]}\n'
            "  program_name 必须填写具体的专业方向全称，绝对不能留空、不能填「需核对当年简章」、不能填文件名。\n"
            "  why_relevant 写1-2句该专业为什么适合此用户（结合用户背景和目标方向）。\n"
            "必须全面覆盖中国人民大学所有与用户目标相关的学院和项目，至少覆盖：\n"
            "财政金融学院、经济学院、应用经济学院、智慧治理学院、国际学院(苏州)、"
            "统计与大数据研究院、统计学院、商学院、深圳研究院等有经济金融相关保研项目的学院。\n"
            "只列出知识库中实际检索到的、有真实招生文件的学院和项目，不要凭空编造。\n"
        ),
        2: (
            "本段对应「二、核心诊断与定位」。须结合用户表单事实；"
            "positioning_by_program 须与第一段 programs 一一对应：每条对象的 program_key_or_name 必须写入与对应 program_name 相同或可唯一识别的具体专业名，"
            "严禁留空、严禁仅写「示例」「项目」等泛称（tier 仅限 冲、稳、保）。\n"
        ),
        3: (
            "本段对应「三、关键时间轴」。你必须严格使用以下 5 个固定阶段，不得自行发明时间节点：\n"
            "阶段一 bucket='5月-6月中旬' title='夏令营筹备期' "
            "deadline_or_window='即日起至6月15日左右，各学院陆续发布夏令营通知'\n"
            "阶段二 bucket='6月下旬-7月上旬' title='夏令营冲刺与参营' "
            "deadline_or_window='6月20日至7月15日，各学院集中举办夏令营考核'\n"
            "阶段三 bucket='8月-9月中旬' title='预推免与候补' "
            "deadline_or_window='8月下旬至9月中旬，未获满意offer则参加预推免批次'\n"
            "阶段四 bucket='9月中下旬' title='本校推免资格认定' "
            "deadline_or_window='9月15日-25日左右，学院公布推免综合排名与资格名单'\n"
            "阶段五 bucket='9月底-10月初' title='国家推免系统填报与确认' "
            "deadline_or_window='9月28日-10月10日，登录yz.chsi.com.cn/tm填报志愿并确认录取'\n"
            "每个阶段的 core_tasks 需结合用户背景（冲/稳/保定位）填写具体的可执行任务（每条任务含动作+目标），"
            "严禁笼统空话如「准备材料」而不写具体准备什么。timeline 必须恰好 5 条，对应上述 5 个阶段。\n"
        ),
        4: "本段对应「四、核心行动指南」。action_guidelines 为 5～10 条可执行字符串。\n",
        5: (
            "本段对应「五、项目准备建议」。若第一段 programs 非空，则 program_prep 条数必须与 programs 相同，绝不能返回空列表 []。\n"
            "每条对象必须严格包含以下 4 个字段：\n"
            '  {"program_name":"金融（证券管理与投资方向）","exam_focus":"笔试重点考察431金融学综合（含公司理财、投资学），面试含英文面与专业面","preferences_from_alumni":"往届学长学姐反馈：面试重视科研与实习经历的关联性","official_pointers":"参见财政金融学院2026年招生简章"}\n'
            "- program_name: 必须与第一段对应项目名称一致\n"
            "- exam_focus: 该项目的笔试/面试考察重点（基于知识库检索的官方文件）\n"
            "- preferences_from_alumni: 往届经验偏好和备考建议（基于经验帖或网搜面经）\n"
            "- official_pointers: 对应官方政策文件线索\n"
            "内容要求：请简明扼要地提取核心信息。如果知识库和网络检索中确实没有对应项目的具体信息，"
            "请直接填写「暂无公开经验信息，请以当年学院官方通知为准」。\n"
            "绝对禁止：为了凑字数而进行无意义的词汇联想、罗列同义词、重复废话或输出空泛的长篇描述。每个字段的输出必须极为精炼。\n"
        ),
    }
    return base + extras.get(part, "")


def generate_long_plan_section(
    part: int,
    intake: Dict[str, Any],
    kb_context: str,
    retrieval_evidence: str,
    web: str,
    generated_at_iso: str,
    prior_context: str,
) -> Tuple[Dict[str, Any], str | None]:
    """生成五段之一；成功返回 (dict, None)，失败返回 (fallback_slice, error_reason)。"""
    intake = intake or {}
    sk = _part_skeleton(part)
    kb_has = bool((kb_context or "").strip()) and (kb_context or "").strip() != "（无）"
    settings = get_settings()
    if not settings.moark_api_key or not settings.enable_real_llm:
        return _fallback_slice_for_part(part, intake, generated_at_iso), "llm_disabled_or_no_key"

    head = (
        f"规划生成时间（ISO）：{generated_at_iso}\n"
        f"用户表单：{json.dumps(intake, ensure_ascii=False)}\n"
    )
    if (retrieval_evidence or "").strip():
        head += retrieval_evidence.strip() + "\n\n"
    if prior_context.strip():
        head += "【前文已生成片段（保持逻辑连贯，勿改写其中事实性列表结构）】\n" + prior_context.strip() + "\n\n"
    user = (
        head
        + f"知识库摘录：\n{kb_context or '（无）'}\n\n"
        + f"网络摘要（未验证）：\n{web or '（无）'}\n"
    )

    # 勿与全局 LLM_MAX_TOKENS 取 max：全局设很大时会抵消「分段减负」；只用分段预算与硬顶的较小值。
    cap = min(_long_plan_part_max_tokens(), _part_output_ceiling_tokens())
    cap = max(256, cap)
    use_json = os.getenv("LONG_PLAN_PART_RESPONSE_JSON", "true").strip().lower() in ("1", "true", "yes", "on")
    last_err: Exception | None = None
    raw = ""

    for attempt in range(2):
        try:
            sys_m = _part_system_prompt(part, sk, kb_has)
            if attempt == 1:
                sys_m = (
                    "你是保研顾问。只输出合法 JSON，键必须与骨架完全一致，禁止 Markdown、禁止代码围栏。\n"
                    f"骨架：\n{json.dumps(sk, ensure_ascii=False)}"
                )
                user = user + "\n\n【重试】上一输出非法或过长，请输出更短、合法 JSON。"
            raw = _llm_json_chat(sys_m, user, temperature=0.2 if attempt == 0 else 0.1, max_tokens=cap, json_mode=use_json)
            data = _extract_json_object(raw)
            data = _filter_part_keys(part, data)
            return data, None
        except Exception as exc:
            last_err = exc
            continue

    fb = _fallback_slice_for_part(part, intake, generated_at_iso)
    reason = f"{type(last_err).__name__}:{last_err}" if last_err else "unknown"
    return fb, reason


def assemble_long_plan_report(
    part1: Dict[str, Any],
    part2: Dict[str, Any],
    part3: Dict[str, Any],
    part4: Dict[str, Any],
    part5: Dict[str, Any],
    intake: Dict[str, Any],
    generated_at_iso: str,
    retrieval_evidence_md: str,
    part_errors: Dict[str, str],
) -> Dict[str, Any]:
    base = long_plan_report_skeleton()
    merged: Dict[str, Any] = {
        **base,
        **part1,
        **part2,
        **part3,
        **part4,
        **part5,
    }
    merged["generated_at_iso"] = generated_at_iso
    merged["target_destination_line"] = str(intake.get("target_destination") or "（未填写）")
    merged["references_note"] = base["references_note"]
    if retrieval_evidence_md.strip():
        merged["_retrieval_evidence_md"] = retrieval_evidence_md.strip()
    if part_errors:
        merged["_generation"] = "partial"
        merged["_fallback_reason"] = "; ".join(f"part{k}:{v}" for k, v in sorted(part_errors.items()))
    else:
        merged["_generation"] = "llm"
        merged["_fallback_reason"] = ""
    return merged


_LOW_VALUE_PATTERNS = (
    "暂无公开经验信息",
    "暂无针对此项目",
    "暂无。",
    "暂无",
    "无公开信息",
    "没有检索到",
    "未检索到",
    "请自行查询",
    "—",
    "-",
)


def _is_low_value_text(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    compact = re.sub(r"\s+", "", text)
    if compact in ("—", "-", "无", "暂无", "无。"):
        return True
    if len(compact) <= 2:
        return True
    return any(p in text for p in _LOW_VALUE_PATTERNS)


def _clean_report_text(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"([。；])\s*(\d+[.、])", r"\1\n\2", text)
    return "" if _is_low_value_text(text) else text


def _doc_text(doc: RetrievedDoc) -> str:
    return " ".join(
        str(doc.get(k) or "")
        for k in ("title", "content", "source_group", "source")
    )


def _dedupe_docs(docs: List[RetrievedDoc]) -> List[RetrievedDoc]:
    out: List[RetrievedDoc] = []
    seen: set[str] = set()
    for d in docs:
        key = "|".join(
            [
                str(d.get("source_group") or ""),
                str(d.get("title") or "")[:120],
                str(d.get("content") or "")[:180],
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out


def _target_terms_from_intake(intake: Dict[str, Any]) -> List[str]:
    raw = " ".join(
        str(intake.get(k) or "")
        for k in ("target_destination", "target_school", "target_college", "major", "college")
    )
    terms = ["中国人民大学", "保研", "推免", "夏令营", "预推免"]
    if "财政金融" in raw or "财金" in raw:
        terms += ["财政金融学院", "财金", "金融专硕", "证券投资", "证投", "投资学", "商业银行", "笔试", "面试"]
    if "信息" in raw or "人工智能" in raw or "电子信息" in raw:
        terms += ["信息学院", "电子信息", "人工智能", "机试", "编程"]
    if "商学院" in raw or "会计" in raw:
        terms += ["商学院", "会计", "面试", "笔试"]
    if "法学院" in raw or "法律" in raw:
        terms += ["法学院", "法律硕士", "专业面试"]
    return list(dict.fromkeys(terms))


def _evidence_snippets(docs: List[RetrievedDoc], terms: List[str], limit: int = 5) -> List[str]:
    scored: List[Tuple[int, str]] = []
    for d in docs:
        text = _doc_text(d)
        score = sum(1 for t in terms if t and t in text)
        if score <= 0:
            continue
        title = str(d.get("title") or "资料").strip()
        content = re.sub(r"\s+", " ", str(d.get("content") or "")).strip()
        if not content:
            continue
        scored.append((score, f"{title}：{content[:180]}"))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in scored[:limit]]


def _program_name_text(program: Dict[str, Any]) -> str:
    return " ".join(
        str(program.get(k) or "") for k in ("college", "program_name", "degree_type_note", "why_relevant")
    )


def _guess_position_tier(program: Dict[str, Any], intake: Dict[str, Any]) -> str:
    p = _program_name_text(program)
    target = str(intake.get("target_destination") or "")
    rank = str(intake.get("major_rank_percentile") or "")
    if ("财政金融" in p or "财金" in p) and ("金融" in p or "证券" in p):
        return "冲" if "1/" not in rank and "0." not in rank else "稳"
    if any(x in p for x in ("经济学院", "商学院", "金融科技", "数字经济", "智慧治理")):
        return "稳"
    if target and any(x in p for x in ("税务", "保险", "应用经济", "国际商务", "碳经济")):
        return "保"
    return "稳"


def _repair_positioning(
    report: Dict[str, Any],
    intake: Dict[str, Any],
    docs: List[RetrievedDoc],
    issues: List[str],
) -> None:
    programs = [p for p in (report.get("programs") or []) if isinstance(p, dict)]
    existing: Dict[str, Dict[str, Any]] = {}
    for item in report.get("positioning_by_program") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("program_key_or_name") or item.get("program_name") or "").strip()
        if not name:
            continue
        existing[name] = item

    repaired: List[Dict[str, Any]] = []
    target_terms = _target_terms_from_intake(intake)
    snippets = _evidence_snippets(docs, target_terms, limit=3)
    evidence_hint = "；".join(snippets[:2])
    for p in programs:
        pname = str(p.get("program_name") or "").strip()
        if not pname:
            continue
        item = existing.get(pname) or next(
            (v for k, v in existing.items() if k and (k in pname or pname in k)), {}
        )
        tier = str(item.get("tier") or "").strip()
        rationale = _clean_report_text(item.get("rationale"))
        if tier not in ("冲", "稳", "保"):
            tier = _guess_position_tier(p, intake)
        if not rationale:
            college = str(p.get("college") or "").strip()
            why = _clean_report_text(p.get("why_relevant"))
            rationale = (
                f"{college}{pname}与目标方向匹配度较高；结合你的排名、证券研究/咨询经历、数模和计算机辅修背景，"
                f"建议按“{tier}”档准备。"
            )
            if why:
                rationale += f" 主要依据：{why}"
            elif evidence_hint:
                rationale += f" 可参考线索：{evidence_hint}"
            issues.append(f"已补全「{pname}」的定位评级。")
        repaired.append({"program_key_or_name": pname, "tier": tier, "rationale": rationale})

    report["positioning_by_program"] = repaired


def _repair_program_prep(
    report: Dict[str, Any],
    intake: Dict[str, Any],
    docs: List[RetrievedDoc],
    issues: List[str],
) -> None:
    programs = [p for p in (report.get("programs") or []) if isinstance(p, dict)]
    existing: Dict[str, Dict[str, Any]] = {}
    for item in report.get("program_prep") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("program_name") or "").strip()
        if name:
            existing[name] = item

    target_terms = _target_terms_from_intake(intake)
    global_snippets = _evidence_snippets(docs, target_terms, limit=6)
    repaired: List[Dict[str, Any]] = []
    for p in programs:
        pname = str(p.get("program_name") or "").strip()
        if not pname:
            continue
        item = existing.get(pname) or next(
            (v for k, v in existing.items() if k and (k in pname or pname in k)), {}
        )
        p_terms = target_terms + [pname, str(p.get("college") or "")]
        snippets = _evidence_snippets(docs, p_terms, limit=4) or global_snippets[:3]
        is_main_target = any(x in _program_name_text(p) for x in ("财政金融", "金融", "证券", "证投"))
        exam_focus = _clean_report_text(item.get("exam_focus"))
        alumni = _clean_report_text(item.get("preferences_from_alumni"))
        official = _clean_report_text(item.get("official_pointers"))

        if not exam_focus and snippets:
            exam_focus = (
                "优先按数学基础、投资学、商业银行经营管理、金融市场与证券估值准备；"
                "若当年通知另有要求，以学院正式通知为准。"
                if is_main_target
                else "围绕项目对应专业基础、英文表达和简历经历深挖准备；具体科目以当年通知为准。"
            )
        if not alumni and snippets:
            alumni = "经验线索显示，可重点准备笔面经中反复出现的专业课、英语问答、简历深挖和项目匹配叙事；资料可信度按经验线索处理。"
        if not official and snippets:
            official = "以中国人民大学研究生招生网、目标学院夏令营/预推免通知和当年专业目录为准；经验信息只作备考线索。"

        strategy = ""
        if is_main_target:
            strategy = (
                "把证券研究所机械组、BCG 项目、数模 CUDA 优化和经济学成绩统一包装为"
                "“产业研究 + 金融分析 + 数据能力”的证投方向叙事；提前准备投资学、商业银行、数学和英文自我介绍。"
            )
        elif snippets:
            strategy = "用你的高排名、研究/咨询经历和数理能力证明可迁移性，同时准备该项目对应专业基础问题。"

        if exam_focus or alumni or official or strategy:
            repaired.append(
                {
                    "program_name": pname,
                    "exam_focus": exam_focus,
                    "preferences_from_alumni": alumni,
                    "official_pointers": official,
                    "applicant_strategy": strategy,
                    "evidence_note": "官方文件优先；经验帖为备考线索，不作录取承诺。",
                }
            )
        else:
            issues.append(f"隐藏「{pname}」项目准备建议：未找到足够可用信息。")

    report["program_prep"] = repaired


def _llm_review_and_repair_report(
    report: Dict[str, Any],
    intake: Dict[str, Any],
    docs: List[RetrievedDoc],
) -> Dict[str, Any]:
    """用额外一次模型评审补写弱项；失败则保持确定性修复结果。"""
    if os.getenv("LONG_PLAN_REVIEW_LLM", "true").strip().lower() not in ("1", "true", "yes", "on"):
        return report
    settings = get_settings()
    if not settings.moark_api_key or not settings.enable_real_llm:
        return report

    terms = _target_terms_from_intake(intake)
    snippets = _evidence_snippets(docs, terms, limit=10)
    if not snippets:
        return report

    schema = {
        "direction_summary": report.get("direction_summary", ""),
        "advantages": report.get("advantages", ""),
        "weaknesses": report.get("weaknesses", ""),
        "positioning_by_program": report.get("positioning_by_program", []),
        "action_guidelines": report.get("action_guidelines", []),
        "program_prep": report.get("program_prep", []),
    }
    sys_m = (
        "你是保研规划报告质检员。请基于用户画像和证据线索，补全报告弱项，只输出合法 JSON。"
        "要求：不要输出空项、横杠、暂无；如果某字段确实无信息，直接从 JSON 中保留为空列表或空字符串，前端会隐藏。"
        "不得虚构官方政策；经验帖只能作为备考线索。"
    )
    user = (
        f"用户画像：{json.dumps(intake, ensure_ascii=False)}\n\n"
        f"当前报告片段：{json.dumps(schema, ensure_ascii=False)}\n\n"
        "可用证据线索：\n" + "\n".join(f"- {s}" for s in snippets) + "\n\n"
        "请重点补全：冲/稳/保定位理由、项目准备建议、本人应对策略、行动指南。"
    )
    try:
        raw = _llm_json_chat(sys_m, user, temperature=0.15, max_tokens=4096, json_mode=True)
        data = _extract_json_object(raw)
    except Exception:
        return report

    out = dict(report)
    for key in (
        "direction_summary",
        "advantages",
        "weaknesses",
        "positioning_by_program",
        "action_guidelines",
        "program_prep",
    ):
        if key in data:
            out[key] = data[key]
    review = dict(out.get("_quality_review") or {})
    fixed = list(review.get("issues_fixed") or [])
    fixed.append("已执行一次模型质检补写。")
    review["issues_fixed"] = fixed
    review["llm_review"] = "applied"
    out["_quality_review"] = review
    return out


def review_and_repair_long_plan_report(
    report: Dict[str, Any],
    intake: Dict[str, Any],
    docs: List[RetrievedDoc],
) -> Dict[str, Any]:
    """整份报告质检：补全关键空缺，隐藏低价值内容，避免把草稿交给用户。"""
    report = dict(report or {})
    docs = _dedupe_docs(docs or [])
    issues: List[str] = []

    programs = []
    for p in report.get("programs") or []:
        if not isinstance(p, dict):
            continue
        if _is_low_value_text(p.get("program_name")):
            continue
        p["why_relevant"] = _clean_report_text(p.get("why_relevant"))
        programs.append(p)
    report["programs"] = programs

    for key in ("direction_summary", "advantages", "weaknesses"):
        cleaned = _clean_report_text(report.get(key))
        if cleaned:
            report[key] = cleaned
        else:
            report.pop(key, None)
            issues.append(f"隐藏低质量字段：{key}")

    _repair_positioning(report, intake, docs, issues)
    _repair_program_prep(report, intake, docs, issues)

    # 时间线与行动指南保留有内容的项；空项不展示。
    timeline = []
    for item in report.get("timeline") or []:
        if not isinstance(item, dict):
            continue
        tasks = item.get("core_tasks")
        if _is_low_value_text(tasks):
            continue
        timeline.append(item)
    report["timeline"] = timeline

    action_guidelines = []
    for x in report.get("action_guidelines") or []:
        cleaned = _clean_report_text(x)
        if cleaned:
            action_guidelines.append(cleaned)
    report["action_guidelines"] = action_guidelines

    report["_quality_review"] = {
        "status": "reviewed",
        "issues_fixed": issues,
        "hidden_empty_content": True,
    }
    report = _llm_review_and_repair_report(report, intake, docs)
    # 模型补写后再跑一遍确定性清洗，避免重新引入空白占位。
    for key in ("direction_summary", "advantages", "weaknesses"):
        cleaned = _clean_report_text(report.get(key))
        if cleaned:
            report[key] = cleaned
        else:
            report.pop(key, None)
    _repair_positioning(report, intake, docs, issues)
    _repair_program_prep(report, intake, docs, issues)
    action_guidelines = []
    for x in report.get("action_guidelines") or []:
        cleaned = _clean_report_text(x)
        if cleaned:
            action_guidelines.append(cleaned)
    report["action_guidelines"] = action_guidelines
    review = dict(report.get("_quality_review") or {})
    review["status"] = "reviewed"
    review["issues_fixed"] = list(dict.fromkeys(issues + list(review.get("issues_fixed") or [])))
    review["hidden_empty_content"] = True
    report["_quality_review"] = review
    return report


def _prior_context_for_part(state: Dict[str, Any], part: int) -> str:
    """生成第 part 段时，串联此前已完成的片段（控制长度）。"""
    chunks: List[str] = []
    if part >= 2 and state.get("part1_target"):
        chunks.append("【段一·目标院校】\n" + json.dumps(state["part1_target"], ensure_ascii=False)[:10000])
    if part >= 3 and state.get("part2_diagnosis"):
        chunks.append("【段二·诊断】\n" + json.dumps(state["part2_diagnosis"], ensure_ascii=False)[:8000])
    if part >= 4 and state.get("part3_timeline"):
        chunks.append("【段三·时间轴】\n" + json.dumps(state["part3_timeline"], ensure_ascii=False)[:8000])
    if part >= 5 and state.get("part4_action"):
        chunks.append("【段四·行动】\n" + json.dumps(state["part4_action"], ensure_ascii=False)[:6000])
    return "\n\n".join(chunks)


def _fallback_report(intake: Dict[str, Any], generated_at_iso: str) -> Dict[str, Any]:
    out = long_plan_report_skeleton()
    out["_generation"] = "fallback"
    out["_fallback_reason"] = "template"
    out["generated_at_iso"] = generated_at_iso
    out["target_destination_line"] = str(intake.get("target_destination") or "（未填写）")
    out["direction_summary"] = (
        f"基于当前信息的占位规划：{intake.get('major', '')} / {intake.get('college', '')}。"
        "本次未能生成完整定制内容（见页首说明）；以下为模板占位，不代表模型已成功解析。"
    )
    out["programs"] = [
        {
            "college": "财政金融学院",
            "program_name": "金融（示例）",
            "degree_type_note": "请以当年简章为准",
            "why_relevant": "与用户方向匹配时请替换为真实项目列表",
        }
    ]
    out["advantages"] = f"院校背景：{intake.get('current_school','')}；排名区间：{intake.get('major_rank_percentile','')}。"
    out["weaknesses"] = str(intake.get("main_concerns") or "（请补充短板）")
    out["positioning_by_program"] = [
        {"program_key_or_name": "示例项目", "tier": "稳", "rationale": "占位；启用模型后按表单与项目逐个生成。"}
    ]
    out["timeline"] = [
        {
            "bucket": "短期",
            "deadline_or_window": "最近 4 周",
            "title": "材料与英语核对",
            "core_tasks": "核对成绩单、英语证明；列出目标学院清单。",
        }
    ]
    out["action_guidelines"] = [
        "整理一页纸简历（量化科研/竞赛/实习）。",
        "按学院分别建立文件夹扫描证明材料为 PDF。",
        "联系推荐人沟通时间节点。",
    ]
    out["program_prep"] = [
        {
            "program_name": "示例项目",
            "exam_focus": "笔试面试请以当年通知为准。",
            "preferences_from_alumni": "参考公众经验库与学长学姐复盘。",
            "official_pointers": "优先查阅学院官网硕士招生/推免专栏。",
        }
    ]
    return out


def report_json_to_markdown(report: Dict[str, Any]) -> str:
    """将报告 JSON 转为可预览的 Markdown（与用户要求的「一～五」结构对齐）。"""
    gen_mode = str(report.get("_generation") or "")
    fb_reason = str(report.get("_fallback_reason") or "")
    pre = ""
    if gen_mode == "partial":
        net_hint = ""
        if any(
            x in fb_reason
            for x in ("APIConnectionError", "Connection error", "502", "503", "proxy", "Proxy")
        ):
            net_hint = (
                " 若为连接类错误，请检查本机/服务器能否直连 **`MOARK_BASE_URL`**（代理故障、`HTTP_PROXY`/`HTTPS_PROXY`、"
                "或网关 `502` 都会导致各段失败）；修复网络后重新生成。"
            )
        pre = (
            f"> 分块生成完成，但 **部分段落失败** 已用占位或简略结果补齐。详情：`{fb_reason}`。"
            f"{net_hint}\n\n"
        )
    elif gen_mode == "fallback":
        if fb_reason == "llm_disabled_or_no_key":
            hint = (
                "当前为占位/离线报告：请配置 `MOARK_API_KEY` 或 `DEEPSEEK_API_KEY`（及对应 `BASE_URL`），"
                "并设置 **`ENABLE_REAL_LLM=true`** 后重试。"
            )
        elif any(
            x in fb_reason
            for x in ("APIConnectionError", "Connection error", "ConnectError", "502", "503", "proxy")
        ):
            hint = (
                "**无法连接到大模型 API**（非应用逻辑错误）。请检查：`MOARK_BASE_URL`/`DEEPSEEK_BASE_URL` 是否可达；"
                "系统代理（Clash/V2Ray 等）是否正常；必要时配置正确的 **`HTTP_PROXY`/`HTTPS_PROXY`** 或暂时关闭代理。"
                "附录中 **`proxy_http_502`** 表示联网抓取通道异常，与模型连接问题可能同源。"
            )
            if fb_reason and fb_reason != "template":
                hint += f" 详情：`{fb_reason}`。"
        elif any(
            x in fb_reason for x in ("JSONDecodeError", "invalid json", "Expecting", "delimiter")
        ):
            hint = (
                "某段模型输出无法解析为合法 JSON（截断或非 JSON 夹杂）。可调小单段体积："
                "**`LONG_PLAN_PART_MAX_TOKENS`**（默认 8192）、**`LONG_PLAN_PART_OUTPUT_CEILING`**（默认 8192）；"
                "或尝试 **`LONG_PLAN_PART_RESPONSE_JSON=true`**（网关需支持 `response_format`）。"
            )
            if fb_reason and fb_reason != "template":
                hint += f" 详情：`{fb_reason}`。"
        elif any(
            x in fb_reason for x in ("APITimeoutError", "ReadTimeout", "timed out", "Timeout")
        ):
            hint = (
                "调用模型时 **HTTP 读超时**。请在 `.env` 增大 **`LONG_PLAN_LLM_TIMEOUT_S`**（默认 900 秒），"
                "并确认反向代理 **`proxy_read_timeout`** 不小于该值。"
            )
            if fb_reason and fb_reason != "template":
                hint += f" 详情：`{fb_reason}`。"
        else:
            hint = (
                "当前为占位/离线报告。常见原因：**网络不可达 API**、**读超时** 或 **JSON 解析失败**。"
                "建议检查代理与 `LONG_PLAN_LLM_TIMEOUT_S`，分段参数：`LONG_PLAN_PART_MAX_TOKENS`、`LONG_PLAN_PART_OUTPUT_CEILING`。"
            )
            if fb_reason and fb_reason != "template":
                hint += f" 失败原因：`{fb_reason}`。"
        pre = f"> {hint}\n\n"

    gen = report.get("generated_at_iso") or ""
    try:
        if gen:
            # Handle both UTC+8 offset (+08:00) and old Z-suffix formats
            clean = gen.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean)
            # Force to Beijing time if it has no tz info or needs conversion
            from datetime import timezone as _tz, timedelta as _td
            beijing = _tz(_td(hours=8))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=beijing)
            else:
                dt = dt.astimezone(beijing)
            gen_cn = dt.strftime("%Y年%m月%d日 %H:%M")
        else:
            gen_cn = gen
    except Exception:
        gen_cn = gen

    target = report.get("target_destination_line") or ""
    lines: List[str] = []
    if pre:
        lines.append(pre)
    lines.append(f"规划生成时间：{gen_cn}　　目标去向：{target}\n")
    lines.append("\n## 一、目标院校可选择项目\n")
    direction_summary = _clean_report_text(report.get("direction_summary"))
    if direction_summary:
        lines.append(direction_summary + "\n")
    programs = report.get("programs") or []
    if isinstance(programs, list):
        for i, p in enumerate(programs, 1):
            if not isinstance(p, dict):
                continue
            college = (p.get("college") or "").strip()
            prog = (p.get("program_name") or "").strip()
            deg = (p.get("degree_type_note") or "").strip()
            # Fallback: if program_name is empty, skip this entry
            if not prog:
                if college:
                    lines.append(f"{i}. **{college}** （项目信息缺失，请以当年简章为准）\n")
                else:
                    continue
            else:
                deg_suffix = f"（{deg}）" if deg else ""
                lines.append(f"{i}. **{college} · {prog}** {deg_suffix}\n")
            if p.get("why_relevant"):
                lines.append(f"   - 相关性：{p['why_relevant']}\n")

    lines.append("\n## 二、核心诊断与定位评级\n")
    advantages = _clean_report_text(report.get("advantages"))
    weaknesses = _clean_report_text(report.get("weaknesses"))
    if advantages:
        lines.append("### 1. 当前优势\n")
        lines.append(advantages + "\n")
    if weaknesses:
        lines.append("### 2. 核心短板\n")
        lines.append(weaknesses + "\n")
    lines.append("### 3. 定位建议（冲 / 稳 / 保）\n")
    pos = report.get("positioning_by_program") or []
    if isinstance(pos, list):
        for item in pos:
            if not isinstance(item, dict):
                continue
            name = item.get("program_key_or_name") or item.get("program_name") or "项目"
            tier = item.get("tier") or ""
            rationale = _clean_report_text(item.get("rationale"))
            if tier and rationale:
                lines.append(f"- **{name}**：{tier} — {rationale}\n")

    lines.append("\n## 三、关键时间轴与 timeline\n")
    tl = report.get("timeline") or []
    if isinstance(tl, list):
        for block in tl:
            if not isinstance(block, dict):
                continue
            bucket = block.get("bucket") or ""
            win = block.get("deadline_or_window") or ""
            title = block.get("title") or ""
            head = f"[{bucket}] {win}：{title}".strip()
            lines.append(f"\n**{head}**\n\n")
            ct = block.get("core_tasks", "")
            if isinstance(ct, list):
                lines.append("\n".join(f"- {t}" for t in ct) + "\n")
            elif ct:
                cleaned = _clean_report_text(ct)
                if cleaned:
                    lines.append(f"核心任务：{cleaned}\n")

    lines.append("\n## 四、核心行动指南\n")
    ag = report.get("action_guidelines") or []
    if isinstance(ag, list):
        for x in ag:
            lines.append(f"- {x}\n")
    else:
        lines.append(str(ag) + "\n")

    lines.append("\n## 五、项目准备建议\n")
    pp = report.get("program_prep") or []
    if isinstance(pp, list):
        for block in pp:
            if not isinstance(block, dict):
                continue
            pname = block.get("program_name") or "（未命名项目）"
            lines.append(f"\n### {pname}\n")
            ef = _clean_report_text(block.get("exam_focus"))
            pa = _clean_report_text(block.get("preferences_from_alumni"))
            op = _clean_report_text(block.get("official_pointers"))
            st = _clean_report_text(block.get("applicant_strategy"))
            if ef:
                lines.append(f"- **考察内容**：{ef}\n")
            if pa:
                lines.append(f"- **经验偏好（往届学长学姐）**：{pa}\n")
            if op:
                lines.append(f"- **官方线索**：{op}\n")
            if st:
                lines.append(f"- **本人应对策略**：{st}\n")

    appendix = str(report.get("_retrieval_evidence_md") or "").strip()
    if appendix:
        lines.append(f"\n---\n\n{appendix}\n")
    note = report.get("references_note") or ""
    if note:
        lines.append(f"\n---\n\n{note}\n")
    # Disclaimer at the very end
    lines.append(
        "\n---\n\n*免责声明：本报告中的联网信息来源于公开网页，未经官方审核，仅供参考。"
        "经验帖内容为主观分享，可能与最新政策存在偏差。"
        "最新招生要求请以中国人民大学各学院官网及研究生招生网陆续发布的官方文件为准。*\n"
    )
    return "".join(lines)


def _repo_root() -> str:
    """Return project root as string (resolved absolute path)."""
    return str(Path(__file__).resolve().parent.parent)


def _find_chinese_font() -> str:
    """Return path to a usable Chinese serif/sans TTF/TTC font."""
    candidates = [
        # 1) Bundled font (user places SimSun.ttf here)
        os.path.join(_repo_root(), "assets", "fonts", "SimSun.ttf"),
        # 2) Windows SimSun TTC (TrueType Collection)
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "simsun.ttc"),
        # 3) Windows SimSun TTF variant
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "simsun.ttf"),
        # 4) Windows YaHei
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "msyh.ttc"),
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "msyh.ttf"),
        # 5) Linux Noto CJK
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        # 6) macOS
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STSong.ttf",
        # 7) Env override
        os.environ.get("LONG_PLAN_PDF_FONT", ""),
    ]
    for p in candidates:
        if p and os.path.isfile(p):
            return p
    return ""


_PDF_CSS = """
body {
    font-family: "SimSun", serif;
    font-size: 10.5pt;
    line-height: 1.8;
    color: #333333;
}
h1 {
    font-size: 18pt;
    text-align: center;
    color: #000000;
    margin-bottom: 20px;
}
h2 {
    font-size: 15pt;
    color: #004080;
    border-bottom: 1px solid #004080;
    margin-top: 25px;
    margin-bottom: 15px;
}
h3 {
    font-size: 12pt;
    font-weight: bold;
    color: #222222;
    margin-top: 15px;
    margin-bottom: 10px;
}
h4 { font-size: 11pt; font-weight: bold; margin-top: 12px; margin-bottom: 8px; }
p {
    margin-bottom: 12px;
    text-align: justify;
    text-indent: 2em;
}
ul, ol { margin-bottom: 15px; padding-left: 2em; }
li { margin-bottom: 8px; }
strong { font-weight: bold; }
sup { font-size: 7.5pt; color: #004080; }
hr { border: none; border-top: 1px solid #cccccc; margin: 2em 0; }
blockquote { margin: 0.5em 0; padding-left: 1em; border-left: 3px solid #999999; color: #555555; }
table { border-collapse: collapse; width: 100%; margin: 0.5em 0; }
th, td { border: 1px solid #999999; padding: 0.4em 0.6em; font-size: 9pt; text-align: left; }
th { background: #f0f0f0; font-weight: bold; }
.disclaimer-block {
    font-size: 9pt;
    color: #666666;
    font-style: italic;
    margin-top: 30px;
    border-top: 0.5px solid #cccccc;
    padding-top: 10px;
}
.ref-title {
    font-size: 12pt;
    font-weight: bold;
    margin-top: 20px;
    color: #444444;
}
.ref-item {
    font-size: 9pt;
    line-height: 1.4;
    margin-bottom: 5px;
}
"""

_PDF_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"/>
<style>{css}</style>
</head>
<body>
<font face="SimSun">{body}</font>
<div class="disclaimer-block">{disclaimer}</div>
</body>
</html>"""

DISCLAIMER_LONG_PLAN = (
    "免责声明：本报告中的联网信息来源于公开网页，未经官方审核，仅供参考。"
    "经验帖内容为主观分享，可能与最新政策存在偏差。"
    "最新招生要求请以中国人民大学各学院官网及研究生招生网陆续发布的官方文件为准。"
)


def report_markdown_to_pdf_bytes(markdown_text: str) -> bytes:
    """Convert report Markdown to PDF with Chinese typography via markdown->HTML->fpdf2.

    Font: bundled SimSun from assets/fonts/ (SimSun.ttf / simsunb.ttf).
    Sizes: headings 15pt (小三号), body 10.5pt (五号).
    Margins: 25mm all sides.
    """
    try:
        from fpdf import FPDF
    except ImportError as e:
        raise RuntimeError("需要安装 fpdf2：pip install fpdf2") from e

    import markdown as md_lib

    repo = _repo_root()
    font_regular = os.path.join(repo, "assets", "fonts", "SimSun.ttf")
    font_bold = os.path.join(repo, "assets", "fonts", "simsunb.ttf")

    # Convert markdown to HTML
    html_body = md_lib.markdown(
        markdown_text,
        extensions=["extra", "tables", "fenced_code"],
    )

    # Post-process: convert [N] citations to superscript
    html_body = re.sub(
        r"\[(\d+)\]",
        r"<sup>[\1]</sup>",
        html_body,
    )

    # Post-process: wrap 【参考文献】 section items in ref-item divs
    html_body = re.sub(
        r"(<p>\[\d+\].*?</p>)",
        r'<div class="ref-item">\1</div>',
        html_body,
    )

    # Build final HTML with template (font wrapper is in template)
    full_html = _PDF_HTML_TEMPLATE.format(
        css=_PDF_CSS,
        body=html_body,
        disclaimer=DISCLAIMER_LONG_PLAN,
    )

    class _RucPDF(FPDF):
        pass

    pdf = _RucPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(25, 25, 25)
    pdf.set_auto_page_break(auto=True, margin=25)

    font_ok = False
    if os.path.isfile(font_regular):
        pdf.add_font("SimSun", "", font_regular)
        if os.path.isfile(font_bold):
            pdf.add_font("SimSun", "B", font_bold)
        else:
            pdf.add_font("SimSun", "B", font_regular)
        pdf.add_font("SimSun", "I", font_regular)
        font_ok = True

    if not font_ok:
        sys_font = _find_chinese_font()
        if sys_font:
            pdf.add_font("SimSun", "", sys_font)
            pdf.add_font("SimSun", "B", sys_font)
            pdf.add_font("SimSun", "I", sys_font)
            font_ok = True

    pdf.add_page()
    pdf.set_font("SimSun", size=10)
    if font_ok:
        pdf.write_html(full_html)
    else:
        plain = re.sub(r"<[^>]+>", " ", full_html)
        plain = re.sub(r"\s+", " ", plain).strip()
        pdf.set_font("Helvetica", size=10)
        pdf.multi_cell(0, 6, "需要安装中文字体。请将 SimSun.ttf 和 simsunb.ttf 放入 assets/fonts/ 目录。")
        pdf.ln(4)
        pdf.multi_cell(0, 6, plain)

    buf = BytesIO()
    try:
        pdf.output(buf)
    except Exception:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            pdf.output(tmp.name)
            tmp.seek(0)
            buf.write(tmp.read())
        os.unlink(tmp.name)
    return buf.getvalue()


def _html_escape(value: Any) -> str:
    return html_lib.escape(str(value or "").strip())


def _html_text(value: Any) -> str:
    text = _clean_report_text(value)
    if not text:
        return ""
    text = _html_escape(text)
    text = re.sub(r"\[(\d+)\]", r"<sup>[\1]</sup>", text)
    return text.replace("\n", "<br>")


def _html_li(value: Any) -> str:
    text = _html_text(value)
    return f"<li>{text}</li>" if text else ""


def _html_rich_block(value: Any) -> str:
    if isinstance(value, list):
        items = "".join(_html_li(x) for x in value)
        return f"<ul>{items}</ul>" if items else ""
    text = _html_text(value)
    return f"<p>{text}</p>" if text else ""


def _cn_section_num(idx: int) -> str:
    nums = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
    if 1 <= idx <= len(nums):
        return nums[idx - 1]
    return str(idx)


def _ruc_logo_svg_inline() -> str:
    candidates = [
        Path(_repo_root()) / "Renmin_University_of_China_logo.svg",
        Path(_repo_root()) / "web" / "assets" / "ruc-logo-full.svg",
        Path(_repo_root()) / "web" / "assets" / "ruc-logo.svg",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            raw = path.read_text(encoding="utf-8", errors="ignore").strip()
        except Exception:
            continue
        raw = re.sub(r"<script\b[^>]*>.*?</script>", "", raw, flags=re.IGNORECASE | re.DOTALL)
        if not raw.lower().startswith("<svg") and "<svg" not in raw[:200].lower():
            continue
        if re.search(r"<svg\b[^>]*\bclass=", raw, flags=re.IGNORECASE):
            return re.sub(
                r'(<svg\b[^>]*\bclass=")([^"]*)(")',
                r"\1ruc-logo \2\3",
                raw,
                count=1,
                flags=re.IGNORECASE,
            )
        return re.sub(r"<svg\b", '<svg class="ruc-logo"', raw, count=1, flags=re.IGNORECASE)
    return '<div class="ruc-logo ruc-logo-fallback">RUC</div>'


def _references_html(report: Dict[str, Any]) -> str:
    refs = report.get("_references") or report.get("references") or []
    if not isinstance(refs, list) or not refs:
        return ""
    items = []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        idx = _html_escape(ref.get("idx") or "")
        entry = _html_escape(ref.get("entry") or ref.get("title") or "")
        url = str(ref.get("url") or "").strip()
        if not entry:
            continue
        if url:
            body = f'<a href="{_html_escape(url)}" target="_blank" rel="noopener noreferrer">{entry}</a>'
        else:
            body = entry
        prefix = f"[{idx}] " if idx else ""
        items.append(f"<li>{prefix}{body}</li>")
    if not items:
        return ""
    return f"""
      <section class="references-section">
        <h2 class="section-title">参考链接与资料来源</h2>
        <ol class="reference-list">{''.join(items)}</ol>
      </section>
    """


def _report_meta_date(report: Dict[str, Any]) -> str:
    gen = str(report.get("generated_at_iso") or "")
    if not gen:
        return datetime.now().strftime("%Y年%m月%d日")
    try:
        dt = datetime.fromisoformat(gen.replace("Z", "+00:00"))
        return dt.strftime("%Y年%m月%d日")
    except Exception:
        return datetime.now().strftime("%Y年%m月%d日")


def report_json_to_html(report: Dict[str, Any]) -> str:
    """Render the reviewed structured report directly to polished HTML."""
    report = report or {}
    generated = _report_meta_date(report)
    target = _html_escape(report.get("target_destination_line") or "中国人民大学保研目标")
    logo_svg = _ruc_logo_svg_inline()

    programs_html = []
    for p in report.get("programs") or []:
        if not isinstance(p, dict) or _is_low_value_text(p.get("program_name")):
            continue
        programs_html.append(
            f"""
            <article class="program-card">
              <div class="card-topline">{_html_escape(p.get('college') or '目标学院')}</div>
              <h3>{_html_escape(p.get('program_name'))}</h3>
              <p class="pill">{_html_escape(p.get('degree_type_note') or '项目类型以当年通知为准')}</p>
              <p>{_html_text(p.get('why_relevant'))}</p>
            </article>
            """
        )

    pos_html = []
    for item in report.get("positioning_by_program") or []:
        if not isinstance(item, dict):
            continue
        name = _html_escape(item.get("program_key_or_name") or item.get("program_name") or "")
        tier = _html_escape(item.get("tier") or "")
        rationale = _html_text(item.get("rationale"))
        if not name or not tier or not rationale:
            continue
        pos_html.append(
            f"""
            <article class="position-card tier-{tier}">
              <span class="tier">{tier}</span>
              <h4>{name}</h4>
              <p>{rationale}</p>
            </article>
            """
        )

    timeline_html = []
    for block in report.get("timeline") or []:
        if not isinstance(block, dict) or _is_low_value_text(block.get("core_tasks")):
            continue
        timeline_html.append(
            f"""
            <article class="timeline-item">
              <div class="timeline-dot"></div>
              <div>
                <p class="timeline-window">{_html_escape(block.get('bucket') or '')} · {_html_escape(block.get('deadline_or_window') or '')}</p>
                <h3>{_html_escape(block.get('title') or '阶段任务')}</h3>
                {_html_rich_block(block.get('core_tasks'))}
              </div>
            </article>
            """
        )

    prep_html = []
    for block in report.get("program_prep") or []:
        if not isinstance(block, dict) or _is_low_value_text(block.get("program_name")):
            continue
        rows = []
        field_map = [
            ("考察内容", "exam_focus"),
            ("经验偏好", "preferences_from_alumni"),
            ("官方线索", "official_pointers"),
            ("本人应对策略", "applicant_strategy"),
        ]
        for label, key in field_map:
            value = _html_text(block.get(key))
            if value:
                rows.append(f"<tr><th>{label}</th><td>{value}</td></tr>")
        if not rows:
            continue
        prep_html.append(
            f"""
            <article class="prep-card">
              <h3>{_html_escape(block.get('program_name'))}</h3>
              <table>{''.join(rows)}</table>
            </article>
            """
        )

    action_items = "".join(_html_li(x) for x in (report.get("action_guidelines") or []))
    advantages = _html_text(report.get("advantages"))
    weaknesses = _html_text(report.get("weaknesses"))
    direction_summary = _html_text(report.get("direction_summary"))
    review = report.get("_quality_review") or {}
    fixed_count = len(review.get("issues_fixed") or []) if isinstance(review, dict) else 0
    quality_badge = f"已完成报告自查与补全，修复 {fixed_count} 处空缺/弱项" if fixed_count else "已完成报告自查"
    sections: List[Tuple[str, str]] = []
    if programs_html:
        lead = f'<p class="lead">{direction_summary}</p>' if direction_summary else ""
        sections.append(("目标院校可选择项目", f'{lead}<div class="program-grid">{"".join(programs_html)}</div>'))

    diagnosis_cards = ""
    if advantages:
        diagnosis_cards += f'<article class="diagnosis-card"><h3>当前优势</h3><p>{advantages}</p></article>'
    if weaknesses:
        diagnosis_cards += f'<article class="diagnosis-card"><h3>核心短板</h3><p>{weaknesses}</p></article>'
    if diagnosis_cards or pos_html:
        sections.append((
            "核心诊断与定位评级",
            f'<div class="diagnosis-grid">{diagnosis_cards}</div><div class="position-grid">{"".join(pos_html)}</div>',
        ))
    if timeline_html:
        sections.append(("关键时间轴", f'<div class="timeline">{"".join(timeline_html)}</div>'))
    if action_items:
        sections.append(("核心行动指南", f'<ul class="action-list">{action_items}</ul>'))
    if prep_html:
        sections.append(("项目准备建议", "".join(prep_html)))

    numbered_sections = "\n".join(
        f'<section><h2 class="section-title">{_cn_section_num(i)}、{title}</h2>{body}</section>'
        for i, (title, body) in enumerate(sections, 1)
    )
    references_section = _references_html(report)

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>中国人民大学保研规划报告</title>
  <style>
    :root {{
      --ruc-red:#b4002d; --ink:#111827; --muted:#667085; --line:#e5e7eb;
      --bg:#f5f5f4; --paper:#fff; --soft:#fff7f8; --green:#0f766e; --blue:#2563eb; --amber:#b45309;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--ink); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; line-height:1.75; }}
    .report-shell {{ max-width:1100px; margin:32px auto; background:var(--paper); box-shadow:0 20px 60px rgba(15,23,42,.10); border:1px solid var(--line); }}
    .cover {{ display:grid; grid-template-columns:128px 1fr; gap:30px; align-items:center; padding:42px 56px 34px; border-bottom:5px solid var(--ruc-red); background:linear-gradient(180deg,#fff 0%,#fff7f8 100%); }}
    .ruc-logo {{ width:120px; height:120px; object-fit:contain; display:block; }}
    .ruc-logo-fallback {{ display:grid; place-items:center; border-radius:50%; border:2px solid var(--ruc-red); color:var(--ruc-red); font-weight:800; }}
    .kicker {{ color:var(--ruc-red); font-weight:800; letter-spacing:.14em; font-size:14px; margin:0 0 8px; }}
    h1 {{ margin:0; font-size:38px; line-height:1.2; }}
    .meta {{ margin:12px 0 0; color:var(--muted); font-size:15px; }}
    main {{ padding:36px 56px 56px; }}
    .summary-strip {{ display:flex; flex-wrap:wrap; gap:14px; margin:0 0 28px; padding:18px 20px; background:#fafafa; border:1px solid var(--line); border-radius:12px; }}
    .summary-strip strong {{ color:var(--ink); }}
    section {{ margin-top:34px; }}
    .section-title {{ margin:0 0 16px; padding-bottom:10px; border-bottom:1px solid var(--line); color:var(--ruc-red); font-size:25px; }}
    .lead {{ font-size:17px; color:#344054; background:#fafafa; padding:18px 20px; border-radius:12px; border:1px solid var(--line); }}
    .program-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px; }}
    .program-card,.position-card,.prep-card,.diagnosis-card {{ border:1px solid var(--line); border-radius:14px; padding:18px 20px; background:#fff; break-inside:avoid; }}
    .program-card h3,.prep-card h3 {{ margin:4px 0 8px; font-size:20px; }}
    .card-topline {{ color:var(--muted); font-size:13px; font-weight:700; }}
    .pill,.tier {{ display:inline-flex; align-items:center; padding:3px 10px; border-radius:999px; background:var(--soft); color:var(--ruc-red); font-weight:700; font-size:13px; }}
    .diagnosis-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
    .diagnosis-card h3 {{ margin:0 0 8px; }}
    .position-grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; margin-top:16px; }}
    .position-card h4 {{ margin:8px 0; font-size:17px; }}
    .tier-冲 .tier {{ background:#fff1f2; color:#be123c; }}
    .tier-稳 .tier {{ background:#ecfdf5; color:var(--green); }}
    .tier-保 .tier {{ background:#eff6ff; color:var(--blue); }}
    .timeline {{ position:relative; display:grid; gap:18px; }}
    .timeline-item {{ display:grid; grid-template-columns:28px 1fr; gap:14px; }}
    .timeline-dot {{ width:14px; height:14px; border-radius:50%; background:var(--ruc-red); margin-top:10px; box-shadow:0 0 0 6px #fff1f2; }}
    .timeline-window {{ color:var(--muted); font-weight:700; margin:0 0 4px; }}
    .timeline-item h3 {{ margin:0 0 6px; }}
    .timeline-item ul {{ margin:0; padding-left:1.2em; }}
    .action-list {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px 18px; padding-left:20px; }}
    table {{ width:100%; border-collapse:collapse; margin-top:10px; }}
    th,td {{ border:1px solid var(--line); padding:10px 12px; text-align:left; vertical-align:top; }}
    th {{ width:120px; background:#fafafa; color:#344054; }}
    sup {{ color:var(--ruc-red); font-weight:800; }}
    .quality {{ margin-top:36px; padding:14px 18px; border-left:4px solid var(--ruc-red); background:#fff7f8; color:#475467; }}
    .references-section {{ margin-top:34px; }}
    .reference-list {{ padding-left:1.4em; color:#344054; font-size:14px; }}
    .reference-list a {{ color:var(--blue); text-decoration:none; border-bottom:1px solid rgba(37,99,235,.25); }}
    .reference-list li {{ margin-bottom:8px; }}
    .footer-note {{ margin-top:28px; color:var(--muted); font-size:13px; }}
    @media (max-width:820px) {{ .report-shell{{margin:0;border:none}} .cover{{grid-template-columns:1fr;padding:28px 24px}} main{{padding:24px}} .program-grid,.diagnosis-grid,.position-grid,.action-list{{grid-template-columns:1fr}} h1{{font-size:28px}} }}
  </style>
</head>
<body>
  <article class="report-shell">
    <header class="cover">
      {logo_svg}
      <div>
        <p class="kicker">RENMIN UNIVERSITY OF CHINA</p>
        <h1>中国人民大学保研规划报告</h1>
        <p class="meta">生成日期：{generated}　|　目标去向：{target}</p>
        <p class="meta">供个人规划参考，最终以学院最新通知为准</p>
      </div>
    </header>
    <main>
      <div class="summary-strip"><span><strong>目标：</strong>{target}</span><span><strong>状态：</strong>{_html_escape(quality_badge)}</span></div>
      {numbered_sections}
      {references_section}
      <div class="quality">{_html_escape(quality_badge)}。报告中已隐藏空白、横杠和低价值占位内容；经验信息只作为备考线索。</div>
      <p class="footer-note">本报告由系统基于官方文件、公众经验库和可选联网资料生成；经验信息可能过时或带有个人偏差，请以中国人民大学各学院官网及研究生招生网最新通知为准。</p>
    </main>
  </article>
</body>
</html>"""


def report_markdown_to_html(markdown_text: str) -> str:
    """Convert report Markdown to a polished standalone HTML report."""
    try:
        import markdown as md_lib
    except ImportError:
        body = "<p>" + re.sub(r"\n+", "<br>", markdown_text.strip()) + "</p>"
    else:
        body = md_lib.markdown(
            markdown_text,
            extensions=["extra", "tables", "fenced_code"],
        )

    body = re.sub(r"\[(\d+)\]", r"<sup>[\1]</sup>", body)
    generated = datetime.now().strftime("%Y年%m月%d日")
    logo_svg = _ruc_logo_svg_inline()
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>中国人民大学保研规划报告</title>
  <style>
    :root {{
      --ruc-red: #b4002d;
      --ink: #1f2937;
      --muted: #6b7280;
      --line: #e5e7eb;
      --paper: #ffffff;
      --bg: #f5f5f4;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      line-height: 1.75;
    }}
    .report-shell {{
      max-width: 980px;
      margin: 32px auto;
      background: var(--paper);
      box-shadow: 0 20px 60px rgba(15, 23, 42, 0.10);
      border: 1px solid var(--line);
    }}
    .cover {{
      display: grid;
      grid-template-columns: 132px 1fr;
      gap: 28px;
      align-items: center;
      padding: 44px 52px 34px;
      border-bottom: 4px solid var(--ruc-red);
      background: linear-gradient(180deg, #fff 0%, #fff7f8 100%);
    }}
    .ruc-logo {{
      width: 124px;
      height: 124px;
      object-fit: contain;
      display: block;
    }}
    .ruc-logo-fallback {{
      display: grid;
      place-items: center;
      border-radius: 50%;
      border: 2px solid var(--ruc-red);
      color: var(--ruc-red);
      font-weight: 800;
    }}
    .kicker {{
      color: var(--ruc-red);
      font-weight: 700;
      letter-spacing: 0.12em;
      font-size: 13px;
      margin: 0 0 8px;
    }}
    h1 {{
      margin: 0;
      font-size: 34px;
      line-height: 1.25;
      color: #111827;
    }}
    .meta {{
      margin: 12px 0 0;
      color: var(--muted);
      font-size: 14px;
    }}
    main {{
      padding: 36px 52px 52px;
    }}
    h2 {{
      margin-top: 34px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--line);
      color: var(--ruc-red);
      font-size: 23px;
    }}
    h3 {{
      margin-top: 24px;
      font-size: 18px;
      color: #111827;
    }}
    p {{ margin: 0 0 14px; }}
    ul, ol {{ padding-left: 1.4em; }}
    li {{ margin-bottom: 7px; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 18px 0;
      font-size: 14px;
    }}
    th, td {{
      border: 1px solid var(--line);
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
    }}
    th {{ background: #f9fafb; }}
    blockquote {{
      margin: 18px 0;
      padding: 12px 16px;
      border-left: 4px solid var(--ruc-red);
      background: #fff7f8;
      color: #4b5563;
    }}
    sup {{ color: var(--ruc-red); font-weight: 700; }}
    .footer-note {{
      margin-top: 42px;
      padding-top: 16px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 13px;
    }}
    @media (max-width: 720px) {{
      .report-shell {{ margin: 0; border: none; }}
      .cover {{ grid-template-columns: 1fr; padding: 28px 24px; }}
      .ruc-logo {{ width: 96px; height: 96px; }}
      h1 {{ font-size: 26px; }}
      main {{ padding: 24px; }}
    }}
  </style>
</head>
<body>
  <article class="report-shell">
    <header class="cover">
      {logo_svg}
      <div>
        <p class="kicker">RENMIN UNIVERSITY OF CHINA</p>
        <h1>中国人民大学保研规划报告</h1>
        <p class="meta">生成日期：{generated}　|　供个人规划参考，最终以学院最新通知为准</p>
      </div>
    </header>
    <main>
      {body}
      <p class="footer-note">本报告由系统基于官方文件、公众经验库和可选联网资料生成；经验信息可能过时或带有个人偏差，请以中国人民大学各学院官网及研究生招生网最新通知为准。</p>
    </main>
  </article>
</body>
</html>"""


def empty_intake_template() -> Dict[str, Any]:
    return long_plan_intake_template()


def empty_report_template() -> Dict[str, Any]:
    return long_plan_report_skeleton()
