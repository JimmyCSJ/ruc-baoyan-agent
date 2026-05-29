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
