"""Xiaohongshu Excel KB verify flow (counts, samples, match explain, row diagnosis)."""

from kb.experience_verify import build_xiaohongshu_verify_report
from tools.xiaohongshu_excel_kb import rebuild_kb


def test_verify_report_counts_and_five_samples() -> None:
    rebuild_kb()
    r = build_xiaohongshu_verify_report("", top_k=8, sample_count=5)
    assert r["counts"]["indexed_chunks"] >= 1
    assert r["counts"]["pandas_rows"] >= r["counts"]["indexed_chunks"]
    assert len(r["samples_first_chunks"]) == min(5, r["counts"]["indexed_chunks"])
    for s in r["samples_first_chunks"]:
        assert "excel_row" in s
        assert "indexed_text_preview" in s


def test_verify_matched_rows_include_token_explanation() -> None:
    rebuild_kb()
    r = build_xiaohongshu_verify_report("中国人民大学 保研", top_k=5)
    assert r["matched_rows"]
    row0 = r["matched_rows"][0]
    assert "matched_tokens" in row0
    assert "why_matched" in row0
    assert "excel_row" in row0
    assert r["retrieval_mode"] in ("lexical_hits_only", "fallback_first_rows_no_token_hits")


def test_verify_diagnose_invalid_row() -> None:
    rebuild_kb()
    r = build_xiaohongshu_verify_report("x", check_excel_row=999999)
    d = r.get("row_diagnosis") or {}
    assert d.get("category") == "not_in_sheet"
    assert d.get("found_in_index") is False


def test_verify_diagnose_first_sample_row() -> None:
    rebuild_kb()
    base = build_xiaohongshu_verify_report("", sample_count=1)
    row = base["samples_first_chunks"][0]["excel_row"]
    r = build_xiaohongshu_verify_report("保研 经验 人大", top_k=8, check_excel_row=int(row))
    d = r["row_diagnosis"]
    assert d["found_in_index"] is True
    assert d["category"] in (
        "ok_in_top_k",
        "scoring_below_top_k",
        "scoring_zero_hits",
        "chunking_truncation",
        "scoring_fallback_order",
    )
