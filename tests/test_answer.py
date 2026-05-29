"""Answer unit tests.

Owner: member 3.
"""

from agents.answer import ensure_answer_completion, generate_mock_answer


def test_generate_mock_answer_contains_core_fields() -> None:
    docs = [
        {
            "source": "official_site",
            "title": "测试标题",
            "content": "测试内容",
            "confidence": 0.9,
        }
    ]
    answer, refs = generate_mock_answer(
        user_query="我想看申请条件",
        question_type="admission_requirement",
        retrieved_docs=docs,
    )

    assert "问题分类" in answer
    assert "【总结回答】" in answer
    assert "【不确定性" in answer
    assert "测试标题" in answer
    assert "测试内容" in answer
    assert isinstance(refs, list)


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
    answer, refs = generate_mock_answer(
        user_query="保研经验",
        question_type="experience_reference",
        retrieved_docs=docs,
    )
    assert "【上下文打包】retrieved=60" in answer
    assert "packed=" in answer
    assert isinstance(refs, list)


def test_ensure_answer_completion_repairs_truncated_action_list() -> None:
    raw = (
        "### 【总结回答】\n"
        "这是一个较长回答。\n\n"
        "*本周你可以立即着手的三件事*：\n\n"
        "*(动作)* 盘点自己高数线代概率论的掌握程度并列出薄弱章节清单 /\n\n"
        "### 【不确定性 / 冲突说明】\n"
        "暂无。"
    )

    fixed = ensure_answer_completion(
        raw,
        user_query="中国人民大学财政金融学院金融、金融科技、保险、税务等方向近年招收规模和考核差异怎么看？",
        force=True,
    )

    assert "本周可执行动作" in fixed
    assert "方向对比表" in fixed
    assert "模型原始输出疑似在行动清单附近被截断" in fixed
