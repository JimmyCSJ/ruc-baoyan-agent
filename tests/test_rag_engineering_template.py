"""Lightweight engineering checks for the RAG stack.

This file is intentionally small and fast. Extend it when adding new KB source
types, retrieval policies, or credibility rules.
"""

from kb.catalog import catalog_report
from kb.manifest import load_manifest, repo_root


def test_kb_source_catalog_is_declared_and_auditable() -> None:
    root = repo_root()
    report = catalog_report(load_manifest(root), root)

    assert report["source_count"] >= 4
    assert report["policy"]["official_precedence"] is True
    assert report["policy"]["experience_can_override_official"] is False

    groups = {item["kb_group"] for item in report["sources"]}
    assert "official_documents_brochures" in groups
    assert "public_info_xhs" in groups
    assert "public_info_manual_stats" in groups
    assert "public_info_baoyan_basics" in groups


def test_kb_source_catalog_keeps_authority_order_visible() -> None:
    root = repo_root()
    report = catalog_report(load_manifest(root), root)
    by_group = {item["kb_group"]: item for item in report["sources"]}

    official_rank = by_group["official_documents_brochures"]["authority_rank"]
    xhs_rank = by_group["public_info_xhs"]["authority_rank"]
    assert official_rank > xhs_rank
    assert by_group["official_documents_brochures"]["evidence_role"] == "primary_policy"
