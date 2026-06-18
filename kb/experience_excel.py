"""Public info notes from Excel (Xiaohongshu) — explicit columns & provenance."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from kb.internal import InternalChunk
from kb.manifest import PublicInfoXHSConfig

# Canonical field -> possible column headers (first match wins)
_COLUMN_ALIASES: Dict[str, List[str]] = {
    "title": ["笔记标题", "标题", "title", "笔记名"],
    "body": ["笔记正文", "正文", "笔记内容", "content", "文本"],
    "author": ["作者昵称", "作者", "nickname", "博主"],
    "link": ["笔记链接", "链接", "url", "link"],
    "created": ["create_time（精确到秒）", "create_time", "发布时间", "时间"],
}


def _pick_column(df: pd.DataFrame, aliases: List[str]) -> Optional[str]:
    cols = {str(c).strip(): c for c in df.columns}
    for a in aliases:
        if a in cols:
            return str(cols[a])
    lower_map = {str(c).strip().lower(): c for c in df.columns}
    for a in aliases:
        if a.lower() in lower_map:
            return str(lower_map[a.lower()])
    return None


def _cell_str(row: Dict[str, Any], key: str) -> str:
    if key not in row:
        return ""
    val = row[key]
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    text = str(val).strip()
    if text.lower() == "nan":
        return ""
    return text


def _resolve_excel_path(cfg: PublicInfoXHSConfig, root: Path) -> Path | None:
    candidates: List[Path] = [
        (root / cfg.excel_path).resolve(),
        (root / "小红书保研笔记.xlsx").resolve(),
    ]
    xhs_dir = (root / "data/public_info_xhs").resolve()
    if xhs_dir.is_dir():
        candidates.extend(sorted(xhs_dir.glob("*.xlsx")))
    seen: set[str] = set()
    for p in candidates:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        if p.is_file():
            return p
    return None


def load_experience_excel(cfg: PublicInfoXHSConfig, root: Path) -> tuple[List[InternalChunk], List[str], Dict[str, Any]]:
    path = _resolve_excel_path(cfg, root)
    if path is None:
        expected = (root / cfg.excel_path).resolve()
        warn = (
            f"未找到小红书经验库 Excel（期望路径：{expected}）。"
            "请将「小红书保研笔记.xlsx」放到 data/public_info_xhs/ 或项目根目录后，"
            "在管理页执行「重建索引」；当前将仅使用手工统计与其它公众资料。"
        )
        return [], [warn], {"chunks_indexed": 0, "error": "file_not_found", "expected_path": str(expected)}

    # Suppress harmless openpyxl warning for some exported workbooks.
    warnings.filterwarnings(
        "ignore",
        message="Workbook contains no default style, apply openpyxl's default",
        category=UserWarning,
    )

    # First read only header to resolve title/body columns, then load only those 2 columns.
    header_df = pd.read_excel(path, sheet_name=cfg.sheet, engine="openpyxl", nrows=0)
    header_title = _pick_column(header_df, _COLUMN_ALIASES["title"])
    header_body = _pick_column(header_df, _COLUMN_ALIASES["body"])
    if header_title and header_body:
        df = pd.read_excel(path, sheet_name=cfg.sheet, engine="openpyxl", usecols=[header_title, header_body])
    else:
        df = pd.read_excel(path, sheet_name=cfg.sheet, engine="openpyxl")
    warn_list: List[str] = []
    col_title = _pick_column(df, _COLUMN_ALIASES["title"])
    col_body = _pick_column(df, _COLUMN_ALIASES["body"])
    if not col_title:
        warn_list.append("未匹配到「标题」列别名，将尝试用首列作为标题。")
    if not col_body:
        warn_list.append("未匹配到「正文」列别名，将尝试用次列作为正文。")

    # User requirement: only learn from title/body columns; ignore other metadata columns.
    col_author = None
    col_link = None
    col_created = None

    first_col = str(df.columns[0]) if len(df.columns) else ""
    second_col = str(df.columns[1]) if len(df.columns) > 1 else ""
    use_title = col_title or first_col
    use_body = col_body or (second_col if second_col != use_title else first_col)

    records = df.fillna("").to_dict(orient="records")
    excel_column_headers = [str(c) for c in df.columns.tolist()]
    chunks: List[InternalChunk] = []
    skipped_empty_rows: List[int] = []
    # pandas index i -> excel row ≈ i + 2 (header row 1)
    for i, row in enumerate(records):
        d = {str(k): row[k] for k in row}
        title = _cell_str(d, use_title)
        body = _cell_str(d, use_body)
        if not title and not body:
            skipped_empty_rows.append(i + 2)
            continue
        excel_row = i + 2
        body_truncated = len(body) > 400
        brief = body[:400] + ("…" if body_truncated else "")
        text = brief.strip()
        doc_id = f"experience:public_info_xhs:r{excel_row}"
        try:
            rel_path = str(path.relative_to(root))
        except ValueError:
            rel_path = str(path)
        chunks.append(
            InternalChunk(
                doc_id=doc_id,
                source_group="experience",
                kb_group="public_info_xhs",
                source_tag="public_info_xhs_excel",
                title=title or "（无标题笔记）",
                text=text,
                base_confidence=0.56,
                provenance={
                    "file": rel_path,
                    "sheet": cfg.sheet,
                    "excel_row": excel_row,
                    "body_full_chars": len(body),
                    "body_indexed_chars": len(brief),
                    "body_truncated": body_truncated,
                    "columns": {
                        "title": use_title,
                        "body": use_body,
                    },
                },
            )
        )

    if not chunks:
        warn_list.append("Excel 解析后有效行为 0：请检查表头与数据行。")

    try:
        rel_path = str(path.relative_to(root))
    except ValueError:
        rel_path = str(path)
    parse_meta: Dict[str, Any] = {
        "file": rel_path,
        "sheet": cfg.sheet,
        "excel_column_headers": excel_column_headers,
        "columns_resolved": {
            "title": use_title,
            "body": use_body,
        },
        "pandas_rows": len(records),
        "chunks_indexed": len(chunks),
        "rows_skipped_empty": len(skipped_empty_rows),
        "skipped_excel_rows_sample": skipped_empty_rows[:25],
        "sample_indexed_rows": [
            {
                "excel_row": c.provenance.get("excel_row"),
                "doc_id": c.doc_id,
                "title_preview": (c.title[:120] + "…") if len(c.title) > 120 else c.title,
                "indexed_text_chars": len(c.text),
            }
            for c in chunks[:8]
        ],
    }
    return chunks, warn_list, parse_meta
