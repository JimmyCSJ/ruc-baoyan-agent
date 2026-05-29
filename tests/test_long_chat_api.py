"""Long-plan API tests."""

from fastapi.testclient import TestClient

import server


def _minimal_intake_flat() -> dict:
    return {
        "use_web": False,
        "current_school": "中国人民大学",
        "grade_year": "大三",
        "college": "财政金融学院",
        "major": "金融学",
        "gpa": "3.7",
        "major_rank_percentile": "前15%",
        "target_destination": "中国人民大学 · 经济金融方向 · 专硕",
        "english_scores": "六级 580",
        "research_and_competitions": "",
        "internships": "",
        "region_preference": "",
        "student_work_clubs": "",
        "career_path_3_5y": "",
        "expected_roles_or_industry": "",
        "admission_prep_stage": "",
        "main_concerns": "",
    }


def test_long_chat_templates() -> None:
    client = TestClient(server.app)
    r = client.get("/api/long-chat/templates")
    assert r.status_code == 200
    data = r.json()
    assert "intake" in data and "report_skeleton" in data
    assert "required" in data["intake"]
    assert "direction_summary" in data["report_skeleton"]


def test_long_chat_report() -> None:
    client = TestClient(server.app)
    r = client.post("/api/long-chat/report", json=_minimal_intake_flat())
    assert r.status_code == 200
    body = r.json()
    assert "report" in body
    assert "report_markdown" in body
    rep = body["report"]
    assert "advantages" in rep or "timeline" in rep
    assert rep.get("_generation") in ("llm", "fallback", "partial")
    assert isinstance(body.get("latency_ms"), int)


def test_long_chat_report_nested_body() -> None:
    client = TestClient(server.app)
    payload = {
        "use_web": False,
        "required": {
            "current_school": "中国人民大学",
            "grade_year": "大二",
            "college": "财政金融学院",
            "major": "金融学",
            "gpa": "3.6",
            "major_rank_percentile": "前20%",
            "target_destination": "中国人民大学 · 金融 · 专硕",
            "english_scores": "雅思 7.0",
        },
        "optional": {"main_concerns": "时间紧张"},
    }
    r = client.post("/api/long-chat/report", json=payload)
    assert r.status_code == 200


def test_long_chat_report_validation() -> None:
    client = TestClient(server.app)
    r = client.post(
        "/api/long-chat/report",
        json={"use_web": False, "current_school": "中国人民大学"},
    )
    assert r.status_code == 422


def test_long_chat_report_stream_returns_ndjson() -> None:
    client = TestClient(server.app)
    r = client.post("/api/long-chat/report/stream", json=_minimal_intake_flat())
    assert r.status_code == 200
    ct = r.headers.get("content-type", "")
    assert "ndjson" in ct or "json" in ct


def test_long_chat_report_pdf_returns_binary_or_error() -> None:
    client = TestClient(server.app)
    r = client.post("/api/long-chat/report/pdf", json=_minimal_intake_flat())
    assert r.status_code in (200, 501, 500)
    if r.status_code == 200:
        assert r.headers.get("content-type", "").startswith("application/pdf")


def test_long_chat_report_html_returns_html_document() -> None:
    client = TestClient(server.app)
    r = client.post(
        "/api/long-chat/report/html",
        json={"report_markdown": "# 测试报告\n\n## 一、目标院校可选择项目\n\n内容"},
    )
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("text/html")
    text = r.text
    assert "中国人民大学保研规划报告" in text
    assert "ruc-logo" in text
