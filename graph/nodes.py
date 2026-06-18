"""LangGraph node adapters.

Owner: member 1 (graph flow).
Responsibility: call agent modules and map return values into `AgentState`.
Avoid putting retrieval data and answer prompt content directly here.
"""

from typing import Any, Dict, List

from agents.answer import generate_llm_answer, generate_mock_answer
from agents.evidence_judge import review_evidence_with_model
from agents.retrieval import retrieve_documents_with_trace
from agents.router import classify_question
from config import get_settings
from graph.state import AgentState


def _retrieval_process_section(state: AgentState) -> str:
    docs = state.get("retrieved_docs") or []
    official_files = list(state.get("official_files_read") or [])
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
    lines.append("### 【检索过程】")
    if official_files:
        shown = official_files[:12]
        tail = f"（其余 {len(official_files) - len(shown)} 个省略）" if len(official_files) > len(shown) else ""
        lines.append("- 本次参考的官方材料：")
        for f in shown:
            lines.append(f"  - {f}")
        if tail:
            lines.append(f"- {tail}")
    elif official_titles:
        shown = official_titles[:8]
        tail = f"（共 {len(official_titles)} 份，按标题展示）" if len(official_titles) > len(shown) else ""
        lines.append(f"- 本次命中官方文件标题：{'、'.join([f'“{x}”' for x in shown])} {tail}".strip())
    else:
        lines.append("- 本次参考的官方材料：无（未启用官方检索或未命中）")

    lines.append(f"- 公众信息库命中记录：{public_count} 条")
    if web_count:
        lines.append(f"- 联网检索命中：{web_count} 条")
    lines.append(
        f"- 证据覆盖计数：官方 {official_count} 条｜公众 {public_count} 条｜联网 {web_count} 条｜合计 {len(docs)} 条"
    )

    return "\n".join(lines).strip() + "\n\n"


def route_question(state: AgentState) -> Dict[str, str]:
    return {"question_type": classify_question(state["user_query"])}


def retrieve_docs(state: AgentState) -> Dict[str, object]:
    scope = state.get("kb_scope") or "hybrid"
    docs, trace = retrieve_documents_with_trace(
        user_query=state["user_query"],
        question_type=state["question_type"],
        enable_web_search=state["enable_web_search"],
        kb_debug=bool(state.get("kb_debug", False)),
        kb_scope=scope,
    )
    steps = trace.get("execution_steps") if isinstance(trace, dict) else None
    files = trace.get("official_files_read") if isinstance(trace, dict) else None
    return {
        "retrieved_docs": docs,
        "retrieval_trace": trace,
        "execution_steps": list(steps or []),
        "official_files_read": list(files or []),
    }


def generate_answer(state: AgentState) -> Dict[str, object]:
    docs = review_evidence_with_model(state["user_query"], state["retrieved_docs"])
    state = {**state, "retrieved_docs": docs}
    data_result = state.get("data_agent_result", "")
    retrieval_section = _retrieval_process_section(state)
    if data_result:
        retrieval_section = data_result + "\n\n" + retrieval_section
    references: List[Dict[str, Any]] = []
    settings = get_settings()
    if not settings.enable_real_llm:
        hint = (
            "【提示】当前为离线演示模式：请在 `.env` 中设置 `ENABLE_REAL_LLM=true`；API Key 可使用 `MOARK_API_KEY` 或 `DEEPSEEK_API_KEY`（二者读其一即可），并配置 `MOARK_BASE_URL` 或 `DEEPSEEK_BASE_URL`。"
            "下方回答是本地模板拼接检索片段，不是模型生成的完整解答。\n\n"
        )
        mock_answer, references = generate_mock_answer(
            user_query=state["user_query"],
            question_type=state["question_type"],
            retrieved_docs=docs,
        )
        return {
            "final_answer": hint + retrieval_section + mock_answer,
            "references": references,
            "retrieved_docs": docs,
        }

    try:
        answer, references = generate_llm_answer(
            user_query=state["user_query"],
            question_type=state["question_type"],
            retrieved_docs=docs,
            data_agent_result=data_result,
        )
    except Exception:
        # 无 key 或调用失败时，回退到本地 mock，保证链路可演示
        hint = (
            "【提示】大模型调用失败（请检查 `MOARK_API_KEY`/`DEEPSEEK_API_KEY`、`MOARK_BASE_URL`/`DEEPSEEK_BASE_URL` 与网络），已回退为本地模板回答。\n\n"
        )
        mock_answer, references = generate_mock_answer(
            user_query=state["user_query"],
            question_type=state["question_type"],
            retrieved_docs=docs,
        )
        answer = hint + mock_answer
    return {"final_answer": retrieval_section + answer, "references": references, "retrieved_docs": docs}
