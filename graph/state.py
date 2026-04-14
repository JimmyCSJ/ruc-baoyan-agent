"""Shared state schema for LangGraph.

Owner: member 1.
Responsibility: define stable data contracts across graph/agents/tools.
Avoid putting business logic here.
"""

from typing import List, Literal, TypedDict

QuestionType = Literal[
    "major_info",
    "admission_requirement",
    "eligibility_evaluation",
    "experience_reference",
    "general_info",
]


class RetrievedDoc(TypedDict):
    source: str
    title: str
    content: str
    confidence: float


class ChatMessage(TypedDict):
    role: str
    content: str


class AgentState(TypedDict):
    user_query: str
    question_type: QuestionType
    retrieved_docs: List[RetrievedDoc]
    final_answer: str
    chat_history: List[ChatMessage]
