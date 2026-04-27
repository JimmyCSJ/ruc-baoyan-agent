"""Thread-safe in-memory KB registry."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, List

from kb.internal import InternalChunk


@dataclass(frozen=True)
class RebuildMeta:
    loaded_at: str
    rebuild_digest: str
    manifest_version: int
    warnings: tuple[str, ...]
    parse_report: Dict[str, Any]


class KBRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._official: List[InternalChunk] = []
        self._experience: List[InternalChunk] = []
        self._meta: RebuildMeta | None = None

    def replace(self, official: List[InternalChunk], experience: List[InternalChunk], meta: RebuildMeta) -> None:
        with self._lock:
            self._official = official
            self._experience = experience
            self._meta = meta

    def snapshot(self) -> tuple[List[InternalChunk], List[InternalChunk], RebuildMeta | None]:
        with self._lock:
            return list(self._official), list(self._experience), self._meta

    def official_chunks(self) -> List[InternalChunk]:
        with self._lock:
            return list(self._official)

    def experience_chunks(self) -> List[InternalChunk]:
        with self._lock:
            return list(self._experience)


def compute_rebuild_digest(official: List[InternalChunk], experience: List[InternalChunk], manifest_yaml: str) -> str:
    lines: List[str] = [hashlib.sha256(manifest_yaml.encode("utf-8")).hexdigest()]
    all_c = sorted(official + experience, key=lambda c: c.doc_id)
    for c in all_c:
        lines.append(f"{c.doc_id}\t{c.source_group}\t{hashlib.sha256(c.text.encode('utf-8')).hexdigest()[:16]}")
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


REGISTRY = KBRegistry()
