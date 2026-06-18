"""Official brochure ingestion: one chunk per brochure text file.

This project distinguishes:
- official: deterministic, high-credibility, used as primary policy evidence
- public: user-generated / public notes (lower credibility, supplementary)

Brochure TXT files are already pre-extracted and stored under `data/official_documents_brochures/`.
We keep ingestion simple and inspectable: one document = one chunk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

from kb.internal import InternalChunk


@dataclass(frozen=True)
class BrochureEntry:
    file: str  # repo-relative path
    title: str


def _normalize_text(text: str) -> str:
    t = (text or "").replace("\u00a0", " ").strip()
    if not t:
        return ""
    # Keep line breaks, normalize intra-line spaces.
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in t.splitlines()]
    # Drop excessive empty lines but keep paragraph separation.
    out: List[str] = []
    blank = False
    for ln in lines:
        if not ln:
            if not blank and out:
                out.append("")
            blank = True
            continue
        blank = False
        out.append(ln)
    return "\n".join(out).strip()


def _title_from_filename(path: Path) -> str:
    # Example: "0084_应用经济学院+碳经济.txt" -> "应用经济学院 碳经济"
    stem = path.stem
    stem = re.sub(r"^\d+[_-]?", "", stem).strip()
    stem = stem.replace("+", " ").replace("_", " ")
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem or path.stem


def list_brochure_entries(root: Path, brochures_dir: Path) -> List[BrochureEntry]:
    base = (root / brochures_dir).resolve()
    if not base.exists():
        raise FileNotFoundError(f"Official brochures directory not found: {base}")
    files = sorted(
        [
            p
            for p in base.iterdir()
            if p.is_file()
            and p.name.lower() != "filenames.txt"
            and p.suffix.lower() in (".txt", ".pdf")
        ],
        key=lambda p: p.name,
    )
    out: List[BrochureEntry] = []
    for p in files:
        try:
            rel = str(p.relative_to(root))
        except ValueError:
            rel = str(p)
        out.append(BrochureEntry(file=rel, title=_title_from_filename(p)))
    return out


def write_filenames_txt(root: Path, brochures_dir: Path, filename: str = "filenames.txt") -> Path:
    """Write a simple newline-delimited file list under the brochures directory.

    This file is used as a lightweight catalog for LLM-based file selection.
    """
    base = (root / brochures_dir).resolve()
    entries = list_brochure_entries(root, brochures_dir)
    out_path = base / filename
    lines = [Path(e.file).name for e in entries]
    out_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return out_path


def read_brochure_text_by_filename(root: Path, brochures_dir: Path, filename: str, *, max_chars: int = 18000) -> Dict[str, Any]:
    """Read a brochure TXT by its basename (as listed in filenames.txt).

    Returns a dict with {file, title, text, truncated}.
    """
    base = (root / brochures_dir).resolve()
    name = str(filename).strip()
    if not name:
        raise ValueError("empty filename")
    if "/" in name or "\\" in name:
        raise ValueError("filename must be a basename, not a path")

    path = (base / name).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Brochure file not found: {path}")
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader  # local import to avoid hard import at module load

        reader = PdfReader(str(path))
        pages: List[str] = []
        for p in reader.pages:
            pages.append((p.extract_text() or "").strip())
        raw = "\n\n".join(pages)
    else:
        raw = path.read_text(encoding="utf-8", errors="ignore")
    text = _normalize_text(raw)
    truncated = False
    if max_chars > 0 and len(text) > max_chars:
        text = text[: max_chars - 1] + "…"
        truncated = True
    try:
        rel = str(path.relative_to(root))
    except ValueError:
        rel = str(path)
    return {
        "file": rel,
        "title": _title_from_filename(path),
        "text": text,
        "truncated": truncated,
        "chars_raw": len(raw),
        "chars_indexed": len(text),
    }


def load_official_brochures(root: Path, brochures_dir: Path) -> List[InternalChunk]:
    entries = list_brochure_entries(root, brochures_dir)
    chunks: List[InternalChunk] = []
    for e in entries:
        p = (root / e.file).resolve()
        info = read_brochure_text_by_filename(root, brochures_dir, p.name, max_chars=9000)
        raw = str(info.get("text") or "")
        text = raw
        if not text:
            text = "（该简章文本为空；请检查文件编码或导入流程。）"
        doc_id = f"official:brochure:{Path(e.file).as_posix()}"
        chunks.append(
            InternalChunk(
                doc_id=doc_id,
                source_group="official",
                kb_group="official_documents_brochures",
                source_tag="official_brochure",
                title=e.title,
                text=text[:9000],
                base_confidence=0.94,
                provenance={
                    "file": e.file,
                    "chunk_kind": "brochure_file",
                    "chars_raw": int(info.get("chars_raw") or 0),
                    "chars_indexed": min(len(text), 9000),
                    "truncated": bool(info.get("truncated")),
                },
            )
        )
    return chunks


def summarize_brochures(chunks: Iterable[InternalChunk]) -> Dict[str, Any]:
    ch = list(chunks)
    truncated = sum(1 for c in ch if bool(c.provenance.get("truncated")))
    chars_total = sum(len(c.text) for c in ch)
    samples = []
    for c in ch[:5]:
        samples.append(
            {
                "doc_id": c.doc_id,
                "title": c.title,
                "file": c.provenance.get("file"),
                "text_preview": (c.text[:240] + "…") if len(c.text) > 240 else c.text,
                "char_count": len(c.text),
            }
        )
    return {
        "file_count": len(ch),
        "chunks": len(ch),
        "chars_total": chars_total,
        "truncated_files": truncated,
        "samples": samples,
    }

