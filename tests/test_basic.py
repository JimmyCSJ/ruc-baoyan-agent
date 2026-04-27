"""Core workflow tests.

Owner: member 3 (tests and answer quality).
Responsibility: end-to-end smoke test for graph flow.
Avoid putting heavy data fixtures directly here.
"""

from graph.builder import build_graph

_REQUIRED_DOC_KEYS = {"source", "title", "content", "confidence"}


def test_graph_end_to_end_mock_path() -> None:
    graph = build_graph()
    result = graph.invoke(
        {
            "user_query": "我想看人大专业和申请条件",
            "question_type": "general_info",
            "retrieved_docs": [],
            "final_answer": "",
            "chat_history": [],
            "enable_web_search": False,
        }
    )

    assert result["question_type"] in {"major_info", "admission_requirement"}
    assert len(result["retrieved_docs"]) >= 1
    assert all(_REQUIRED_DOC_KEYS <= set(doc.keys()) for doc in result["retrieved_docs"])
    assert result["final_answer"]
    assert "retrieval_trace" in result
    assert result["retrieval_trace"]["stages"]
