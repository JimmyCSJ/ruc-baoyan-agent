"""Graph node adapter for the Text-to-SQL data agent."""

from typing import Dict

from agents.data_agent import data_agent_query
from graph.state import AgentState


def query_data_agent(state: AgentState) -> Dict[str, object]:
    result, activated = data_agent_query(state["user_query"])
    return {"data_agent_result": result}
