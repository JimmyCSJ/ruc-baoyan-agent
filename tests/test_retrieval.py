"""Retrieval unit tests.

Owner: member 3.
"""

from agents.retrieval import retrieve_documents_with_trace
from kb.tokenize import tokenize_query


def test_retrieve_major_includes_official_pdf() -> None:
    docs, trace = retrieve_documents_with_trace("我想看专业", "major_info", enable_web_search=False)
    assert docs
    assert any(doc["source"] == "official_pdf" for doc in docs)
    assert trace["stages"][0]["source_group"] == "official"
    assert trace["stages"][1]["source_group"] == "experience"


def test_retrieve_requirement_includes_official_first() -> None:
    docs, trace = retrieve_documents_with_trace("我想了解申请条件", "admission_requirement", enable_web_search=False)
    assert docs
    assert any(doc["source"] == "official_pdf" for doc in docs)
    assert trace["stages"][0]["source_group"] == "official"


def test_retrieve_experience_stage_populated() -> None:
    docs, trace = retrieve_documents_with_trace("保研经验", "experience_reference", enable_web_search=False)
    assert docs
    assert all("confidence" in doc for doc in docs)
    assert any(doc.get("source_group") == "experience" for doc in docs)


def test_kb_scope_official_excludes_experience_kb() -> None:
    docs, trace = retrieve_documents_with_trace(
        "保研面试经验",
        "experience_reference",
        enable_web_search=False,
        kb_scope="official_only",
    )
    assert trace.get("kb_scope") == "official_only"
    assert not any(d.get("source_group") == "experience" for d in docs)
    assert any(d.get("source_group") == "official" for d in docs)


def test_kb_scope_xiaohongshu_excludes_official_kb() -> None:
    docs, trace = retrieve_documents_with_trace(
        "人大保研",
        "general_info",
        enable_web_search=False,
        kb_scope="xiaohongshu_only",
    )
    assert trace.get("kb_scope") == "xiaohongshu_only"
    assert not any(d.get("source_group") == "official" for d in docs)
    assert any(d.get("source_group") == "experience" for d in docs)


def test_kb_debug_trace_lists_chunks_and_locators() -> None:
    docs, trace = retrieve_documents_with_trace(
        "中国人民大学保研申请条件",
        "admission_requirement",
        enable_web_search=False,
        kb_debug=True,
    )
    assert trace.get("query_tokens")
    assert isinstance(trace.get("docs_passed_to_generation"), list)
    assert len(trace["docs_passed_to_generation"]) == len(docs)
    for row in trace["docs_passed_to_generation"]:
        assert "locator" in row
        assert "content_preview" in row
    for st in trace["stages"]:
        for m in st["matched"]:
            assert "content_preview" in m
            assert "locator" in m


def test_web_access_primary_trace_fields(monkeypatch) -> None:
    import agents.retrieval as r

    monkeypatch.setattr(
        r,
        "search_web_via_web_access",
        lambda _q: (
            [
                {
                    "source": "web_access_ruc",
                    "title": "RUC",
                    "content": "政策条款\n链接：https://www.ruc.edu.cn/x",
                    "confidence": 0.72,
                }
            ],
            {"used": True, "failure_reason": "", "strategy": "web_access_primary"},
        ),
    )
    monkeypatch.setattr(r, "search_web_vertical", lambda _q: [])
    docs, trace = retrieve_documents_with_trace("人大推免政策", "admission_requirement", enable_web_search=True)
    assert any(str(d.get("source", "")).startswith("web_access") for d in docs)
    assert trace.get("web_access_used") is True
    assert trace.get("web_fallback_used") is False
    assert trace.get("web_failure_reason", "") == ""


def test_web_access_fallback_trace_fields(monkeypatch) -> None:
    import agents.retrieval as r

    monkeypatch.setattr(
        r,
        "search_web_via_web_access",
        lambda _q: ([], {"used": False, "failure_reason": "proxy_unreachable", "strategy": "web_access_primary"}),
    )
    monkeypatch.setattr(
        r,
        "search_web_vertical",
        lambda _q: [{"source": "web_general", "title": "legacy", "content": "x\n链接：https://a.b", "confidence": 0.48}],
    )
    docs, trace = retrieve_documents_with_trace("知乎 保研", "general_info", enable_web_search=True)
    assert docs
    assert trace.get("web_fallback_used") is True
    assert "proxy_unreachable" in str(trace.get("web_failure_reason", ""))


def test_tokenize_query_adds_chinese_ngrams() -> None:
    tokens = tokenize_query("保研面试经验")
    assert "保研面试经验" in tokens
    # ngram expansion improves non-exact lexical recall.
    assert "保研" in tokens
    assert "面试" in tokens


def test_xiaohongshu_only_uses_larger_default_top_k() -> None:
    docs, trace = retrieve_documents_with_trace(
        "保研经验分享",
        "general_info",
        enable_web_search=False,
        kb_scope="xiaohongshu_only",
    )
    assert docs
    exp_stage = next(st for st in trace["stages"] if st["source_group"] == "experience")
    assert exp_stage["top_k"] >= 100
