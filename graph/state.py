"""Shared state schema for LangGraph.

Owner: member 1.
Responsibility: define stable data contracts across graph/agents/tools.
Avoid putting business logic here.
"""

from typing import Any, Dict, List, Literal, TypedDict

from typing_extensions import NotRequired

KBScope = Literal["hybrid", "official_only", "public_only"]

SourceType = Literal["official_school_document", "experience_note", "web_citation", "other"]
CredibilityLevel = Literal["high", "medium", "low"]
FreshnessHint = Literal["unknown", "indexed_campus_doc", "possibly_outdated", "web_unverified"]
EvidenceRole = Literal["primary_policy", "supplementary_experience", "supplementary_web", "system"]

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
    source_group: NotRequired[str]
    kb_group: NotRequired[str]
    doc_id: NotRequired[str]
    provenance: NotRequired[Dict[str, object]]
    match_score: NotRequired[float]
    source_type: NotRequired[SourceType]
    credibility_level: NotRequired[CredibilityLevel]
    suspected_ad: NotRequired[bool]
    freshness: NotRequired[FreshnessHint]
    evidence_role: NotRequired[EvidenceRole]
    ad_risk_reasons: NotRequired[List[str]]
    evidence_quality_tier: NotRequired[int]
    evidence_quality_label: NotRequired[str]
    credibility_notes: NotRequired[List[str]]


class TraceStage(TypedDict):
    stage: str
    source_group: str
    top_k: int
    matched: List[Dict[str, object]]


class RetrievalTrace(TypedDict):
    policy: str
    stages: List[TraceStage]
    merged_for_generation: List[str]
    kb_scope: NotRequired[KBScope]
    execution_steps: NotRequired[List[str]]
    official_files_read: NotRequired[List[str]]
    query: NotRequired[str]
    query_tokens: NotRequired[List[str]]
    question_type: NotRequired[QuestionType]
    policy_like_query: NotRequired[bool]
    web_primary_source: NotRequired[str]
    web_access_used: NotRequired[bool]
    web_fallback_used: NotRequired[bool]
    web_failure_reason: NotRequired[str]
    query_plan: NotRequired[Dict[str, object]]
    docs_passed_to_generation: NotRequired[List[Dict[str, object]]]


class ChatMessage(TypedDict):
    role: str
    content: str


class AgentState(TypedDict):
    user_query: str
    question_type: QuestionType
    retrieved_docs: List[RetrievedDoc]
    final_answer: str
    chat_history: List[ChatMessage]
    enable_web_search: bool
    retrieval_trace: NotRequired[RetrievalTrace]
    kb_debug: NotRequired[bool]
    kb_scope: NotRequired[KBScope]
    execution_steps: NotRequired[List[str]]
    official_files_read: NotRequired[List[str]]
    data_agent_result: NotRequired[str]
    references: NotRequired[List[Dict[str, Any]]]
