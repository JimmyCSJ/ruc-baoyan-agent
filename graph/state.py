from typing import Any, Dict, List, TypedDict


class AgentState(TypedDict):
    user_query: str
    question_type: str
    retrieved_docs: List[Dict[str, Any]]
    final_answer: str
    chat_history: List[Dict[str, Any]]
