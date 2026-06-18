"""Web search query expansion (no network)."""

from tools.web_search import expand_query_variants


def test_expand_replaces_ruc_shorthand() -> None:
    v = expand_query_variants("中国人民大学保研申请条件有哪些？")
    assert any("人大" in x and "中国人民大学" not in x for x in v)


def test_expand_non_empty() -> None:
    assert expand_query_variants("  ") == []
    assert len(expand_query_variants("测试问题？")) >= 1
