"""LangGraph node adapters.

Owner: member 1 (graph flow).
Responsibility: call agent modules and map return values into `AgentState`.
Avoid putting retrieval data and answer prompt content directly here.
"""

from typing import Dict, List

from agents.answer import generate_llm_answer, generate_mock_answer
from agents.retrieval import retrieve_documents
from agents.router import classify_question
from config import get_settings
from graph.state import AgentState, RetrievedDoc


def route_question(state: AgentState) -> Dict[str, str]:
    return {"question_type": classify_question(state["user_query"])}


def retrieve_docs(state: AgentState) -> Dict[str, List[RetrievedDoc]]:
    return {
        "retrieved_docs": retrieve_documents(
            user_query=state["user_query"],
            question_type=state["question_type"],
        )
    }


def generate_answer(state: AgentState) -> Dict[str, str]:
    docs = state["retrieved_docs"]
    settings = get_settings()
    if not settings.enable_real_llm:
        return {
            "final_answer": generate_mock_answer(
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
        answer = generate_mock_answer(
            user_query=state["user_query"],
            question_type=state["question_type"],
            retrieved_docs=docs,
        )
    return {"final_answer": answer}
