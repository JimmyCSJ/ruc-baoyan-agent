"""Backward-compatible entry points → unified `kb` package."""

from __future__ import annotations

from pathlib import Path

from kb.manifest import repo_root
from kb.service import ensure_loaded as ensure_kb_loaded
from kb.service import get_legacy_aggregate_status, rebuild_all, search_experience_only

EXCEL_PATH: Path = repo_root() / "小红书保研笔记.xlsx"


def rebuild_kb() -> dict:
    return rebuild_all()


def kb_status() -> dict:
    return get_legacy_aggregate_status()


def search_kb(query: str, top_k: int = 6) -> list:
    ensure_kb_loaded()
    return search_experience_only(query, top_k)
