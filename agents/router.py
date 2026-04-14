"""Routing module.

Owner: member 1 (graph flow) + member 2 (data strategy).
Responsibility: classify query into shared `QuestionType`.
Avoid putting retrieval logic or prompt rendering here.
"""

from graph.state import QuestionType


def classify_question(user_query: str) -> QuestionType:
    if "经验" in user_query:
        return "experience_reference"
    if "是否能保研" in user_query or "能不能保研" in user_query or "资格" in user_query:
        return "eligibility_evaluation"
    if "条件" in user_query or "成绩" in user_query:
        return "admission_requirement"
    if "专业" in user_query:
        return "major_info"
    return "general_info"
