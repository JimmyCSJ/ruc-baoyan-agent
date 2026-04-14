from graph.builder import build_graph


def test_build_graph_placeholder() -> None:
    result = build_graph()
    assert result["status"] == "placeholder graph"
    assert result["state_schema"].__name__ == "AgentState"
