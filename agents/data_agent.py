"""Text-to-SQL Data Agent for structured admission statistics.

Detects quantitative queries and answers them via LLM-generated SQL
against data/ruc_stats.db. Only SELECT statements are allowed.
"""

from __future__ import annotations

import os
import re
import sqlite3
import time
from contextlib import closing
from typing import Any, Dict, List, Optional, Tuple

from config import get_settings
from openai import OpenAI

_QUANTITATIVE_KEYWORDS = (
    "录取人数", "名额", "报录比", "录取率", "招多少人", "录多少人",
    "扩招", "缩招", "名额数", "占比", "入营", "预推免人数",
    "多少人", "几个名额", "招生规模", "多少名", "录取名额",
    "专硕几个", "学硕几个", "直博几个", "多少硕士", "多少博士",
    "招收", "录取了",
)


def is_quantitative_query(query: str) -> bool:
    if not os.getenv("ENABLE_DATA_AGENT", "false").lower() == "true":
        return False
    q = query.strip()
    return any(k in q for k in _QUANTITATIVE_KEYWORDS)


def _build_schema_prompt() -> str:
    """Introspect the SQLite DB and produce a DDL+descriptions prompt."""
    schema = """
数据库中有以下三张表，包含中国人民大学 2026 年保研推免的录取统计数据。
请根据用户问题生成一条 SELECT 查询来回答。

=== 表 1：college_summary（学院总览）===
CREATE TABLE college_summary (
    college TEXT,        -- 学院名称，如"财政金融学院"、注意模糊数值，别完全匹配。列名必须与上述 DDL 完全一致
    year INTEGER,        -- 年份，2026 表示 2026 级
    masters INTEGER,     -- 硕士录取总人数（含专硕+学硕）
    direct_phd INTEGER,  -- 直博生录取人数
    total INTEGER,       -- 全院总录取人数（masters + direct_phd）
    prev_total INTEGER,  -- 上一年（2025级）总录取人数
    change INTEGER       -- 扩招/缩招人数（正数=比去年扩招，负数=比去年缩招）
);

=== 表 2：major_detail（专业明细）===
CREATE TABLE major_detail (
    college TEXT,        -- 所属学院名称
    major TEXT,          -- 专业/方向名称，如"金融科技"、"人工智能"
    program_type TEXT,   -- 培养类型："专硕"/"学硕"/"直博"/"硕博直通"
    year INTEGER,        -- 年份
    quota INTEGER,       -- 该专业拟录取人数（名额数）
    ratio TEXT           -- 该专业占全院录取总名额的比例，如"70.50%"
);

=== 表 3：admission_stats（竞争数据：夏令营/预推免）===
CREATE TABLE admission_stats (
    college TEXT,        -- 学院名称
    program_type TEXT,   -- 参营类型："硕士（专硕）"/"直博"/"全院总计"
    year INTEGER,        -- 年份
    campers INTEGER,     -- 参营人数（入营/预推免报名人数）
    admitted INTEGER,    -- 最终拟录取人数
    rate TEXT            -- 录取率，如"32.50%"
);

约束（必须遵守）：
- 只输出一条 SELECT 语句，不要任何解释或注释
- 禁止 INSERT/UPDATE/DELETE/DROP/ALTER/CREATE
- 列名必须与上述 DDL 中的列名完全一致，不允许自己编造
- 如果用户问"录取人数"或"录了多少人"：college_summary 用 total 列；admission_stats 用 admitted 列
- 如果用户问"名额"或"招多少人"：用 major_detail 的 quota 列
- 如果用户问"扩招"或"缩招"：用 college_summary 的 change 列
- 如果用户问"录取率"：用 admission_stats 的 rate 列
- 如果用户问"参营"或"入营"：用 admission_stats 的 campers 列
- college 列的值必须用 LIKE 做模糊匹配（如 college LIKE '%财政金融%'），禁止用 = 做精确匹配
- 如果用户没有指定年份，默认查 year=2026
- 如果没有匹配结果，返回 SELECT '暂无数据' AS 提示
"""
    return schema


def generate_sql_via_llm(query: str) -> Tuple[str, str]:
    """Use LLM to generate a SQLite SELECT query. Returns (sql, error)."""
    settings = get_settings()
    if not settings.enable_real_llm or not settings.moark_api_key:
        return "", "LLM 未启用（ENABLE_REAL_LLM=false 或缺少 API Key）"

    schema = _build_schema_prompt()
    prompt = (
        f"{schema}\n\n"
        f"用户问题：{query}\n\n"
        "SQL："
    )

    client = OpenAI(base_url=settings.moark_base_url, api_key=settings.moark_api_key)
    try:
        resp = client.chat.completions.create(
            model=settings.moark_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=512,
            temperature=0.1,
            top_p=0.5,
        )
        text = (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        return "", f"LLM 调用失败：{exc}"

    m = re.search(r"(SELECT[\s\S]*?)(?:;|$)", text, re.I)
    if not m:
        return "", f"无法从 LLM 回复中提取 SELECT 语句：{text[:120]}"
    sql = m.group(1).strip().rstrip(";")
    return sql, ""


def _is_safe_sql(sql: str) -> bool:
    forbidden = r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|DETACH|PRAGMA)\b"
    if re.search(forbidden, sql, re.I):
        return False
    if not re.match(r"\s*SELECT\b", sql, re.I):
        return False
    return True


def execute_sql(sql: str) -> Tuple[List[Dict[str, Any]], List[str], float]:
    """Execute a SELECT statement safely. Returns (rows, column_names, latency_ms)."""
    if not _is_safe_sql(sql):
        raise ValueError(f"不允许执行非 SELECT 语句：{sql[:80]}")
    from kb.build_stats_db import get_stats_db_connection

    t0 = time.perf_counter()
    with closing(get_stats_db_connection()) as conn:
        conn.execute("PRAGMA query_only = ON")
        try:
            cur = conn.execute(sql)
            col_names = [d[0] for d in cur.description] if cur.description else []
            rows = [dict(row) for row in cur.fetchall()]
        except Exception as exc:
            raise RuntimeError(f"SQL 执行错误：{exc}") from exc
    latency_ms = (time.perf_counter() - t0) * 1000
    return rows, col_names, latency_ms


def format_sql_results(rows: List[Dict[str, Any]], columns: List[str], query: str) -> str:
    """Format SQL results as a compact context block for the LLM."""
    if not rows:
        return ""

    col_map = {
        "college": "学院", "year": "年份", "masters": "硕士人数",
        "direct_phd": "直博人数", "total": "总录取", "prev_total": "上年录取",
        "change": "扩缩招", "major": "专业", "program_type": "培养类型",
        "quota": "名额", "ratio": "占比", "campers": "参营人数",
        "admitted": "录取人数", "rate": "录取率",
    }

    header_cn = [col_map.get(c, c) for c in columns]
    lines: List[str] = [
        "【结构化数据查询结果 — 来自 2026 人大保研手工统计数据库】",
        "",
        "| " + " | ".join(header_cn) + " |",
        "|" + "|".join(["---"] * len(header_cn)) + "|",
    ]
    for row in rows:
        vals = [str(row.get(c, "")) if row.get(c) is not None else "/" for c in columns]
        lines.append("| " + " | ".join(vals) + " |")
    lines.append("")
    lines.append("数据来源：手工整理的 ruc_2026_manual_stats.txt，可能不完整，以学院官网当年通知为准。")
    lines.append(f"原始查询：{query}")
    return "\n".join(lines)


def data_agent_query(user_query: str) -> Tuple[str, bool]:
    """Orchestrator: returns (formatted_results_or_empty, was_activated)."""
    if not is_quantitative_query(user_query):
        return "", False

    # Ensure DB is built
    from kb.build_stats_db import build_stats_db
    try:
        build_stats_db()
    except FileNotFoundError:
        return "", False

    sql, err = generate_sql_via_llm(user_query)
    if err:
        return "", False

    try:
        rows, columns, _latency = execute_sql(sql)
    except Exception:
        return "", False

    if not rows or not columns:
        return "", False

    formatted = format_sql_results(rows, columns, user_query)
    return formatted, True
