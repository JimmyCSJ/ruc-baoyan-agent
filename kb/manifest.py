"""Load `data/kb/manifest.yaml`.

Schema v2:
- official_documents_brochures: a directory containing pre-extracted official brochure TXT files
- public_info_xhs: an Excel file (public notes) under data/public_info_xhs/
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import yaml

_MANIFEST_REL = Path("data/kb/manifest.yaml")


@dataclass(frozen=True)
class OfficialBrochuresConfig:
    directory: str


@dataclass(frozen=True)
class PublicInfoXHSConfig:
    excel_path: str
    sheet: int | str


@dataclass(frozen=True)
class PublicInfoManualStatsConfig:
    txt_path: str


@dataclass(frozen=True)
class PublicInfoBaoyanBasicsConfig:
    md_path: str


@dataclass(frozen=True)
class KBManifest:
    version: int
    official_documents_brochures: OfficialBrochuresConfig
    public_info_xhs: PublicInfoXHSConfig
    public_info_manual_stats: PublicInfoManualStatsConfig
    public_info_baoyan_basics: PublicInfoBaoyanBasicsConfig


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_manifest(root: Path | None = None) -> KBManifest:
    base = root or repo_root()
    path = base / _MANIFEST_REL
    raw: Dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    off = raw.get("official_documents_brochures") or {}
    official_brochures = OfficialBrochuresConfig(
        directory=str(off.get("directory", "data/official_documents_brochures")),
    )
    pub = raw.get("public_info_xhs") or {}
    public_info_xhs = PublicInfoXHSConfig(
        excel_path=str(pub.get("excel_path", "data/public_info_xhs/小红书保研笔记.xlsx")),
        sheet=pub.get("sheet", 0),
    )
    manual = raw.get("public_info_manual_stats") or {}
    public_info_manual_stats = PublicInfoManualStatsConfig(
        txt_path=str(manual.get("txt_path", "data/public_info_manual_stats/ruc_2026_manual_stats.txt")),
    )
    basics = raw.get("public_info_baoyan_basics") or {}
    public_info_baoyan_basics = PublicInfoBaoyanBasicsConfig(
        md_path=str(basics.get("md_path", "data/public_info_baoyan_basics/baoyan_basics.md")),
    )
    return KBManifest(
        version=int(raw.get("version", 2)),
        official_documents_brochures=official_brochures,
        public_info_xhs=public_info_xhs,
        public_info_manual_stats=public_info_manual_stats,
        public_info_baoyan_basics=public_info_baoyan_basics,
    )
