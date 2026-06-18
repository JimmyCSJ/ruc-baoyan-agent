"""Concrete credibility/ad-risk examples + impact notes."""

from tools.credibility import build_credibility_fields, credibility_impact_note


def _eval(source_group: str, source_tag: str, title: str, text: str) -> dict:
    fields = build_credibility_fields(
        source_group=source_group,
        source_tag=source_tag,
        title=title,
        text=text,
        provenance={},
    )
    impact = credibility_impact_note(
        source_group=source_group,
        suspected_ad=bool(fields.get("suspected_ad", False)),
        credibility_level=str(fields.get("credibility_level", "")),
    )
    return {"fields": fields, "impact": impact}


def test_case_hard_sell_ad_language() -> None:
    r = _eval(
        "experience",
        "xiaohongshu_excel",
        "上岸包过冲刺营",
        "名额有限！保过/不过退费！私聊加vx领取内部资料，一对一陪跑。",
    )
    assert r["fields"]["suspected_ad"] is True
    assert r["fields"]["credibility_level"] == "low"
    assert r["impact"]["affects_ranking"] is False
    assert r["impact"]["affects_presentation"] is True


def test_case_soft_sell_consulting_language() -> None:
    r = _eval(
        "experience",
        "xiaohongshu_excel",
        "保研规划复盘",
        "如果你也想要一对一规划/陪跑，我可以提供咨询。欢迎私信了解。",
    )
    assert r["fields"]["suspected_ad"] is True
    assert r["fields"]["credibility_level"] == "low"


def test_case_normal_experience_sharing() -> None:
    r = _eval(
        "experience",
        "xiaohongshu_excel",
        "人大财金夏令营面试复盘（2025）",
        "我投了简历后大概两周收到通知。面试主要问研究兴趣、简历项目、英文自我介绍。"
        "建议提前准备一页研究计划和常见问题清单。",
    )
    assert r["fields"]["suspected_ad"] is False
    assert r["fields"]["credibility_level"] == "medium"


def test_case_official_policy_text() -> None:
    r = _eval(
        "official",
        "official_pdf",
        "财政金融学院优秀应届本科毕业生免试攻读研究生推荐综合素质拓展评价办法（2025年修订） · 第 1 页",
        "申请人须按规定提交材料。学院将对材料进行审核，未按要求提交者不予受理。",
    )
    assert r["fields"]["suspected_ad"] is False
    assert r["fields"]["credibility_level"] == "high"

