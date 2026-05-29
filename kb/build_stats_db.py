"""Build SQLite DB from ruc_2026_manual_stats.txt.

Produces data/ruc_stats.db with three tables:
- college_summary: per-college admission totals
- major_detail: per-major quotas within each college
- admission_stats: competition data (campers/admitted/rate)

Idempotent: skips rebuild when content digest is unchanged.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
import threading
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from kb.manifest import repo_root

DB_PATH = repo_root() / "data" / "ruc_stats.db"
_STATS_TXT_REL = "data/public_info_manual_stats/ruc_2026_manual_stats.txt"
_SCHEMA_VERSION = 1

_BUILD_LOCK = threading.Lock()

DDL = """
CREATE TABLE IF NOT EXISTS _build_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS college_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    college TEXT NOT NULL,
    year INTEGER NOT NULL DEFAULT 2026,
    masters INTEGER,
    direct_phd INTEGER,
    total INTEGER,
    prev_total INTEGER,
    change INTEGER,
    UNIQUE(college, year)
);

CREATE TABLE IF NOT EXISTS major_detail (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    college TEXT NOT NULL,
    major TEXT NOT NULL,
    program_type TEXT,
    year INTEGER NOT NULL DEFAULT 2026,
    quota INTEGER,
    ratio TEXT
);

CREATE TABLE IF NOT EXISTS admission_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    college TEXT NOT NULL,
    program_type TEXT,
    year INTEGER NOT NULL DEFAULT 2026,
    campers INTEGER,
    admitted INTEGER,
    rate TEXT
);
"""


def _normalize_college(name: str) -> str:
    n = (name or "").strip()
    n = re.sub(r"\s+", "", n)
    n = n.rstrip("（专业学位）")
    return n


def _parse_int(s: str) -> Optional[int]:
    s = (s or "").strip()
    if s in ("/", "-", "—", "", "无"):
        return None
    s = re.sub(r"[^\d\-]", "", s)
    if not s or s == "-":
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _parse_college_summary(text: str) -> List[Dict[str, Any]]:
    """Parse the TSV college summary table after '全校与学院总览'."""
    rows: List[Dict[str, Any]] = []
    in_table = False
    for line in text.splitlines():
        line = line.strip()
        if "学院名称" in line and "硕士" in line:
            in_table = True
            continue
        if not in_table:
            continue
        if not line or line.startswith("##"):
            if rows:
                break
            continue
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) < 5:
            continue
        college = _normalize_college(parts[0])
        if not college or college in ("全校合计", "学院名称"):
            continue
        row = {
            "college": parts[0].strip(),
            "year": 2026,
            "masters": _parse_int(parts[1]),
            "direct_phd": _parse_int(parts[2]),
            "total": _parse_int(parts[3]),
            "prev_total": _parse_int(parts[4]),
            "change": _parse_int(parts[5]) if len(parts) > 5 and parts[5].strip() != "/" else None,
        }
        rows.append(row)
    return rows


def _parse_major_detail_section(text: str, college: str) -> List[Dict[str, Any]]:
    """Parse per-college major detail from a section body."""
    rows: List[Dict[str, Any]] = []

    # Try TSV format first (major table with headers)
    tsv_rows: List[List[str]] = []
    in_tsv = False
    has_tsv_header = False
    for line in text.splitlines():
        line = line.strip()
        if not line:
            if tsv_rows and has_tsv_header:
                break
            continue
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) >= 3:
            if "专业名称" in parts[0] or ("专业" in parts[0] and "培养类型" in (parts[1] if len(parts) > 1 else "")):
                has_tsv_header = True
                in_tsv = True
                continue
            if "类型" in parts[0] and "入营" in line:
                in_tsv = False
                continue
            if "合计" in parts[0] or "总计" in parts[0]:
                in_tsv = False
                continue
            if in_tsv:
                tsv_rows.append(parts)

    for parts in tsv_rows:
        major = parts[0].strip()
        if not major or major in ("-", "—"):
            continue
        prog_type = parts[1].strip() if len(parts) > 1 else ""
        quota = _parse_int(parts[2]) if len(parts) > 2 else None
        ratio = parts[3].strip() if len(parts) > 3 else ""
        if quota is None:
            continue
        rows.append({
            "college": college,
            "major": major,
            "program_type": prog_type,
            "year": 2026,
            "quota": quota,
            "ratio": ratio if ratio not in ("", "/") else "",
        })

    # Try semicolon-separated format: "专业名 数字；专业名 数字"
    if not rows:
        m = re.search(r"（2026[^）]*）\s*(.+?)(?:。|$)", text)
        if m:
            segment = m.group(1)
            items = re.split(r"[；;]\s*", segment)
        else:
            items = re.split(r"[；;]\s*", text)
        for item in items:
            item = item.strip()
            if not item or len(item) < 4:
                continue
            match = re.match(r"([^\d]+?)\s*(\d+)", item)
            if match:
                rows.append({
                    "college": college,
                    "major": match.group(1).strip(),
                    "program_type": "",
                    "year": 2026,
                    "quota": int(match.group(2)),
                    "ratio": "",
                })

    return rows


def _parse_admission_stats_section(text: str, college: str) -> List[Dict[str, Any]]:
    """Parse competition stats (入营/录取/rate) from a section."""
    rows: List[Dict[str, Any]] = []
    in_table = False
    for line in text.splitlines():
        line = line.strip()
        if not line:
            if in_table and rows:
                break
            continue
        if "预推免入营" in line or ("入营人数" in line and "录取人数" in line):
            in_table = True
            continue
        if not in_table:
            continue
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) < 3:
            if rows:
                break
            continue
        prog_type = parts[0]
        campers = _parse_int(parts[1])
        admitted = _parse_int(parts[2])
        rate = parts[3].strip() if len(parts) > 3 else ""
        if prog_type in ("合计", "总计", "全院总计"):
            break
        if campers is not None or admitted is not None:
            rows.append({
                "college": college,
                "program_type": prog_type,
                "year": 2026,
                "campers": campers,
                "admitted": admitted,
                "rate": rate if rate not in ("", "/") else "",
            })
    return rows


def _parse_txt(path: Path) -> Tuple[
    List[Dict[str, Any]],
    List[Dict[str, Any]],
    List[Dict[str, Any]],
]:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    # Split into sections by ## and numbered headers
    sections: List[Tuple[str, str]] = []
    current_title = "preamble"
    buf: List[str] = []
    heading_re = re.compile(r"^(##\s+.+|[一二三四五六七八九十]+、\s*.+)")
    for ln in raw.splitlines():
        if heading_re.match(ln.strip()):
            if buf:
                sections.append((current_title, "\n".join(buf).strip()))
                buf = []
            current_title = ln.strip()
            continue
        buf.append(ln)
    if buf:
        sections.append((current_title, "\n".join(buf).strip()))

    college_summary_rows: List[Dict[str, Any]] = []
    major_rows: List[Dict[str, Any]] = []
    admission_rows: List[Dict[str, Any]] = []

    for title, body in sections:
        if "全校与学院总览" in title:
            college_summary_rows = _parse_college_summary(body)
        elif title.startswith(("一、", "二、", "三、", "四、", "五、", "六、", "七、", "八、",
                                "九、", "十、", "十一、", "十二、", "十三、", "十四、", "十五、", "十六、")):
            college_match = re.match(r"[一二三四五六七八九十]+、\s*(.+)", title)
            college = college_match.group(1) if college_match else title
            major_rows += _parse_major_detail_section(body, college)
            admission_rows += _parse_admission_stats_section(body, college)

    return college_summary_rows, major_rows, admission_rows


def build_stats_db(root: Optional[Path] = None) -> str:
    """Build (or skip if unchanged) the SQLite stats database.

    Returns the content digest used.
    """
    base = root or repo_root()
    txt_path = (base / _STATS_TXT_REL).resolve()
    if not txt_path.exists():
        raise FileNotFoundError(f"Manual stats TXT not found: {txt_path}")

    current_digest = hashlib.sha256(txt_path.read_bytes()).hexdigest()
    db_path = base / "data" / "ruc_stats.db"

    with _BUILD_LOCK:
        # Check if rebuild is needed
        if db_path.exists():
            try:
                with closing(sqlite3.connect(str(db_path))) as conn:
                    cur = conn.execute("SELECT value FROM _build_meta WHERE key = 'content_digest'")
                    row = cur.fetchone()
                    if row and row[0] == current_digest:
                        return current_digest
            except Exception:
                pass

        college_rows, major_rows, admission_rows = _parse_txt(txt_path)

        with closing(sqlite3.connect(str(db_path))) as conn:
            conn.executescript(DDL)
            conn.execute("DELETE FROM _build_meta WHERE key = 'content_digest'")
            conn.execute("DELETE FROM college_summary")
            conn.execute("DELETE FROM major_detail")
            conn.execute("DELETE FROM admission_stats")

            conn.execute(
                "INSERT OR REPLACE INTO _build_meta(key, value) VALUES(?, ?)",
                ("content_digest", current_digest),
            )
            conn.execute(
                "INSERT OR REPLACE INTO _build_meta(key, value) VALUES(?, ?)",
                ("schema_version", str(_SCHEMA_VERSION)),
            )

            for r in college_rows:
                conn.execute(
                    """INSERT OR REPLACE INTO college_summary
                       (college, year, masters, direct_phd, total, prev_total, change)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (r["college"], r["year"], r["masters"], r["direct_phd"],
                     r["total"], r["prev_total"], r["change"]),
                )
            for r in major_rows:
                conn.execute(
                    """INSERT INTO major_detail
                       (college, major, program_type, year, quota, ratio)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (r["college"], r["major"], r["program_type"], r["year"],
                     r["quota"], r["ratio"] or ""),
                )
            for r in admission_rows:
                conn.execute(
                    """INSERT INTO admission_stats
                       (college, program_type, year, campers, admitted, rate)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (r["college"], r["program_type"], r["year"],
                     r["campers"], r["admitted"], r["rate"] or ""),
                )
            conn.commit()

    return current_digest


def get_stats_db_connection() -> sqlite3.Connection:
    db_path = repo_root() / "data" / "ruc_stats.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn
