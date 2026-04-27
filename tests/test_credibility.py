"""Credibility / ad-risk heuristics."""

from tools.credibility import build_credibility_fields, heuristic_ad_risk


def test_official_never_flagged_ad() -> None:
    f = build_credibility_fields(
        source_group="official",
        source_tag="official_pdf",
        title="财政金融学院 · 第 1 页",
        text="推免工作按学校规定执行。",
        provenance={},
    )
    assert f["suspected_ad"] is False
    assert f["credibility_level"] == "high"
    assert f["evidence_role"] == "primary_policy"


def test_experience_redirect_triggers_ad() -> None:
    text = "私信我领取资料，加微保过夏令营。"
    suspected, reasons = heuristic_ad_risk("标题", text, "experience", "xiaohongshu_excel")
    assert suspected is True
    assert len(reasons) >= 1


def test_consulting_language_triggers_ad() -> None:
    text = "全程班陪跑，一对一规划，私聊上车。"
    suspected, reasons = heuristic_ad_risk("标题", text, "experience", "xiaohongshu_excel")
    assert suspected is True


def test_web_xhs_extra_caution() -> None:
    suspected, _reasons = heuristic_ad_risk("经验", "这是一段分享。", "web", "web_xhs")
    assert suspected is True
