"""LangGraph node adapters.

Owner: member 1 (graph flow).
Responsibility: call agent modules and map return values into `AgentState`.
Avoid putting retrieval data and answer prompt content directly here.
"""

from typing import Dict

from agents.answer import generate_llm_answer, generate_mock_answer
from agents.retrieval import retrieve_documents_with_trace
from agents.router import classify_question
from config import get_settings
from graph.state import AgentState


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
    return {"retrieved_docs": docs, "retrieval_trace": trace}


def generate_answer(state: AgentState) -> Dict[str, str]:
    docs = state["retrieved_docs"]
    settings = get_settings()
    if not settings.enable_real_llm:
        hint = (
            "【提示】当前为离线演示模式：未启用真实大模型（请在 `.env` 中设置 `ENABLE_REAL_LLM=true` 并配置有效的 `DEEPSEEK_API_KEY`）。"
            "下方回答是本地模板拼接检索片段，不是模型生成的完整解答。\n\n"
        )
        return {
            "final_answer": hint
            + generate_mock_answer(
                user_query=state["user_query"],
                question_type=state["question_type"],
                retrieved_docs=docs,
            )
        }

    try:
        answer = generate_llm_answer(
            user_query=state["user_query"],
            question_type=state["question_type"],
            retrieved_docs=docs,
        )
    except Exception:
        # 无 key 或调用失败时，回退到本地 mock，保证链路可演示
        hint = (
            "【提示】大模型调用失败（请检查 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL` 与网络），已回退为本地模板回答。\n\n"
        )
        answer = hint + generate_mock_answer(
            user_query=state["user_query"],
            question_type=state["question_type"],
            retrieved_docs=docs,
        )
    return {"final_answer": answer}
