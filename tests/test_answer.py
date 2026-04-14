"""Answer unit tests.

Owner: member 3.
"""

from agents.answer import generate_mock_answer


def test_generate_mock_answer_contains_core_fields() -> None:
    docs = [
        {
            "source": "official_site",
            "title": "测试标题",
            "content": "测试内容",
            "confidence": 0.9,
        }
    ]
    answer = generate_mock_answer(
        user_query="我想看申请条件",
        question_type="admission_requirement",
        retrieved_docs=docs,
    )

    assert "问题分类" in answer
    assert "测试标题" in answer
    assert "测试内容" in answer
