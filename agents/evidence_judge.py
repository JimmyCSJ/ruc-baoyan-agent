"""Model-assisted evidence review for user-facing source cards."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List

from openai import OpenAI

from config import get_settings

_LABELS = {"官方依据", "高价值经验", "经验线索", "待核验线索", "低可信线索"}


def _snippet(text: Any, limit: int = 700) -> str:
    body = re.sub(r"\s+", " ", str(text or "")).strip()
    return body[:limit]


def _json_object(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _level(text: str, default: str) -> str:
    val = str(text or "").strip()
    return val[:24] if val else default


def _explanation(text: str, default: str) -> str:
    val = re.sub(r"\s+", " ", str(text or "")).strip()
    return val[:160] if val else default


def _fallback_label(doc: Dict[str, Any]) -> tuple[str, int]:
    if doc.get("suspected_ad"):
        return "低可信线索", 1
    if doc.get("source_group") == "official":
        return "官方依据", 5
    if doc.get("source_group") == "web":
        return "待核验线索", 2
    label = str(doc.get("evidence_quality_label") or "")
    if "高价值经验" in label:
        return "高价值经验", 4
    if doc.get("source_group") == "experience":
        return "经验线索", 3
    return "待核验线索", 2


def _fallback_review(user_query: str, doc: Dict[str, Any]) -> Dict[str, Any]:
    label, stars = _fallback_label(doc)
    title = str(doc.get("title") or "")
    content = str(doc.get("content") or "")
    haystack = f"{title}\n{content}"
    query_terms = [x for x in re.split(r"\s+", user_query.strip()) if len(x) >= 2]
    query_terms += re.findall(r"[\u4e00-\u9fff]{2,8}", user_query)
    important_terms = re.findall(
        r"[\u4e00-\u9fff]*(?:学院|专业|方向|项目|笔试|面试|材料|推免|保研|夏令营|预推免)[\u4e00-\u9fff]*",
        user_query,
    )
    query_terms += important_terms
    compact_query = re.sub(r"\s+", "", user_query)
    query_terms += [compact_query[i : i + n] for n in (2, 3, 4) for i in range(max(0, len(compact_query) - n + 1))]
    matched = any(t and t in haystack for t in query_terms[:16]) if query_terms else bool(haystack)
    ad_reasons = [str(x) for x in list(doc.get("ad_risk_reasons") or []) if str(x).strip()]
    has_year = bool(re.search(r"20\d{2}", haystack))
    has_detail = bool(re.search(r"学院|专业|方向|项目|笔试|面试|材料|流程|题型|排名|成绩|夏令营|预推免", haystack))

    if doc.get("source_group") == "official":
        evidence_level = "强"
        truth_level = "可信"
        usage = "可作为正式规则和政策依据；若与经验内容冲突，以官方材料为准。"
    elif ad_reasons:
        evidence_level = "较弱"
        truth_level = "存疑"
        usage = "只能作为低权重线索，不能写成确定事实。"
    elif label == "高价值经验":
        evidence_level = "较强"
        truth_level = "较可信"
        usage = "可用于形成准备建议，但不能替代学院正式通知。"
    elif label == "经验线索":
        evidence_level = "中等" if has_detail else "较弱"
        truth_level = "需交叉核验"
        usage = "可作为经验参考，关键结论仍需结合官方材料或更多样本。"
    else:
        evidence_level = "较弱"
        truth_level = "需核验"
        usage = "适合发现方向，不应单独支撑结论。"

    if not has_year and doc.get("source_group") in ("experience", "web"):
        ad_reasons.append("缺少明确年份")

    return {
        "evidence_model_label": label,
        "evidence_model_stars": stars,
        "evidence_model_review": {
            "label": label,
            "stars": stars,
            "target_match": {
                "level": "基本匹配" if matched else "弱匹配",
                "explanation": "资料与用户问题中的关键词或问题类型有交集。"
                if matched
                else "资料未明显对应用户提到的学院、项目或问题类型。",
            },
            "evidence_strength": {
                "level": evidence_level,
                "explanation": "资料包含明确来源或可识别细节。"
                if has_detail or doc.get("source_group") == "official"
                else "资料缺少学院、项目、流程、年份或题型等可核验细节。",
            },
            "truthfulness_judgment": {
                "level": truth_level,
                "explanation": "未发现明显推广或夸张承诺。"
                if not ad_reasons
                else "存在需要降权处理的风险信号：" + "；".join(ad_reasons[:3]),
            },
            "usage_guidance": usage,
            "risk_notes": ad_reasons[:5],
            "review_mode": "rule_fallback",
        },
    }


def _sanitize_review(raw: Dict[str, Any], user_query: str, doc: Dict[str, Any]) -> Dict[str, Any]:
    fallback = _fallback_review(user_query, doc)["evidence_model_review"]
    label = str(raw.get("label") or fallback["label"]).strip()
    if label not in _LABELS:
        label = str(fallback["label"])
    try:
        stars = int(raw.get("stars", fallback["stars"]))
    except (TypeError, ValueError):
        stars = int(fallback["stars"])
    stars = max(1, min(5, stars))

    def block(name: str, default_level: str, default_explanation: str) -> Dict[str, str]:
        src = raw.get(name) if isinstance(raw.get(name), dict) else {}
        return {
            "level": _level(src.get("level", ""), default_level),
            "explanation": _explanation(src.get("explanation", ""), default_explanation),
        }

    risk_raw = raw.get("risk_notes", [])
    risk_notes = [str(x).strip()[:80] for x in risk_raw if str(x).strip()] if isinstance(risk_raw, list) else []
    return {
        "evidence_model_label": label,
        "evidence_model_stars": stars,
        "evidence_model_review": {
            "label": label,
            "stars": stars,
            "target_match": block(
                "target_match",
                fallback["target_match"]["level"],
                fallback["target_match"]["explanation"],
            ),
            "evidence_strength": block(
                "evidence_strength",
                fallback["evidence_strength"]["level"],
                fallback["evidence_strength"]["explanation"],
            ),
            "truthfulness_judgment": block(
                "truthfulness_judgment",
                fallback["truthfulness_judgment"]["level"],
                fallback["truthfulness_judgment"]["explanation"],
            ),
            "usage_guidance": _explanation(raw.get("usage_guidance", ""), fallback["usage_guidance"]),
            "risk_notes": risk_notes[:5],
            "review_mode": "llm",
        },
    }


def _review_batch_with_llm(user_query: str, batch: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    settings = get_settings()
    if not settings.enable_real_llm or not settings.moark_api_key:
        return {}

    items = []
    for idx, doc in enumerate(batch):
        items.append(
            {
                "id": idx,
                "title": str(doc.get("title") or "")[:180],
                "snippet": _snippet(doc.get("content")),
                "source_group": doc.get("source_group", "other"),
                "source": doc.get("source", ""),
                "kb_group": doc.get("kb_group", ""),
                "year_hint": ", ".join(re.findall(r"20\d{2}", f"{doc.get('title','')} {doc.get('content','')}")[:4]),
                "raw_system_flags": {
                    "suspected_ad": bool(doc.get("suspected_ad", False)),
                    "ad_risk_reasons": list(doc.get("ad_risk_reasons") or [])[:5],
                    "source_type": doc.get("source_type", ""),
                    "old_quality_label": doc.get("evidence_quality_label", ""),
                    "freshness": doc.get("freshness", ""),
                },
            }
        )

    prompt = (
        "你是中国人民大学保研信息真伪与证据质量审查员。你要逐条审查资料，帮助用户判断哪些信息可靠、哪些只能作为线索。\n"
        "不要预设学院或项目；用户问哪个学院/项目，就按用户问题和资料内容识别。用户没说清楚时，要标注匹配不明确。\n"
        "你必须结合：用户问题、资料标题、资料片段、来源类型、年份线索、推广风险信号，以及你对中文招生/经验帖常见表达的判断。\n"
        "你不能凭空补事实，不能因为文字像真的就当成官方结论。\n\n"
        "标签只能从这 5 个中选：官方依据、高价值经验、经验线索、待核验线索、低可信线索。\n"
        "星级规则：官方依据=5；高价值经验=4；经验线索=3；待核验线索=2；低可信线索=1。\n"
        "判断规则：\n"
        "1. 官方文件、招生简章、学院通知，且与问题相关，标为官方依据。\n"
        "2. 经验资料若有明确学院/项目/专业、年份、流程、题型、时间线或准备细节，才可标高价值经验。\n"
        "3. 只有泛泛描述、缺少年份或项目细节的经验，标经验线索或待核验线索。\n"
        "4. 联网来源没有官方背书时，通常最多是待核验线索；若很具体且像真人经验，可给经验线索，但不能给官方依据。\n"
        "5. 出现卖课、资料包、私信、+V、手机号、群号、保过、内部渠道、夸张承诺，必须降为低可信线索。\n"
        "6. 资料与用户问题的学院、项目、专业或问题类型不匹配时，必须降级。\n"
        "7. 对每条资料都要说明：匹配度、证据强度、可信判断、使用建议。\n\n"
        "只输出 JSON，不要 Markdown。格式：\n"
        "{\"items\":[{\"id\":0,\"label\":\"高价值经验\",\"stars\":4,"
        "\"target_match\":{\"level\":\"高度匹配\",\"explanation\":\"...\"},"
        "\"evidence_strength\":{\"level\":\"较强\",\"explanation\":\"...\"},"
        "\"truthfulness_judgment\":{\"level\":\"较可信\",\"explanation\":\"...\"},"
        "\"usage_guidance\":\"...\",\"risk_notes\":[]}]}\n\n"
        f"用户问题：{user_query}\n"
        f"资料列表：{json.dumps(items, ensure_ascii=False)}"
    )

    client = OpenAI(base_url=settings.moark_base_url, api_key=settings.moark_api_key, max_retries=0)
    resp = client.chat.completions.create(
        model=settings.moark_model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=3500,
        temperature=0.1,
        top_p=0.6,
        **({"extra_body": settings.llm_extra_body} if settings.llm_extra_body else {}),
    )
    data = _json_object(resp.choices[0].message.content or "")
    out: Dict[int, Dict[str, Any]] = {}
    rows = data.get("items")
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            idx = int(row.get("id"))
        except (TypeError, ValueError):
            continue
        if 0 <= idx < len(batch):
            out[idx] = _sanitize_review(row, user_query, batch[idx])
    return out


def review_evidence_with_model(user_query: str, docs: Iterable[Dict[str, Any]], batch_size: int = 8) -> List[Dict[str, Any]]:
    """Attach model evidence review to every returned source.

    When the model is unavailable, every source still receives the same output
    shape via deterministic fallback so the UI and prompts remain stable.
    """
    reviewed: List[Dict[str, Any]] = [dict(d) for d in docs]
    if not reviewed:
        return reviewed

    for start in range(0, len(reviewed), batch_size):
        batch = reviewed[start : start + batch_size]
        llm_reviews: Dict[int, Dict[str, Any]] = {}
        try:
            llm_reviews = _review_batch_with_llm(user_query, batch)
        except Exception:
            llm_reviews = {}
        for i, doc in enumerate(batch):
            fields = llm_reviews.get(i) or _fallback_review(user_query, doc)
            reviewed[start + i].update(fields)
    return reviewed
