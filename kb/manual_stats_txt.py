"""Manual admissions stats TXT ingestion (user-curated public info)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from kb.internal import InternalChunk


def _normalize_text(text: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", (ln or "").strip()) for ln in (text or "").splitlines()]
    out: List[str] = []
    prev_blank = False
    for ln in lines:
        if not ln:
            if not prev_blank and out:
                out.append("")
            prev_blank = True
            continue
        prev_blank = False
        out.append(ln)
    return "\n".join(out).strip()


def _split_sections(text: str) -> List[Tuple[str, str]]:
    """Split by Chinese heading markers like '一、xx' / '二、xx'."""
    lines = text.splitlines()
    sections: List[Tuple[str, str]] = []
    current_title = "总览"
    buf: List[str] = []
    heading_re = re.compile(r"^[一二三四五六七八九十百]+、\s*.+")
    for ln in lines:
        if heading_re.match(ln.strip()):
            if buf:
                sections.append((current_title, "\n".join(buf).strip()))
                buf = []
            current_title = ln.strip()
            continue
        buf.append(ln)
    if buf:
        sections.append((current_title, "\n".join(buf).strip()))
    return [(t, b) for t, b in sections if b]


def load_manual_stats_txt(txt_path: str, root: Path) -> tuple[List[InternalChunk], List[str], Dict[str, Any]]:
    path = (root / txt_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Manual stats TXT not found: {path}")
    raw = path.read_text(encoding="utf-8", errors="ignore")
    text = _normalize_text(raw)
    warns: List[str] = []
    if not text:
        warns.append("手工统计 TXT 为空。")
        return [], warns, {"file": txt_path, "chunks_indexed": 0}

    sections = _split_sections(text)
    if not sections:
        sections = [("总览", text)]

    chunks: List[InternalChunk] = []
    for i, (title, body) in enumerate(sections, start=1):
        snippet = body[:5000]
        doc_id = f"experience:manual_stats:s{i:02d}"
        chunks.append(
            InternalChunk(
                doc_id=doc_id,
                source_group="experience",
                kb_group="public_info_manual_stats",
                source_tag="public_info_manual_stats_txt",
                title=f"手工统计数据 {title}",
                text=snippet,
                base_confidence=0.66,
                provenance={
                    "file": txt_path,
                    "section_index": i,
                    "section_title": title,
                    "chars_raw": len(body),
                    "chars_indexed": len(snippet),
                    "truncated": len(body) > len(snippet),
                },
            )
        )

    parse_meta: Dict[str, Any] = {
        "file": txt_path,
        "sections": len(sections),
        "chunks_indexed": len(chunks),
        "sample_titles": [t for t, _ in sections[:8]],
    }
    return chunks, warns, parse_meta

