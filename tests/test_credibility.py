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


def test_hidden_contact_and_material_pack_triggers_ad_risk() -> None:
    text = "真诚分享人大保研经历，完整资料包可 si 我，裙号 123456，电话 13800138000，V：abc123。"
    suspected, reasons = heuristic_ad_risk("经验贴", text, "experience", "xiaohongshu_excel")
    assert suspected is True
    assert any("联系方式" in r or "引流" in r or "资料" in r for r in reasons)


def test_specific_real_person_experience_can_remain_medium_without_ad() -> None:
    text = "2025 年参加人大商学院会计夏令营，上午英文自我介绍，下午围绕简历科研经历追问，未提到资料售卖。"
    fields = build_credibility_fields(
        source_group="experience",
        source_tag="xiaohongshu_excel",
        title="人大商学院会计夏令营面试复盘",
        text=text,
        provenance={"excel_row": 12},
    )
    assert fields["suspected_ad"] is False
    assert fields["credibility_level"] == "medium"
