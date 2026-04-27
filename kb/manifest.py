"""Load `data/kb/manifest.yaml`."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import yaml

_MANIFEST_REL = Path("data/kb/manifest.yaml")


@dataclass(frozen=True)
class OfficialEntry:
    id: str
    title: str
    path: str


@dataclass(frozen=True)
class ExperienceConfig:
    excel_path: str
    sheet: int | str


@dataclass(frozen=True)
class KBManifest:
    version: int
    official_documents: List[OfficialEntry]
    experience: ExperienceConfig


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_manifest(root: Path | None = None) -> KBManifest:
    base = root or repo_root()
    path = base / _MANIFEST_REL
    raw: Dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    official_raw = raw.get("official_documents") or []
    official = [
        OfficialEntry(id=str(o["id"]), title=str(o["title"]), path=str(o["path"])) for o in official_raw
    ]
    exp = raw.get("experience") or {}
    experience = ExperienceConfig(
        excel_path=str(exp.get("excel_path", "小红书保研笔记.xlsx")),
        sheet=exp.get("sheet", 0),
    )
    return KBManifest(version=int(raw.get("version", 1)), official_documents=official, experience=experience)
