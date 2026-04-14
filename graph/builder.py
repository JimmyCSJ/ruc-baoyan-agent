"""Graph builder.

Owner: member 1 (main flow and graph structure).
Responsibility: define node list and execution edges only.
Avoid embedding business logic here.
"""

from langgraph.graph import END, START, StateGraph

from graph.nodes import generate_answer, retrieve_docs, route_question
from graph.state import AgentState


def build_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("route_question", route_question)
    workflow.add_node("retrieve_docs", retrieve_docs)
    workflow.add_node("generate_answer", generate_answer)

    workflow.add_edge(START, "route_question")
    workflow.add_edge("route_question", "retrieve_docs")
    workflow.add_edge("retrieve_docs", "generate_answer")
    workflow.add_edge("generate_answer", END)

    return workflow.compile()
