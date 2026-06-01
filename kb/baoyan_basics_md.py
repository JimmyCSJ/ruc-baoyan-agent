"""Baoyan basics ingestion (user-curated public process knowledge)."""

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


def _split_markdown_sections(text: str) -> List[Tuple[str, str]]:
    sections: List[Tuple[str, str]] = []
    current_title = "保研通识总览"
    buf: List[str] = []
    for ln in text.splitlines():
        m = re.match(r"^##\s+(.+)$", ln.strip())
        if m:
            if buf:
                sections.append((current_title, "\n".join(buf).strip()))
                buf = []
            current_title = m.group(1).strip()
            continue
        if ln.strip().startswith("# "):
            continue
        buf.append(ln)
    if buf:
        sections.append((current_title, "\n".join(buf).strip()))
    return [(title, body) for title, body in sections if body.strip()]


def load_baoyan_basics_md(md_path: str, root: Path) -> tuple[List[InternalChunk], List[str], Dict[str, Any]]:
    path = (root / md_path).resolve()
    if not path.exists():
        warn = f"保研通识库 Markdown 不存在，已跳过：{path}"
        return [], [warn], {"file": md_path, "chunks_indexed": 0, "error": "file_not_found"}
    text = _normalize_text(path.read_text(encoding="utf-8", errors="ignore"))
    warns: List[str] = []
    if not text:
        warns.append("保研通识库 Markdown 为空。")
        return [], warns, {"file": md_path, "chunks_indexed": 0}

    sections = _split_markdown_sections(text) or [("保研通识总览", text)]
    chunks: List[InternalChunk] = []
    for i, (title, body) in enumerate(sections, start=1):
        snippet = body[:5200]
        chunks.append(
            InternalChunk(
                doc_id=f"experience:baoyan_basics:s{i:02d}",
                source_group="experience",
                kb_group="public_info_baoyan_basics",
                source_tag="public_info_baoyan_basics_md",
                title=f"保研通识 {title}",
                text=snippet,
                base_confidence=0.72,
                provenance={
                    "file": md_path,
                    "section_index": i,
                    "section_title": title,
                    "chars_raw": len(body),
                    "chars_indexed": len(snippet),
                    "truncated": len(body) > len(snippet),
                    "curation": "user_provided_process_knowledge",
                },
            )
        )

    return chunks, warns, {
        "file": md_path,
        "sections": len(sections),
        "chunks_indexed": len(chunks),
        "sample_titles": [t for t, _ in sections[:8]],
    }
