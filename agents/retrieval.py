"""Retrieval orchestration module.

Owner: member 2 (data & retrieval).
Responsibility: choose data sources by `QuestionType` and return unified docs.
Avoid putting graph orchestration or answer prompt logic here.
"""

from typing import List

from graph.state import QuestionType, RetrievedDoc
from tools.brochure_search import search_brochure_for_admission_requirement, search_brochure_for_major
from tools.official_search import (
    search_official_for_admission_requirement,
    search_official_for_eligibility_evaluation,
    search_official_for_major,
)
from tools.xiaohongshu_search import search_xiaohongshu_experience_reference


def retrieve_documents(user_query: str, question_type: QuestionType) -> List[RetrievedDoc]:
    docs: List[RetrievedDoc] = []

    if "专业" in user_query or question_type == "major_info":
        docs.extend(search_official_for_major())
        docs.extend(search_brochure_for_major())

    if "条件" in user_query or "成绩" in user_query or question_type == "admission_requirement":
        docs.extend(search_official_for_admission_requirement())
        docs.extend(search_brochure_for_admission_requirement())

    if "经验" in user_query or question_type == "experience_reference":
        docs.extend(search_xiaohongshu_experience_reference())

    if "资格" in user_query or question_type == "eligibility_evaluation":
        docs.extend(search_official_for_eligibility_evaluation())

    if not docs and question_type == "general_info":
        docs.append(
            {
                "source": "fallback",
                "title": "通用建议",
                "content": "未命中具体类别，建议先查看人大研招网与学院官网最新通知。",
                "confidence": 0.5,
            }
        )

    return docs
