"""Excel KB unit tests."""

from tools.xiaohongshu_excel_kb import kb_status, rebuild_kb, search_kb


def test_rebuild_kb_and_status() -> None:
    info = rebuild_kb()
    assert info["loaded"] is True
    assert info["row_count"] > 0
    assert info["checksum"]
    assert isinstance(info.get("kb_groups"), list)
    assert len(info["kb_groups"]) == 4
    assert {g["kb_group"] for g in info["kb_groups"]} == {
        "official_documents_brochures",
        "public_info_xhs",
        "public_info_manual_stats",
        "public_info_baoyan_basics",
    }

    status = kb_status()
    assert status["loaded"] is True
    assert status["row_count"] == info["row_count"]
    assert len(status.get("kb_groups") or []) == 4


def test_search_kb_returns_docs() -> None:
    rebuild_kb()
    docs = search_kb("人大 保研", top_k=3)
    assert docs
    assert len(docs) <= 3
    assert all(doc["source"] in ("public_info_xhs_excel", "xiaohongshu_excel") for doc in docs)
