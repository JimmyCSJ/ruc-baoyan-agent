"""Server API tests."""

from fastapi.testclient import TestClient

import server


def _fake_run_chat_pipeline(_state):
    return (
        {
            "user_query": "x",
            "question_type": "experience_reference",
            "retrieved_docs": [
                {
                    "source": "xiaohongshu_excel",
                    "title": "测试来源",
                    "content": "测试内容",
                    "confidence": 0.77,
                    "source_group": "experience",
                    "doc_id": "experience:test:1",
                    "source_type": "experience_note",
                    "credibility_level": "medium",
                    "suspected_ad": False,
                    "freshness": "possibly_outdated",
                    "evidence_role": "supplementary_experience",
                    "ad_risk_reasons": [],
                }
            ],
            "retrieval_trace": {
                "policy": "test",
                "stages": [],
                "merged_for_generation": ["experience:test:1"],
            },
            "final_answer": "这是测试回答",
            "chat_history": [],
            "enable_web_search": False,
        },
        {"route_ms": 1, "retrieve_ms": 2, "answer_ms": 3, "total_ms": 6},
    )


def test_health() -> None:
    client = TestClient(server.app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_chat_api(monkeypatch) -> None:
    monkeypatch.setattr(server, "_run_chat_pipeline", _fake_run_chat_pipeline)
    client = TestClient(server.app)

    response = client.post("/api/chat", json={"query": "请给我保研建议"})
    body = response.json()

    assert response.status_code == 200
    assert body["answer"] == "这是测试回答"
    assert body["question_type"] == "experience_reference"
    assert body["sources"]
    assert isinstance(body["latency_ms"], int)
    assert body["timing"]["total_ms"] == 6
    assert "route_ms" in body["timing"]


def test_kb_status_and_rebuild() -> None:
    client = TestClient(server.app)

    status_resp = client.get("/api/kb/status")
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert "loaded" in body
    assert "official_chunk_count" in body

    rebuild_resp = client.post("/api/kb/rebuild")
    assert rebuild_resp.status_code == 200
    rebuild_body = rebuild_resp.json()
    assert rebuild_body["loaded"] is True
    assert rebuild_body["row_count"] > 0
    assert rebuild_body.get("official_chunk_count", 0) > 0


def test_chat_kb_debug_includes_trace(monkeypatch) -> None:
    monkeypatch.setattr(server, "_run_chat_pipeline", _fake_run_chat_pipeline)
    client = TestClient(server.app)
    response = client.post("/api/chat", json={"query": "hello", "kb_debug": True})
    assert response.status_code == 200
    assert response.json().get("retrieval_trace") is not None


def test_chat_kb_debug_header_enables_verbose_trace(monkeypatch) -> None:
    """X-KB-Debug must turn on kb_debug in pipeline (same as body flag)."""
    captured = {}

    def capture_pipeline(state):
        captured["kb_debug"] = state.get("kb_debug")
        return _fake_run_chat_pipeline(state)

    monkeypatch.setattr(server, "_run_chat_pipeline", capture_pipeline)
    client = TestClient(server.app)
    r = client.post("/api/chat", json={"query": "hello"}, headers={"X-KB-Debug": "true"})
    assert r.status_code == 200
    assert captured.get("kb_debug") is True


def test_xiaohongshu_verify_endpoint() -> None:
    client = TestClient(server.app)
    client.post("/api/kb/rebuild")
    r = client.post(
        "/api/kb/xiaohongshu/verify",
        json={"query": "人大 保研", "top_k": 5, "sample_count": 5},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("counts", {}).get("indexed_chunks", 0) >= 1
    assert len(body.get("matched_rows") or []) >= 1
    assert len(body.get("samples_first_chunks") or []) >= 1


def test_kb_retrieve_preview_returns_verbose_trace() -> None:
    client = TestClient(server.app)
    client.post("/api/kb/rebuild")
    r = client.post(
        "/api/kb/retrieve-preview",
        json={"query": "中国人民大学保研申请条件有哪些？"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["question_type"]
    assert isinstance(body["retrieval_trace"]["docs_passed_to_generation"], list)
    assert body["sources_count"] == len(body["sources"])


def test_web_access_test_endpoint(monkeypatch) -> None:
    import server as s

    monkeypatch.setattr(
        s,
        "get_settings",
        s.get_settings,
    )
    monkeypatch.setattr(
        __import__("tools.web_access_bridge", fromlist=["search_web_via_web_access"]),
        "search_web_via_web_access",
        lambda _q: (
            [{"source": "web_access_ruc", "title": "ruc", "content": "abc\n链接：https://ruc.edu.cn", "confidence": 0.7}],
            {"used": True, "failure_reason": ""},
        ),
    )
    monkeypatch.setattr(
        __import__("tools.web_search", fromlist=["search_web_vertical"]),
        "search_web_vertical",
        lambda _q: [{"source": "web_general", "title": "legacy", "content": "x", "confidence": 0.5}],
    )
    client = TestClient(server.app)
    r = client.post("/api/web-access/test", json={"query": "人大 推免", "scenario": "official_site"})
    assert r.status_code == 200
    body = r.json()
    assert body["web_access_primary"]["docs_count"] >= 1
    assert body["final_path"] == "web_access_primary"


def test_kb_debug_bundle_when_admin_enabled(monkeypatch) -> None:
    from config import Settings

    monkeypatch.setattr(
        server,
        "get_settings",
        lambda: Settings(
            deepseek_api_key="",
            deepseek_base_url="https://api.deepseek.com",
            deepseek_model="deepseek-chat",
            enable_real_llm=False,
            failover_enabled=True,
            llm_temperature=0.7,
            llm_top_p=0.7,
            llm_max_tokens=1024,
            llm_frequency_penalty=1,
            llm_top_k=50,
            enable_kb_admin=True,
            web_access_primary=True,
            web_access_proxy_url="http://localhost:3456",
            web_access_timeout_s=14,
            web_access_max_pages=3,
            web_access_fallback_enabled=True,
        ),
    )
    client = TestClient(server.app)
    client.post("/api/kb/rebuild")
    r = client.get("/api/kb/debug")
    assert r.status_code == 200
    body = r.json()
    assert "status" in body and "inspect" in body
    assert body["inspect"].get("sources")


def test_kb_debug_disabled_when_admin_off(monkeypatch) -> None:
    from config import Settings

    monkeypatch.setattr(
        server,
        "get_settings",
        lambda: Settings(
            deepseek_api_key="",
            deepseek_base_url="https://api.deepseek.com",
            deepseek_model="deepseek-chat",
            enable_real_llm=False,
            failover_enabled=True,
            llm_temperature=0.7,
            llm_top_p=0.7,
            llm_max_tokens=1024,
            llm_frequency_penalty=1,
            llm_top_k=50,
            enable_kb_admin=False,
            web_access_primary=True,
            web_access_proxy_url="http://localhost:3456",
            web_access_timeout_s=14,
            web_access_max_pages=3,
            web_access_fallback_enabled=True,
        ),
    )
    client = TestClient(server.app)
    assert client.get("/api/kb/debug").status_code == 404


def test_admin_kb_inspect_when_enabled(monkeypatch) -> None:
    from config import Settings

    monkeypatch.setattr(
        server,
        "get_settings",
        lambda: Settings(
            deepseek_api_key="",
            deepseek_base_url="https://api.deepseek.com",
            deepseek_model="deepseek-chat",
            enable_real_llm=False,
            failover_enabled=True,
            llm_temperature=0.7,
            llm_top_p=0.7,
            llm_max_tokens=1024,
            llm_frequency_penalty=1,
            llm_top_k=50,
            enable_kb_admin=True,
            web_access_primary=True,
            web_access_proxy_url="http://localhost:3456",
            web_access_timeout_s=14,
            web_access_max_pages=3,
            web_access_fallback_enabled=True,
        ),
    )
    client = TestClient(server.app)
    client.post("/api/kb/rebuild")
    r = client.get("/api/admin/kb/inspect")
    assert r.status_code == 200
    data = r.json()
    assert "sources" in data
    assert data.get("totals", {}).get("official_chunks", 0) >= 0
    assert "parse_verification" in data
    pv = data["parse_verification"]
    assert pv.get("excel", {}).get("chunks_indexed", 0) >= 0
    assert len(pv.get("official_documents", [])) >= 1
