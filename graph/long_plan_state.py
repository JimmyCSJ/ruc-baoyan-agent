"""LangGraph state for long-term (保研) planning workflow."""

from __future__ import annotations

from typing import Any, Dict, List, TypedDict

from typing_extensions import Required

from graph.state import RetrievedDoc, RetrievalTrace


class LongPlanIntakeRequired(TypedDict):
    """表单必填项（后台组装为 intake JSON）。"""

    current_school: str
    grade_year: str
    college: str
    major: str
    gpa: str
    major_rank_percentile: str
    target_destination: str
    english_scores: str


class LongPlanIntakeOptional(TypedDict, total=False):
    """选填项。"""

    research_and_competitions: str
    internships: str
    region_preference: str
    student_work_clubs: str
    career_path_3_5y: str
    expected_roles_or_industry: str
    admission_prep_stage: str
    main_concerns: str


class ProgramItem(TypedDict, total=False):
    college: str
    program_name: str
    degree_type_note: str
    why_relevant: str


class PositioningItem(TypedDict, total=False):
    program_key_or_name: str
    tier: str
    rationale: str


class TimelineItem(TypedDict, total=False):
    bucket: str
    deadline_or_window: str
    title: str
    core_tasks: str


class ProgramPrepItem(TypedDict, total=False):
    program_name: str
    exam_focus: str
    preferences_from_alumni: str
    official_pointers: str


class LongPlanReport(TypedDict, total=False):
    """与前端预览 / PDF 一致的五段式报告 JSON。"""

    generated_at_iso: str
    target_destination_line: str
    direction_summary: str
    programs: List[ProgramItem]
    advantages: str
    weaknesses: str
    positioning_by_program: List[PositioningItem]
    timeline: List[TimelineItem]
    action_guidelines: List[str]
    program_prep: List[ProgramPrepItem]
    references_note: str


class LongPlanState(TypedDict, total=False):
    """长程规划图状态：表单 intake → 可选 KB → 报告。"""

    intake: Required[Dict[str, Any]]
    use_web: Required[bool]
    generated_at_iso: str
    retrieval_query: str
    retrieved_docs: List[RetrievedDoc]
    retrieval_trace: RetrievalTrace
    kb_context_text: str
    retrieval_evidence_prompt: str
    retrieval_evidence_md: str
    part1_target: Dict[str, Any]
    part2_diagnosis: Dict[str, Any]
    part3_timeline: Dict[str, Any]
    part4_action: Dict[str, Any]
    part5_prep: Dict[str, Any]
    part_generation_errors: Dict[str, str]
    report: LongPlanReport
    report_markdown: str
    error: str
    references: List[Dict[str, Any]]
