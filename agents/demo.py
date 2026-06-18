"""Demo entry helpers.

Owner: member 3 (output format and demo UX).
Responsibility: demo input fixtures and terminal rendering.
Avoid putting graph wiring logic here.
"""

from graph.state import AgentState


def default_demo_query() -> str:
    return "我想了解中国人民大学某学院有哪些专业，以及申请条件是什么？"


def build_initial_state(user_query: str) -> AgentState:
    return {
        "user_query": user_query,
        "question_type": "general_info",
        "retrieved_docs": [],
        "final_answer": "",
        "chat_history": [],
        "enable_web_search": False,
    }


def render_demo_output(result: AgentState) -> str:
    doc_lines = []
    for idx, doc in enumerate(result["retrieved_docs"], start=1):
        doc_lines.append(f"{idx}. [{doc['source']}] {doc['title']} (confidence={doc['confidence']}): {doc['content']}")

    return (
        "=== Agent Demo Start ===\n"
        f"User Query: {result['user_query']}\n"
        f"Question Type: {result['question_type']}\n"
        "Retrieved Docs:\n"
        + "\n".join(doc_lines)
        + "\nFinal Answer:\n"
        + result["final_answer"]
        + "\n=== Agent Demo End ==="
    )
