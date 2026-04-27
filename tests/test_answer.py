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


def test_generate_mock_answer_respects_context_packing(monkeypatch) -> None:
    monkeypatch.setenv("LLM_CONTEXT_MAX_CHARS", "3000")
    monkeypatch.setenv("LLM_CONTEXT_DOC_MAX_CHARS", "120")
    monkeypatch.setenv("LLM_CONTEXT_MAX_EXPERIENCE_DOCS", "10")
    docs = [
        {
            "source": "xiaohongshu_excel",
            "title": f"经验{i}",
            "content": "保研经验内容" * 120,
            "confidence": 0.6,
            "source_group": "experience",
            "match_score": 10,
        }
        for i in range(60)
    ]
    answer = generate_mock_answer(
        user_query="保研经验",
        question_type="experience_reference",
        retrieved_docs=docs,
    )
    assert "【上下文打包】retrieved=60" in answer
    assert "packed=" in answer
