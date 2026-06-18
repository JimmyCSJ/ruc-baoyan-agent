"""Authentication and per-user profile API tests."""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server
from auth import service


@pytest.fixture()
def auth_client(tmp_path, monkeypatch):
    data_dir = tmp_path / "auth_data"
    monkeypatch.setenv("AUTH_DATA_DIR", str(data_dir))
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setattr(service, "is_auth_required", lambda: True)
    return TestClient(server.app)


def test_register_login_and_profile(auth_client: TestClient) -> None:
    reg = auth_client.post(
        "/api/auth/register",
        json={"username": "test_user", "password": "secret12"},
    )
    assert reg.status_code == 200
    token = reg.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    me = auth_client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["username"] == "test_user"

    put = auth_client.put(
        "/api/auth/profile",
        headers=headers,
        json={
            "current_school": "中国人民大学",
            "major": "金融学",
            "target_school": "中国人民大学",
        },
    )
    assert put.status_code == 200
    assert put.json()["current_school"] == "中国人民大学"

    get = auth_client.get("/api/auth/profile", headers=headers)
    assert get.status_code == 200
    assert get.json()["major"] == "金融学"

    profile_file = Path(os.environ["AUTH_DATA_DIR"]) / "profiles" / "test_user.json"
    assert profile_file.is_file()


def test_study_calendar_persists_per_user(auth_client: TestClient) -> None:
    reg = auth_client.post(
        "/api/auth/register",
        json={"username": "cal_user", "password": "secret12"},
    )
    assert reg.status_code == 200
    token = reg.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    empty = auth_client.get("/api/auth/study-calendar", headers=headers)
    assert empty.status_code == 200
    assert empty.json()["plans"] == []

    put = auth_client.put(
        "/api/auth/study-calendar",
        headers=headers,
        json={
            "plans": [
                {
                    "title": "学习英语",
                    "type": "recurring",
                    "weekdays": [4],
                    "start_date": "2020-01-01",
                    "end_date": "2035-12-31",
                    "color": "#2563eb",
                }
            ]
        },
    )
    assert put.status_code == 200
    body = put.json()
    assert len(body["plans"]) == 1
    assert body["plans"][0]["title"] == "学习英语"
    assert body.get("updated_at")

    get = auth_client.get("/api/auth/study-calendar", headers=headers)
    assert get.status_code == 200
    assert get.json()["plans"][0]["weekdays"] == [4]

    cal_file = Path(os.environ["AUTH_DATA_DIR"]) / "study_calendars" / "cal_user.json"
    assert cal_file.is_file()


def test_study_calendar_completion_persists(auth_client: TestClient) -> None:
    reg = auth_client.post(
        "/api/auth/register",
        json={"username": "cal_done", "password": "secret12"},
    )
    headers = {"Authorization": f"Bearer {reg.json()['token']}"}

    saved = auth_client.put(
        "/api/auth/study-calendar",
        headers=headers,
        json={
            "plans": [
                {
                    "id": "plan1",
                    "title": "英语",
                    "type": "once",
                    "date": "2026-06-07",
                    "color": "#2563eb",
                }
            ],
            "completions": {"2026-06-07": {"plan1": True}},
        },
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["completions"]["2026-06-07"]["plan1"] is True

    loaded = auth_client.get("/api/auth/study-calendar", headers=headers).json()
    assert loaded["completions"]["2026-06-07"]["plan1"] is True


def test_study_calendar_isolated_between_users(auth_client: TestClient) -> None:
    reg_a = auth_client.post(
        "/api/auth/register",
        json={"username": "cal_a", "password": "secret12"},
    )
    reg_b = auth_client.post(
        "/api/auth/register",
        json={"username": "cal_b", "password": "secret12"},
    )
    headers_a = {"Authorization": f"Bearer {reg_a.json()['token']}"}
    headers_b = {"Authorization": f"Bearer {reg_b.json()['token']}"}

    auth_client.put(
        "/api/auth/study-calendar",
        headers=headers_a,
        json={
            "plans": [
                {
                    "title": "用户A计划",
                    "type": "once",
                    "date": "2026-06-07",
                    "color": "#2563eb",
                }
            ]
        },
    )

    plans_b = auth_client.get("/api/auth/study-calendar", headers=headers_b).json()["plans"]
    plans_a = auth_client.get("/api/auth/study-calendar", headers=headers_a).json()["plans"]
    assert len(plans_a) == 1
    assert plans_a[0]["title"] == "用户A计划"
    assert len(plans_b) == 0


def test_todos_persist_per_user(auth_client: TestClient) -> None:
    reg = auth_client.post(
        "/api/auth/register",
        json={"username": "todo_user", "password": "secret12"},
    )
    assert reg.status_code == 200
    headers = {"Authorization": f"Bearer {reg.json()['token']}"}

    empty = auth_client.get("/api/auth/todos", headers=headers)
    assert empty.status_code == 200
    assert empty.json()["items"] == []

    put = auth_client.put(
        "/api/auth/todos",
        headers=headers,
        json={
            "items": [
                {
                    "name": "整理材料",
                    "details": "简历与成绩单",
                    "date": "2026-06-15",
                    "quadrant": "I",
                }
            ]
        },
    )
    assert put.status_code == 200
    body = put.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["name"] == "整理材料"
    assert body["items"][0]["quadrant"] == "I"
    assert body.get("updated_at")

    loaded = auth_client.get("/api/auth/todos", headers=headers).json()
    assert loaded["items"][0]["details"] == "简历与成绩单"

    todo_file = Path(os.environ["AUTH_DATA_DIR"]) / "todos" / "todo_user.json"
    assert todo_file.is_file()


def test_todos_isolated_between_users(auth_client: TestClient) -> None:
    reg_a = auth_client.post(
        "/api/auth/register",
        json={"username": "todo_a", "password": "secret12"},
    )
    reg_b = auth_client.post(
        "/api/auth/register",
        json={"username": "todo_b", "password": "secret12"},
    )
    headers_a = {"Authorization": f"Bearer {reg_a.json()['token']}"}
    headers_b = {"Authorization": f"Bearer {reg_b.json()['token']}"}

    auth_client.put(
        "/api/auth/todos",
        headers=headers_a,
        json={"items": [{"name": "用户A待办", "quadrant": "II"}]},
    )

    items_b = auth_client.get("/api/auth/todos", headers=headers_b).json()["items"]
    items_a = auth_client.get("/api/auth/todos", headers=headers_a).json()["items"]
    assert len(items_a) == 1
    assert items_a[0]["name"] == "用户A待办"
    assert len(items_b) == 0


def test_chat_requires_auth_when_enabled(auth_client: TestClient, monkeypatch) -> None:
    denied = auth_client.post("/api/chat", json={"query": "hello"})
    assert denied.status_code == 401

    def _fake_pipeline(_state):
        return (
            {
                "user_query": "hello",
                "question_type": "general_info",
                "retrieved_docs": [],
                "final_answer": "ok",
                "chat_history": [],
                "execution_steps": [],
                "official_files_read": [],
                "references": [],
            },
            {"route_ms": 0, "retrieve_ms": 0, "answer_ms": 0, "total_ms": 0},
        )

    monkeypatch.setattr(server, "_run_chat_pipeline", _fake_pipeline)

    reg = auth_client.post(
        "/api/auth/register",
        json={"username": "chat_user", "password": "pass1234"},
    )
    token = reg.json()["token"]
    r = auth_client.post(
        "/api/chat",
        json={"query": "hello"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["answer"] == "ok"


def test_duplicate_register_rejected(auth_client: TestClient) -> None:
    auth_client.post(
        "/api/auth/register",
        json={"username": "dup", "password": "pass1234"},
    )
    again = auth_client.post(
        "/api/auth/register",
        json={"username": "dup", "password": "pass5678"},
    )
    assert again.status_code == 400
