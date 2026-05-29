"""Credibility, freshness, and promotional-risk heuristics for retrieved evidence."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Literal, Tuple

SourceType = Literal["official_school_document", "experience_note", "web_citation", "other"]
CredibilityLevel = Literal["high", "medium", "low"]
FreshnessHint = Literal["unknown", "indexed_campus_doc", "possibly_outdated", "web_unverified"]
EvidenceRole = Literal["primary_policy", "supplementary_experience", "supplementary_web", "system"]

_MARKETING_RE = re.compile(
    r"限时|秒杀|抢位|名额有限|仅剩|火热报名|独家|内部通道|上岸密训|上岸包过|保过|包过|稳过|"
    r"100%|百分百录取|不过退费|原价\d|现价\d|限时优惠|钜惠|私信领取|免费领取|0元|"
    r"咨询(?!学院|招办)|陪跑|一对一辅导|一对一规划|一对一陪跑|付费(?!学费)|辅导课|全程班|内部资料|资料包|资料合集|真题包|笔记包|上岸资料",
    re.I,
)
_REDIRECT_RE = re.compile(
    r"私聊|私信|私我|si\s*我|s\s*i\s*我|加微|加\s*w(?:x|信)?|加wx|加vx|加v\b|加\s*v|"
    r"\+v|\+vx|\+wx|v[:：][A-Za-z0-9_-]{3,}|vx[:：]|\bwx[:：]|威信|薇信|微\s*信|"
    r"扣扣|qq[:：]|\bq[:：]|群号|裙号|进群|小窗|扫码|二维码|关注公号|回复关键词|"
    r"戳链接|点我主页|加我|联系方式在|看简介|引流|主页有方式|主页置顶|评论区见|置顶笔记",
    re.I,
)
_CONTACT_RE = re.compile(
    r"(?<!\d)1[3-9]\d{9}(?!\d)|(?:电话|手机|手机号|联系方式|联系我|call|tel)[:：]?\s*\d{6,}|"
    r"(?:微信|vx|wx|v|qq|q)[:：]?\s*[A-Za-z0-9_-]{4,}",
    re.I,
)
_UNREALISTIC_RE = re.compile(
    r"保证录取|保研稳了|躺着进|绿色通道|内推名额|保录|代操作|代写文书|付费保过|"
    r"稳上岸|必过|不过全退",
    re.I,
)
_NO_ANCHOR_RE = re.compile(r"20\d{2}|人大|财政金融|RUC|推免|夏令营|预推免", re.I)
_POLICY_STRONG_EXP_RE = re.compile(
    r"不要求|不需要|没有要求|无要求|不重要|无所谓|肯定能|一定过|百分百",
    re.I,
)


def _short_body(text: str, threshold: int = 72) -> bool:
    t = re.sub(r"\s+", "", (text or "").strip())
    return len(t) < threshold


def heuristic_ad_risk(
    title: str,
    content: str,
    source_group: str,
    source_tag: str = "",
) -> Tuple[bool, List[str]]:
    """Return (suspected_ad, reasons)."""
    text = f"{title}\n{content}"
    reasons: List[str] = []

    if _MARKETING_RE.search(text):
        reasons.append("营销话术")
    if _REDIRECT_RE.search(text):
        reasons.append("引流/私聊/加好友提示")
    if _CONTACT_RE.search(text):
        reasons.append("隐藏联系方式或站外引流")
    if _UNREALISTIC_RE.search(text):
        reasons.append("过度承诺或不实暗示")

    if source_group in ("experience", "web") and _short_body(content, threshold=48):
        reasons.append("正文过短，缺乏可核验细节")

    if source_group == "experience":
        blob = f"{title}\n{content}"
        if len(re.sub(r"\s+", "", blob)) >= 40 and not _NO_ANCHOR_RE.search(blob):
            reasons.append("缺少具体年份/学校/流程锚点，难以与正式文件对齐核实")

    if source_tag == "web_xhs":
        if not reasons:
            reasons.append("小红书网页检索结果商业推广风险相对较高")
        elif "小红书网页" not in "".join(reasons):
            reasons.append("小红书网页类结果需额外警惕推广")

    suspected = bool(reasons)
    if source_group == "official":
        suspected = False
        reasons = []
    return suspected, reasons


def experience_official_conflict_hints(title: str, content: str, official_concat: str) -> List[str]:
    """Lightweight consistency checks: experience must not override PDFs; flag rough contradictions."""
    if not official_concat.strip():
        return []
    exp = f"{title}\n{content}"
    off = official_concat
    hints: List[str] = []

    if re.search(r"绩点|学分|成绩|GPA", off) and re.search(
        r"(不要求|不需要|无要求|不重要).{0,16}(绩点|成绩|学分|排名|GPA)|绩点[^。]{0,12}(不重要|无所谓|没用)",
        exp,
    ):
        hints.append("经验出现弱化成绩/要求的措辞，但索引到的正式文件含成绩类要求——以 PDF 原文为准")
    if re.search(r"英语|四六级|CET", off) and re.search(
        r"(不要求|不需要|无要求|不重要).{0,16}(四六级|英语|CET)|四六级[^。]{0,12}(不重要|无所谓|没用)",
        exp,
    ):
        hints.append("经验弱化英语/四六级要求，但正式文件出现相关表述——以 PDF 原文为准")
    if _POLICY_STRONG_EXP_RE.search(exp) and re.search(
        r"须|必须|应当|不得|应提交|申请材料",
        off,
    ):
        hints.append("经验含笼统或弱化规则表述，而正式文件出现约束性措辞——以 PDF 原文为准")

    exp_years = set(re.findall(r"(20\d{2})", exp))
    off_years = set(re.findall(r"(20\d{2})", off))
    if exp_years and off_years and exp_years.isdisjoint(off_years):
        hints.append("经验条目的年份与已检索正式文件中的年份集合不一致，可能过时或非本院版本")

    return hints


def enrich_experience_against_official(
    experience_docs: List[Dict[str, Any]],
    official_docs: List[Dict[str, Any]],
) -> None:
    """Mutate experience docs with extra ad_risk / credibility hints (inspectable, no silent rerank)."""
    if not experience_docs or not official_docs:
        return
    official_concat = "\n".join(str(d.get("content") or "") for d in official_docs)[:14000]
    for d in experience_docs:
        if str(d.get("source_group")) != "experience":
            continue
        hints = experience_official_conflict_hints(
            str(d.get("title") or ""),
            str(d.get("content") or ""),
            official_concat,
        )
        if not hints:
            continue
        prev = list(d.get("ad_risk_reasons") or [])
        merged_reasons = prev + [h for h in hints if h not in prev]
        d["ad_risk_reasons"] = merged_reasons
        if merged_reasons and not d.get("suspected_ad"):
            d["suspected_ad"] = True
        if d.get("credibility_level") == "medium":
            d["credibility_level"] = "low"


def _freshness_official(title: str, provenance: Dict[str, Any]) -> FreshnessHint:
    t = title or ""
    if re.search(r"20(2[4-9]|3\d)", t):
        return "indexed_campus_doc"
    return "unknown"


def _has_specific_experience_anchors(title: str, text: str) -> bool:
    blob = f"{title}\n{text}"
    has_year = bool(re.search(r"20\d{2}", blob))
    has_school_or_project = bool(re.search(r"人大|中国人民大学|学院|夏令营|预推免|九推|推免|专业|方向", blob))
    has_detail = bool(re.search(r"笔试|面试|题型|自我介绍|科研|实习|排名|成绩|材料|导师|英文|追问", blob))
    return has_year and has_school_or_project and has_detail and len(re.sub(r"\s+", "", text)) >= 80


def _evidence_quality(
    *,
    source_group: str,
    source_tag: str,
    title: str,
    text: str,
    suspected_ad: bool,
) -> Dict[str, Any]:
    if source_group == "official":
        if re.search(r"推免|免试|推荐|综合素质|科研能力", title):
            return {
                "evidence_quality_tier": 1,
                "evidence_quality_label": "官方确定",
                "credibility_notes": ["正式文件，可作为政策和规则的主要依据。"],
            }
        return {
            "evidence_quality_tier": 2,
            "evidence_quality_label": "官方相关·需转换口径",
            "credibility_notes": ["正式招生/项目文件可信度高，但若用户问保研，应注意它可能是考研或招生简章口径。"],
        }

    if source_group == "experience":
        if suspected_ad:
            return {
                "evidence_quality_tier": 5,
                "evidence_quality_label": "低可信·疑似推广",
                "credibility_notes": ["可作为线索参考，但因存在推广/引流信号，不能直接作为事实依据。"],
            }
        if source_tag == "public_info_baoyan_basics_md":
            return {
                "evidence_quality_tier": 3,
                "evidence_quality_label": "通识说明",
                "credibility_notes": ["适合解释保研流程和概念，不代表人大某学院当年政策。"],
            }
        if _has_specific_experience_anchors(title, text):
            return {
                "evidence_quality_tier": 3,
                "evidence_quality_label": "高价值经验",
                "credibility_notes": ["有年份、项目或流程细节，适合做准备参考，但仍是个人经验。"],
            }
        return {
            "evidence_quality_tier": 4,
            "evidence_quality_label": "经验线索",
            "credibility_notes": ["可参考，但样本有限或细节不足，需要结合其他来源核验。"],
        }

    if source_group == "web":
        if suspected_ad or source_tag == "web_xhs":
            return {
                "evidence_quality_tier": 5,
                "evidence_quality_label": "低可信·网页推广风险",
                "credibility_notes": ["联网网页未验证，且存在平台或推广风险，只能作为线索。"],
            }
        return {
            "evidence_quality_tier": 4,
            "evidence_quality_label": "网页线索",
            "credibility_notes": ["联网内容未验证，可用于发现线索，不能覆盖本地知识库和官方文件。"],
        }

    return {
        "evidence_quality_tier": 5,
        "evidence_quality_label": "低可信线索",
        "credibility_notes": ["来源类型不明确，仅作辅助线索。"],
    }


def build_credibility_fields(
    *,
    source_group: str,
    source_tag: str,
    title: str,
    text: str,
    provenance: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    prov = dict(provenance or {})
    suspected_ad, ad_reasons = heuristic_ad_risk(title, text, source_group, source_tag)
    quality = _evidence_quality(
        source_group=source_group,
        source_tag=source_tag,
        title=title,
        text=text,
        suspected_ad=suspected_ad,
    )

    if source_group == "official":
        return {
            "source_type": "official_school_document",
            "credibility_level": "high",
            "suspected_ad": False,
            "freshness": _freshness_official(title, prov),
            "evidence_role": "primary_policy",
            "ad_risk_reasons": [],
            **quality,
        }

    if source_group == "experience":
        cred: CredibilityLevel = "low" if suspected_ad else "medium"
        return {
            "source_type": "experience_note",
            "credibility_level": cred,
            "suspected_ad": suspected_ad,
            "freshness": "possibly_outdated",
            "evidence_role": "supplementary_experience",
            "ad_risk_reasons": ad_reasons,
            **quality,
        }

    if source_group == "web":
        cred_w: CredibilityLevel = "low" if suspected_ad or source_tag in ("web_xhs",) else "medium"
        return {
            "source_type": "web_citation",
            "credibility_level": cred_w,
            "suspected_ad": suspected_ad,
            "freshness": "web_unverified",
            "evidence_role": "supplementary_web",
            "ad_risk_reasons": ad_reasons,
            **quality,
        }

    return {
        "source_type": "other",
        "credibility_level": "low",
        "suspected_ad": suspected_ad,
        "freshness": "unknown",
        "evidence_role": "system",
        "ad_risk_reasons": ad_reasons,
        **quality,
    }


def merge_credibility_into_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Attach or refresh credibility fields (e.g. after web enrichment)."""
    sg = str(doc.get("source_group") or "other")
    st = str(doc.get("source") or "")
    title = str(doc.get("title") or "")
    content = str(doc.get("content") or "")
    prov = doc.get("provenance") if isinstance(doc.get("provenance"), dict) else {}
    fields = build_credibility_fields(
        source_group=sg,
        source_tag=st,
        title=title,
        text=content,
        provenance=prov,
    )
    out = dict(doc)
    out.update(fields)
    return out


def credibility_impact_note(
    *,
    source_group: str,
    suspected_ad: bool,
    credibility_level: str,
) -> Dict[str, Any]:
    """Explain how credibility flags affect answer presentation and ranking in this project."""
    # Current design: scoring/ranking is lexical-only; credibility is used for transparency + answer guardrails.
    affects_ranking = False
    affects_presentation = True
    rules: List[str] = []

    if source_group == "official":
        rules.append("正式文件：作为「官方结论」唯一依据，优先展示；不会被标记为 suspected_ad。")
    elif source_group == "experience":
        rules.append("经验：只能作为「经验参考」补充，不得覆盖正式文件结论。")
        if suspected_ad:
            rules.append("suspected_ad=true：不得写入「官方结论」当作事实；只能在「经验参考」谨慎转述并提示警惕营销/核实。")
    elif source_group == "web":
        rules.append("网页：默认未验证，仅作线索；suspected_ad=true 时同样不得作为政策事实。")
    else:
        rules.append("其他来源：默认低可信，仅供线索。")

    if credibility_level == "low":
        rules.append("credibility_level=low：回答中应更强提示不确定性/需核验。")

    return {
        "affects_ranking": affects_ranking,
        "affects_presentation": affects_presentation,
        "notes": rules,
    }
