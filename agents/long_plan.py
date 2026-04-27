"""长问答：信息收集模板 + 追问 + 结构化保研方案报告（JSON）."""

from __future__ import annotations

import json
import re
from typing import Any, Dict

from langchain_openai import ChatOpenAI

from config import get_settings
from tools.web_search import search_web_vertical


def _fix_report_template_types() -> Dict[str, Any]:
    """报告 JSON 固定键（与模型约定一致）。"""
    return {
        "summary": "",
        "profile_recap": "",
        "strategy_overview": "",
        "timeline_by_semester": [],
        "school_and_program_shortlist": [],
        "materials_checklist": [],
        "interview_prep_plan": "",
        "risks_and_mitigations": [],
        "next_actions_7d": [],
        "references_note": "请以目标院校官网、学院通知与研招网最新文件为准；网络检索仅供参考。",
    }


def empty_intake_template() -> Dict[str, Any]:
    """用户侧信息收集模板（由模型或前端填充）。"""
    return {
        "meta": {
            "goal": "",
            "updated_at": "",
        },
        "basic": {
            "year_of_study": "",
            "major_and_undergrad_school": "",
            "gpa_or_rank": "",
            "english_scores": "",
        },
        "targets": {
            "target_schools_or_programs": "",
            "preferred_degree_type": "",
            "city_or_region_preference": "",
        },
        "experience": {
            "research_projects_papers": "",
            "competitions_awards": "",
            "student_work_leadership": "",
        },
        "career": {
            "future_expectations": "",
            "expected_roles_or_industry": "",
        },
        "prep": {
            "interview_prep_status": "",
            "weaknesses_and_constraints": "",
        },
        "free_notes": "",
    }


def empty_report_template() -> Dict[str, Any]:
    """模型输出报告骨架（稳定字段，便于前端渲染与存档）。"""
    return _fix_report_template_types()


def _llm_json_chat(system: str, user: str, temperature: float = 0.35) -> str:
    settings = get_settings()
    if not settings.deepseek_api_key or not settings.enable_real_llm:
        raise RuntimeError("LLM unavailable")

    llm = ChatOpenAI(
        model=settings.deepseek_model,
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        default_headers={"X-Failover-Enabled": str(settings.failover_enabled).lower()},
        temperature=temperature,
        top_p=settings.llm_top_p,
        max_tokens=min(settings.llm_max_tokens, 4096),
        frequency_penalty=settings.llm_frequency_penalty,
        extra_body={"top_k": settings.llm_top_k},
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    return llm.invoke(messages).content


def _extract_json_object(text: str) -> Dict[str, Any]:
    text = text.strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError("no json object in model output")
    return json.loads(m.group(0))


def generate_clarifying_questions(goal: str, partial_intake: Dict[str, Any] | None) -> Dict[str, Any]:
    """根据目标与已填信息生成追问列表；无 LLM 时返回固定追问。"""
    partial_intake = partial_intake or {}
    system = (
        "你是保研规划顾问。根据用户目标和已填写的 intake JSON，生成需要补充的追问。"
        "只输出一个 JSON 对象，格式："
        '{"questions":["..."],"missing_slots":["basic.year_of_study", ...]}'
        "missing_slots 使用点路径表示模板中仍为空的字段；已填充分的可不放。"
        "追问要具体、可回答，中文，6～10 个问题。"
    )
    user = f"用户目标：{goal}\n当前已填：{json.dumps(partial_intake, ensure_ascii=False)}"
    try:
        raw = _llm_json_chat(system, user, temperature=0.4)
        data = _extract_json_object(raw)
        questions = data.get("questions") or []
        missing = data.get("missing_slots") or []
        if not isinstance(questions, list):
            questions = []
        questions = [str(q).strip() for q in questions if str(q).strip()]
        return {"questions": questions[:12], "missing_slots": missing}
    except Exception:
        return {
            "questions": [
                "你目前大几？本科专业与所在院校是？",
                "绩点/排名或核心课成绩大致如何？英语（四六级/雅思托福）分数？",
                "目标院校或方向有哪些（学硕/专硕/直博）？地域偏好？",
                "科研经历、论文、项目或竞赛获奖请简要说明。",
                "学生工作、社团、实习中你最想强调哪一段？",
                "未来 3～5 年你更倾向学术、体制、企业还是创业路径？",
                "期望岗位或行业领域是什么？",
                "夏令营/预推免/九推目前准备到哪一步？模拟面试做过吗？",
                "当前最大短板或顾虑是什么（时间、材料、心态等）？",
            ],
            "missing_slots": [],
        }


def generate_plan_report(goal: str, intake: Dict[str, Any], use_web: bool = True) -> Dict[str, Any]:
    """根据完整 intake 生成结构化报告 JSON；无 LLM 时返回基于模板的占位报告。"""
    intake = intake or {}
    web_snippets = ""
    if use_web:
        q = goal or json.dumps(intake, ensure_ascii=False)[:500]
        web_docs = search_web_vertical(f"保研 {q}")[:6]
        if web_docs:
            web_snippets = "\n".join(
                f"- [{d['source']}] {d['title']}: {d['content'][:400]}" for d in web_docs
            )

    skeleton = _fix_report_template_types()
    system = (
        "你是资深保研规划顾问。请根据用户提供的 intake JSON 与可选网络摘要，"
        "生成一份定制化保研方案。必须只输出一个 JSON 对象，键名与下列骨架完全一致，不要增删键：\n"
        f"{json.dumps(skeleton, ensure_ascii=False)}\n"
        "所有列表项用中文短句；summary 2～4 句；timeline_by_semester 按学期列出可执行步骤；"
        "next_actions_7d 恰好 5～7 条；内容务实、可执行，避免空话。"
    )
    user = (
        f"用户目标：{goal}\n"
        f"intake：{json.dumps(intake, ensure_ascii=False)}\n"
        f"网络摘要（可能为空）：\n{web_snippets or '（无）'}"
    )
    try:
        raw = _llm_json_chat(system, user, temperature=0.25)
        data = _extract_json_object(raw)
        # 合并缺省键，防止模型漏字段
        out = _fix_report_template_types()
        for k in out:
            if k in data:
                out[k] = data[k]
        default_note = _fix_report_template_types()["references_note"]
        out["references_note"] = str(out.get("references_note") or default_note)
        return out
    except Exception:
        out = _fix_report_template_types()
        out["summary"] = (
            f"已收到你的保研规划需求：{goal or '（未填写目标）'}。"
            "当前为离线占位方案：请配置 DEEPSEEK_API_KEY 并设置 ENABLE_REAL_LLM=true 以生成完整定制报告。"
        )
        out["profile_recap"] = json.dumps(intake, ensure_ascii=False)[:2000]
        out["strategy_overview"] = "建议按目标院校官网最新通知核对申请时间线、材料清单与考核形式。"
        out["timeline_by_semester"] = [
            "本学期：核对绩点与科研材料，整理成绩单与证明。",
            "下学期：关注夏令营通知，准备个人陈述与推荐信。",
            "暑假前后：参营/线上考核，复盘笔面试表现。",
        ]
        out["next_actions_7d"] = [
            "列出 3～5 所目标院系并下载去年招生简章。",
            "整理一页纸简历（科研/竞赛/学生工作量化）。",
            "准备英语自我介绍与常见专业问题草稿。",
            "联系 1～2 位推荐人沟通推荐信时间节点。",
            "建立材料文件夹（PDF 命名规范）。",
        ]
        return out
