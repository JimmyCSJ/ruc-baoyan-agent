"""Inspectable Xiaohongshu Excel KB: row counts, samples, lexical match explanations, row diagnosis."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from kb.internal import InternalChunk
from kb.manifest import PublicInfoXHSConfig, load_manifest, repo_root
from kb.registry import REGISTRY
from kb.service import ensure_loaded
from kb.tokenize import tokenize_query


def _haystack(chunk: InternalChunk) -> str:
    return f"{chunk.title}\n{chunk.text}".lower()


def explain_lexical_match(query: str, chunk: InternalChunk) -> Dict[str, Any]:
    tokens = tokenize_query(query)
    hay = _haystack(chunk)
    matched = [t for t in tokens if t in hay]
    unmatched = [t for t in tokens if t not in hay]
    return {
        "match_score": len(matched),
        "query_tokens": tokens,
        "matched_tokens": matched,
        "unmatched_tokens": unmatched,
        "scorer": "substring_hit_per_token_in_title_plus_indexed_text_lowercased",
    }


def _rank_all_lexical(query: str, chunks: List[InternalChunk]) -> List[Tuple[int, InternalChunk]]:
    tokens = tokenize_query(query)
    if not tokens:
        return [(0, c) for c in sorted(chunks, key=lambda x: x.doc_id)]
    scored: List[Tuple[int, InternalChunk]] = []
    for chunk in chunks:
        hay = _haystack(chunk)
        hits = sum(1 for t in tokens if t in hay)
        scored.append((hits, chunk))
    scored.sort(key=lambda x: (-x[0], x[1].doc_id))
    return scored


def _simulate_experience_retrieval(
    query: str,
    chunks: List[InternalChunk],
    top_k: int,
) -> Tuple[List[Tuple[int, InternalChunk]], str]:
    """Mirror `search_experience` ranking: only positive hit counts unless all zero."""
    tokens = tokenize_query(query)
    if top_k <= 0:
        return [], "top_k_zero"
    positive: List[Tuple[int, InternalChunk]] = []
    for chunk in chunks:
        hay = _haystack(chunk)
        hits = sum(1 for t in tokens if t in hay) if tokens else 0
        if hits > 0:
            positive.append((hits, chunk))
    positive.sort(key=lambda x: (-x[0], x[1].doc_id))
    if positive:
        return positive[:top_k], "lexical_hits_only"
    if chunks:
        return [(0, c) for c in chunks[:top_k]], "fallback_first_rows_no_token_hits"
    return [], "no_chunks"


def _read_raw_excel_row(cfg: PublicInfoXHSConfig, root: Path, excel_row_1based: int) -> Optional[Dict[str, Any]]:
    path = (root / cfg.excel_path).resolve()
    if not path.exists() or excel_row_1based < 2:
        return None
    df = pd.read_excel(path, sheet_name=cfg.sheet, engine="openpyxl")
    idx = excel_row_1based - 2
    if idx < 0 or idx >= len(df):
        return None
    row = df.iloc[idx]
    return {str(k): row[k] for k in df.columns}


def _cell_clean(val: Any) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    text = str(val).strip()
    return "" if text.lower() == "nan" else text


def diagnose_excel_row(
    query: str,
    top_k: int,
    excel_row: int,
    chunks: List[InternalChunk],
    parse_meta: Dict[str, Any],
    cfg: PublicInfoXHSConfig,
    root: Path,
) -> Dict[str, Any]:
    chunk = next((c for c in chunks if int(c.provenance.get("excel_row") or -1) == excel_row), None)
    raw = _read_raw_excel_row(cfg, root, excel_row)

    if raw is None:
        return {
            "excel_row": excel_row,
            "category": "not_in_sheet",
            "found_in_index": False,
            "explanation": "Excel 中不存在该表行号（超出数据范围或小于表头下一行）。表头占第 1 行，首条数据一般为第 2 行。",
        }

    title_col = str(parse_meta.get("columns_resolved", {}).get("title") or "")
    body_col = str(parse_meta.get("columns_resolved", {}).get("body") or "")
    t = _cell_clean(raw.get(title_col, "")) if title_col else ""
    b = _cell_clean(raw.get(body_col, "")) if body_col else ""
    if not t and not b:
        return {
            "excel_row": excel_row,
            "category": "parsing_skipped_empty",
            "found_in_index": False,
            "explanation": "该行在原始表中解析所用「标题列+正文列」均为空，因此未生成索引块（与 Excel 行存在但无有效内容一致）。",
        }

    if chunk is None:
        return {
            "excel_row": excel_row,
            "category": "parsing_column_mismatch",
            "found_in_index": False,
            "explanation": "原始行在解析列上有内容，但未生成索引块：请核对 manifest 列别名与表头（columns_resolved），或是否读错 sheet。",
            "raw_title_len": len(t),
            "raw_body_len": len(b),
        }

    expl = explain_lexical_match(query, chunk)
    ranked, mode = _simulate_experience_retrieval(query, chunks, top_k)
    ranked_rows = [int(c.provenance.get("excel_row")) for _, c in ranked]
    in_top_k = excel_row in ranked_rows

    full_rank = _rank_all_lexical(query, chunks)
    rank_full = next((i + 1 for i, (_, c) in enumerate(full_rank) if int(c.provenance.get("excel_row") or 0) == excel_row), None)
    prov = chunk.provenance
    body_truncated = bool(prov.get("body_truncated"))

    tokens = tokenize_query(query)
    tokens_in_full_body_only: List[str] = []
    if tokens and raw is not None:
        body_col = parse_meta.get("columns_resolved", {}).get("body") or ""
        title_col = parse_meta.get("columns_resolved", {}).get("title") or ""
        full_blob = (
            f"{_cell_clean(raw.get(title_col, ''))}\n{_cell_clean(raw.get(body_col, ''))}"
        ).lower()
        hay_idx = _haystack(chunk)
        for t in expl["unmatched_tokens"]:
            if t in full_blob and t not in hay_idx:
                tokens_in_full_body_only.append(t)

    parts: List[str] = []
    category = "ok_in_top_k"
    if in_top_k:
        parts.append(f"该行在本次 top_k={top_k} 结果中（检索模式：{mode}）。")
        category = "ok_in_top_k"
    else:
        if expl["match_score"] == 0 and mode == "lexical_hits_only":
            category = "scoring_zero_hits"
            parts.append(
                "检索模式为「仅保留至少命中 1 个 query token 的行」："
                f"当前 query 分词 {tokens} 在「标题+已索引正文」中无任何子串命中，因此该行被排除；"
                "其他行有正分。"
            )
        elif expl["match_score"] == 0 and mode == "fallback_first_rows_no_token_hits":
            category = "scoring_fallback_order"
            parts.append(
                f"所有行对该 query 的命中数均为 0，系统回退为「按表顺序取前 {top_k} 行」；"
                f"该行在全表顺序中未进入前 {top_k} 名。"
            )
            if rank_full:
                parts.append(f"在「按命中数排序（含 0）」的全排序中，该行位列第 {rank_full}。")
        elif expl["match_score"] > 0:
            category = "scoring_below_top_k"
            parts.append(
                f"该行命中 {expl['match_score']} 个 token（{expl['matched_tokens']}），"
                f"但排序落后于前 {top_k} 条更高分记录。"
            )
            if rank_full:
                parts.append(f"全量按命中数排序名次：第 {rank_full}。")

    if tokens_in_full_body_only:
        if expl["match_score"] == 0:
            category = "chunking_truncation"
        parts.append(
            f"以下 token 出现在 Excel 原始正文但未进入当前「标题+索引正文」（正文仅索引前 400 字）：{tokens_in_full_body_only}。"
            "若 query 仅依赖这些词，会被判为未命中或低命中。"
        )

    if body_truncated and tokens_in_full_body_only:
        parts.append("该条 body_truncated=true，属于截断/分块策略；非解析失败。")

    return {
        "excel_row": excel_row,
        "category": category,
        "found_in_index": True,
        "explanation": " ".join(parts),
        "retrieval_mode_for_query": mode,
        "in_top_k": in_top_k,
        "rank_in_full_lexical_list": rank_full,
        "match_explanation": expl,
        "body_truncated": body_truncated,
        "tokens_found_in_raw_body_but_not_indexed_text": tokens_in_full_body_only,
    }


def _evenly_spaced_chunks(chunks: List[InternalChunk], n: int) -> List[InternalChunk]:
    if not chunks or n <= 0:
        return []
    if len(chunks) <= n:
        return list(chunks)
    if n == 1:
        return [chunks[0]]
    out: List[InternalChunk] = []
    for i in range(n):
        idx = int(round(i * (len(chunks) - 1) / (n - 1)))
        out.append(chunks[idx])
    return out


def build_xiaohongshu_verify_report(
    query: str,
    top_k: int = 8,
    check_excel_row: Optional[int] = None,
    sample_count: int = 5,
    root: Optional[Path] = None,
) -> Dict[str, Any]:
    base = root or repo_root()
    ensure_loaded(base)
    _, chunks, meta = REGISTRY.snapshot()
    manifest = load_manifest(base)
    cfg = manifest.public_info_xhs

    parse_report = dict(meta.parse_report) if meta and meta.parse_report else {}
    excel_meta = dict(parse_report.get("excel") or {})

    exp_chunks = [c for c in chunks if c.kb_group == "public_info_xhs"]
    exp_chunks_sorted = sorted(exp_chunks, key=lambda c: int(c.provenance.get("excel_row") or 0))
    samples: List[Dict[str, Any]] = []
    for c in _evenly_spaced_chunks(exp_chunks_sorted, sample_count):
        ex = explain_lexical_match(query, c) if query.strip() else {}
        samples.append(
            {
                "excel_row": c.provenance.get("excel_row"),
                "doc_id": c.doc_id,
                "title": c.title,
                "indexed_text_preview": (c.text[:240] + "…") if len(c.text) > 240 else c.text,
                "indexed_text_chars": len(c.text),
                "body_truncated": c.provenance.get("body_truncated"),
                "body_full_chars": c.provenance.get("body_full_chars"),
                "match_preview_for_query": ex if query.strip() else None,
            }
        )

    ranked, mode = _simulate_experience_retrieval(query, exp_chunks, top_k)
    matched_rows: List[Dict[str, Any]] = []
    for rank, (score, ch) in enumerate(ranked, start=1):
        ex = explain_lexical_match(query, ch)
        matched_rows.append(
            {
                "rank": rank,
                "excel_row": ch.provenance.get("excel_row"),
                "doc_id": ch.doc_id,
                "match_score": score,
                "matched_tokens": ex["matched_tokens"],
                "unmatched_tokens": ex["unmatched_tokens"],
                "query_tokens": ex["query_tokens"],
                "why_matched": f"子串匹配：query 分词中有 {len(ex['matched_tokens'])} 个在「标题+索引正文」中出现（计分=命中词数）。",
                "title": ch.title,
                "indexed_text_preview": (ch.text[:200] + "…") if len(ch.text) > 200 else ch.text,
            }
        )

    pr = excel_meta.get("pandas_rows")
    ic = excel_meta.get("chunks_indexed")
    sk = excel_meta.get("rows_skipped_empty")
    out: Dict[str, Any] = {
        "counts": {
            "description": "pandas_rows=表内数据行数；indexed_chunks=成功入库的笔记条数；skipped=标题与正文列皆空被跳过。",
            "pandas_rows": pr,
            "indexed_chunks": ic,
            "rows_skipped_empty": sk,
        },
        "excel": {
            "file": excel_meta.get("file") or cfg.excel_path,
            "sheet": excel_meta.get("sheet", cfg.sheet),
            "pandas_rows": pr,
            "indexed_chunks": ic,
            "rows_skipped_empty": sk,
            "skipped_excel_rows_sample": excel_meta.get("skipped_excel_rows_sample"),
            "columns_resolved": excel_meta.get("columns_resolved"),
            "parse_warnings": list(meta.warnings) if meta else [],
        },
        "samples_first_chunks": samples,
        "note_samples": f"共 {sample_count} 条样例：按 excel_row 排序后在全表中均匀抽样，便于扫一眼解析质量。",
        "query": query.strip(),
        "top_k": top_k,
        "retrieval_mode": mode,
        "query_tokens": tokenize_query(query),
        "tokenizer_note": "分词规则：连续 2 个及以上汉字，或字母数字串（见 kb.tokenize.tokenize_query）；单字与标点不参与计分。",
        "matched_rows": matched_rows,
    }

    if check_excel_row is not None:
        out["check_excel_row"] = check_excel_row
        out["row_diagnosis"] = diagnose_excel_row(
            query,
            top_k,
            check_excel_row,
            exp_chunks,
            excel_meta,
            cfg,
            base,
        )

    return out
