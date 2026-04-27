"""Official document ingestion: one chunk per PDF page for inspectability."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

from kb.internal import InternalChunk
from kb.manifest import OfficialEntry

try:
    from pypdf import PdfReader
except ImportError as exc:  # pragma: no cover
    PdfReader = None  # type: ignore[misc, assignment]
    _IMPORT_ERR = exc
else:
    _IMPORT_ERR = None


def _normalize_pdf_text(text: str) -> str:
    """Heuristic cleanup for pypdf extract_text output (keeps inspectability, improves readability)."""
    t = (text or "").replace("\u00a0", " ").strip()
    if not t:
        return ""
    # Normalize excessive whitespace but keep line breaks (often represent layout).
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in t.splitlines()]
    lines = [ln for ln in lines if ln]
    t = "\n".join(lines)
    # Fix spaced punctuation artifacts like "： " / "（ " from extraction.
    t = re.sub(r"\s+([，。；：、】【）])", r"\1", t)
    t = re.sub(r"([（【])\s+", r"\1", t)
    return t.strip()


def load_official_pdf(entry: OfficialEntry, root: Path) -> List[InternalChunk]:
    if PdfReader is None:
        raise RuntimeError(
            "pypdf is required to read official PDFs. Install dependencies (pip install -r requirements.txt)."
        ) from _IMPORT_ERR

    path = (root / entry.path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Official document not found: {path}")

    reader = PdfReader(str(path))
    chunks: List[InternalChunk] = []
    for page_idx, page in enumerate(reader.pages):
        page_num = page_idx + 1
        raw = (page.extract_text() or "").strip()
        text = _normalize_pdf_text(raw)
        if not text:
            text = f"（第 {page_num} 页未提取到文本，可能为扫描版 PDF，请人工核对原件。）"
        doc_id = f"official:{entry.id}#p{page_num}"
        try:
            rel_file = str(path.relative_to(root))
        except ValueError:
            rel_file = str(path)
        chunks.append(
            InternalChunk(
                doc_id=doc_id,
                source_group="official",
                kb_group="official_finance_pdfs",
                source_tag="official_pdf",
                title=f"{entry.title} · 第 {page_num} 页",
                text=text,
                base_confidence=0.94,
                provenance={
                    "file": rel_file,
                    "manifest_id": entry.id,
                    "page": page_num,
                    "chunk_kind": "pdf_page",
                    "extracted_chars": len(raw),
                    "normalized_chars": len(text),
                    "empty_extract": bool(not raw.strip()),
                },
            )
        )
    return chunks


def summarize_official_chunks(entry: OfficialEntry, chunks: List[InternalChunk]) -> Dict[str, Any]:
    """Human-readable load report for admin / parse verification."""
    scan_like = sum(1 for c in chunks if "未提取到文本" in c.text or "扫描版" in c.text)
    chars_total = sum(len(c.text) for c in chunks)
    previews = []
    for c in chunks[:3]:
        previews.append(
            {
                "doc_id": c.doc_id,
                "page": c.provenance.get("page"),
                "title": c.title,
                "text_preview": (c.text[:220] + "…") if len(c.text) > 220 else c.text,
                "char_count": len(c.text),
            }
        )
    return {
        "manifest_id": entry.id,
        "logical_title": entry.title,
        "path": entry.path,
        "page_count": len(chunks),
        "pages_empty_or_scan_hint": scan_like,
        "chars_total": chars_total,
        "chunk_doc_ids_first_pages": [c.doc_id for c in chunks[:5]],
        "page_previews": previews,
    }
