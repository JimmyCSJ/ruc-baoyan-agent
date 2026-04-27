"""Internal chunk representation (pre-retrieval)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Literal

SourceGroup = Literal["official", "experience"]
KBGroup = Literal["official_finance_pdfs", "xiaohongshu_excel"]


@dataclass(frozen=True)
class InternalChunk:
    doc_id: str
    source_group: SourceGroup
    kb_group: KBGroup
    source_tag: str
    title: str
    text: str
    base_confidence: float
    provenance: Dict[str, Any] = field(default_factory=dict)
