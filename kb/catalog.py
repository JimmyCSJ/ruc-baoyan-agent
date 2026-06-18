"""Knowledge-base source catalog.

This module is intentionally read-only: it describes the corpus before and
after ingestion without changing retrieval behavior. It makes KB builds easier
to inspect in API responses, tests, and future admin screens.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List

from kb.manifest import KBManifest


@dataclass(frozen=True)
class SourceProfile:
    kb_group: str
    source_group: str
    relative_path: str
    file_kind: str
    evidence_role: str
    authority_rank: int
    default_confidence: float
    exists: bool
    file_count: int
    byte_size: int
    build_strategy: str


def _relative_or_absolute(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _byte_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    if path.is_dir():
        return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
    return 0


def _file_count(path: Path, suffixes: set[str] | None = None) -> int:
    if path.is_file():
        return 1
    if not path.is_dir():
        return 0
    files = [p for p in path.rglob("*") if p.is_file()]
    if suffixes:
        files = [p for p in files if p.suffix.lower() in suffixes]
    return len(files)


def build_source_catalog(manifest: KBManifest, root: Path) -> List[SourceProfile]:
    official_dir = (root / manifest.official_documents_brochures.directory).resolve()
    xhs_excel = (root / manifest.public_info_xhs.excel_path).resolve()
    manual_stats = (root / manifest.public_info_manual_stats.txt_path).resolve()
    basics_md = (root / manifest.public_info_baoyan_basics.md_path).resolve()

    return [
        SourceProfile(
            kb_group="official_documents_brochures",
            source_group="official",
            relative_path=_relative_or_absolute(official_dir, root),
            file_kind="pdf/txt",
            evidence_role="primary_policy",
            authority_rank=100,
            default_confidence=0.94,
            exists=official_dir.exists(),
            file_count=_file_count(official_dir, {".pdf", ".txt"}),
            byte_size=_byte_size(official_dir),
            build_strategy="official brochures are indexed as high-authority policy evidence",
        ),
        SourceProfile(
            kb_group="public_info_xhs",
            source_group="experience",
            relative_path=_relative_or_absolute(xhs_excel, root),
            file_kind="xlsx",
            evidence_role="supplementary_experience",
            authority_rank=45,
            default_confidence=0.56,
            exists=xhs_excel.exists(),
            file_count=_file_count(xhs_excel),
            byte_size=_byte_size(xhs_excel),
            build_strategy="title/body columns are indexed as row-level experience notes",
        ),
        SourceProfile(
            kb_group="public_info_manual_stats",
            source_group="experience",
            relative_path=_relative_or_absolute(manual_stats, root),
            file_kind="txt",
            evidence_role="supplementary_stats",
            authority_rank=60,
            default_confidence=0.66,
            exists=manual_stats.exists(),
            file_count=_file_count(manual_stats),
            byte_size=_byte_size(manual_stats),
            build_strategy="curated text sections are indexed as admissions-stat evidence",
        ),
        SourceProfile(
            kb_group="public_info_baoyan_basics",
            source_group="experience",
            relative_path=_relative_or_absolute(basics_md, root),
            file_kind="md",
            evidence_role="process_knowledge",
            authority_rank=65,
            default_confidence=0.72,
            exists=basics_md.exists(),
            file_count=_file_count(basics_md),
            byte_size=_byte_size(basics_md),
            build_strategy="markdown sections are indexed as general process knowledge",
        ),
    ]


def catalog_report(manifest: KBManifest, root: Path) -> Dict[str, Any]:
    profiles = build_source_catalog(manifest, root)
    missing = [p.kb_group for p in profiles if not p.exists]
    return {
        "ready": not missing,
        "source_count": len(profiles),
        "missing_sources": missing,
        "total_bytes": sum(p.byte_size for p in profiles),
        "sources": [asdict(p) for p in profiles],
        "policy": {
            "official_precedence": True,
            "experience_can_override_official": False,
            "web_is_supplementary_only": True,
            "fallback_when_hybrid_unavailable": "lexical keyword scoring",
        },
    }
