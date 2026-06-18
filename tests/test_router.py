"""Router unit tests.

Owner: member 3.
"""

from agents.router import classify_question


def test_classify_major_info() -> None:
    assert classify_question("人大有哪些专业方向？") == "major_info"


def test_classify_admission_requirement() -> None:
    assert classify_question("申请条件和成绩要求是什么？") == "admission_requirement"


def test_classify_experience_reference() -> None:
    assert classify_question("有没有学长学姐经验？") == "experience_reference"


def test_classify_eligibility_evaluation() -> None:
    assert classify_question("我这个成绩能不能保研，资格怎么样？") == "eligibility_evaluation"
