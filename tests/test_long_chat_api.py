"""Long Q&A API tests."""

from fastapi.testclient import TestClient

import server


def test_long_chat_templates() -> None:
    client = TestClient(server.app)
    r = client.get("/api/long-chat/templates")
    assert r.status_code == 200
    data = r.json()
    assert "intake" in data and "report_skeleton" in data
    assert "basic" in data["intake"]
    assert "summary" in data["report_skeleton"]


def test_long_chat_clarify() -> None:
    client = TestClient(server.app)
    r = client.post("/api/long-chat/clarify", json={"goal": "想保人大金融硕士"})
    assert r.status_code == 200
    body = r.json()
    assert "questions" in body
    assert isinstance(body["questions"], list)
    assert len(body["questions"]) >= 3


def test_long_chat_report() -> None:
    client = TestClient(server.app)
    r = client.post(
        "/api/long-chat/report",
        json={
            "goal": "测试目标",
            "intake": {"basic": {"year_of_study": "大三"}},
            "use_web": False,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert "report" in body
    assert "summary" in body["report"]
    assert isinstance(body.get("latency_ms"), int)
