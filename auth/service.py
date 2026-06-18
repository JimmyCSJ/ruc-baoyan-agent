"""Auth business logic: register, login, profile."""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from auth import security, store

PROFILE_FIELDS = (
    "display_name",
    "current_school",
    "grade_year",
    "college",
    "major",
    "gpa",
    "major_rank_percentile",
    "target_school",
    "target_college",
    "target_degree_types",
    "english_ielts",
    "english_toefl",
    "english_cet6",
    "research_and_competitions",
    "internships",
    "region_preference",
    "student_work_clubs",
    "career_path_3_5y",
    "expected_roles_or_industry",
    "admission_prep_stage",
    "main_concerns",
    "notes",
)


def is_auth_required() -> bool:
    return os.getenv("AUTH_REQUIRED", "true").lower() == "true"


def session_ttl_days() -> int:
    try:
        return max(1, int(os.getenv("AUTH_SESSION_DAYS", "14")))
    except ValueError:
        return 14


def empty_profile() -> Dict[str, Any]:
    out: Dict[str, Any] = {k: "" for k in PROFILE_FIELDS}
    out["target_degree_types"] = []
    return out


def _normalize_profile(body: Dict[str, Any]) -> Dict[str, Any]:
    base = empty_profile()
    for key in PROFILE_FIELDS:
        if key not in body:
            continue
        val = body[key]
        if key == "target_degree_types":
            if isinstance(val, list):
                base[key] = [str(x).strip() for x in val if str(x).strip()]
            elif isinstance(val, str) and val.strip():
                base[key] = [x.strip() for x in val.replace("，", ",").split(",") if x.strip()]
            continue
        base[key] = str(val or "").strip()
    return base


def register(username: str, password: str) -> Tuple[bool, str]:
    err = store.validate_username(username)
    if err:
        return False, err
    if len(password or "") < 6:
        return False, "密码至少 6 位"
    if store.user_exists(username):
        return False, "用户名已存在"
    digest, salt = security.hash_password(password)
    try:
        store.create_user(username, digest, salt)
    except ValueError as exc:
        return False, str(exc)
    return True, ""


def login(username: str, password: str) -> Tuple[Optional[str], str]:
    err = store.validate_username(username)
    if err:
        return None, err
    rec = store.get_user_record(username)
    if not rec:
        return None, "用户名或密码错误"
    if not security.verify_password(
        password,
        str(rec.get("password_hash") or ""),
        str(rec.get("salt") or ""),
    ):
        return None, "用户名或密码错误"
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=session_ttl_days())
    store.save_session(token, username, expires.timestamp())
    return token, ""


def logout(token: str) -> None:
    store.delete_session(token)


def resolve_token(token: str) -> Optional[str]:
    return store.resolve_session(token)


def get_profile(username: str) -> Dict[str, Any]:
    saved = store.load_profile(username)
    out = empty_profile()
    for key in PROFILE_FIELDS:
        if key in saved:
            if key == "target_degree_types" and isinstance(saved[key], list):
                out[key] = saved[key]
            else:
                out[key] = str(saved.get(key) or "").strip()
    if saved.get("updated_at"):
        out["updated_at"] = saved["updated_at"]
    return out


def update_profile(username: str, body: Dict[str, Any]) -> Dict[str, Any]:
    profile = _normalize_profile(body)
    return store.save_profile(username, profile)


def profile_to_long_plan_payload(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Map saved profile into long-plan form shape."""
    degree = profile.get("target_degree_types") or []
    if isinstance(degree, str):
        degree = [x.strip() for x in degree.replace("，", ",").split(",") if x.strip()]
    target_school = str(profile.get("target_school") or "").strip()
    target_college = str(profile.get("target_college") or "").strip()
    degree_joined = " / ".join(degree)
    english_parts: List[str] = []
    if profile.get("english_ielts"):
        english_parts.append(f"雅思 {profile['english_ielts']}")
    if profile.get("english_toefl"):
        english_parts.append(f"托福 {profile['english_toefl']}")
    if profile.get("english_cet6"):
        english_parts.append(f"六级 {profile['english_cet6']}")
    english_scores = "；".join(english_parts)
    dest_parts = [target_school, target_college, degree_joined]
    target_destination = " · ".join(p for p in dest_parts if p)
    required = {
        "current_school": profile.get("current_school", ""),
        "grade_year": profile.get("grade_year", ""),
        "college": profile.get("college", ""),
        "major": profile.get("major", ""),
        "gpa": profile.get("gpa", ""),
        "major_rank_percentile": profile.get("major_rank_percentile", ""),
        "target_school": target_school,
        "target_college": target_college,
        "target_degree_type": degree_joined,
        "target_destination": target_destination,
        "english_scores": english_scores,
    }
    optional = {
        "research_and_competitions": profile.get("research_and_competitions", ""),
        "internships": profile.get("internships", ""),
        "region_preference": profile.get("region_preference", ""),
        "student_work_clubs": profile.get("student_work_clubs", ""),
        "career_path_3_5y": profile.get("career_path_3_5y", ""),
        "expected_roles_or_industry": profile.get("expected_roles_or_industry", ""),
        "admission_prep_stage": profile.get("admission_prep_stage", ""),
        "main_concerns": profile.get("main_concerns", ""),
    }
    return {"required": required, "optional": optional}


CALENDAR_MIN_YEAR = 2020
CALENDAR_MAX_YEAR = 2035
PLAN_COLORS = (
    "#2563eb",
    "#16a34a",
    "#d97706",
    "#dc2626",
    "#7c3aed",
    "#0891b2",
    "#db2777",
)


def empty_study_calendar() -> Dict[str, Any]:
    return {"plans": [], "completions": {}, "updated_at": ""}


def _valid_date(s: str) -> bool:
    try:
        datetime.strptime(str(s).strip(), "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _normalize_plan(raw: Dict[str, Any], index: int) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    title = str(raw.get("title") or "").strip()
    if not title:
        return None
    plan_type = str(raw.get("type") or "recurring").strip()
    if plan_type not in ("recurring", "once"):
        plan_type = "recurring"
    color = str(raw.get("color") or "").strip()
    if color not in PLAN_COLORS:
        color = PLAN_COLORS[index % len(PLAN_COLORS)]
    note = str(raw.get("note") or "").strip()
    plan_id = str(raw.get("id") or "").strip() or secrets.token_urlsafe(8)
    created_at = str(raw.get("created_at") or "").strip()
    if not created_at:
        created_at = datetime.now(timezone.utc).isoformat()

    if plan_type == "once":
        date = str(raw.get("date") or "").strip()
        if not _valid_date(date):
            return None
        return {
            "id": plan_id,
            "title": title[:80],
            "color": color,
            "type": "once",
            "date": date,
            "note": note[:500],
            "created_at": created_at,
        }

    weekdays_raw = raw.get("weekdays") or []
    weekdays: List[int] = []
    if isinstance(weekdays_raw, list):
        for w in weekdays_raw:
            try:
                n = int(w)
            except (TypeError, ValueError):
                continue
            if 0 <= n <= 6:
                weekdays.append(n)
    weekdays = sorted(set(weekdays))
    if not weekdays:
        return None
    start_date = str(raw.get("start_date") or f"{CALENDAR_MIN_YEAR}-01-01").strip()
    end_date = str(raw.get("end_date") or f"{CALENDAR_MAX_YEAR}-12-31").strip()
    if not _valid_date(start_date) or not _valid_date(end_date):
        return None
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    return {
        "id": plan_id,
        "title": title[:80],
        "color": color,
        "type": "recurring",
        "weekdays": weekdays,
        "start_date": start_date,
        "end_date": end_date,
        "note": note[:500],
        "created_at": created_at,
    }


def _normalize_completions(
    raw: Any,
    plan_ids: set[str],
) -> Dict[str, Dict[str, bool]]:
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Dict[str, bool]] = {}
    for date_key, day_map in raw.items():
        date_str = str(date_key or "").strip()
        if not _valid_date(date_str):
            continue
        if not isinstance(day_map, dict):
            continue
        day_out: Dict[str, bool] = {}
        for plan_id, done in day_map.items():
            pid = str(plan_id or "").strip()
            if pid not in plan_ids:
                continue
            day_out[pid] = bool(done)
        if day_out:
            out[date_str] = day_out
    return out


def get_study_calendar(username: str) -> Dict[str, Any]:
    saved = store.load_study_calendar(username)
    plans_raw = saved.get("plans") if isinstance(saved.get("plans"), list) else []
    plans: List[Dict[str, Any]] = []
    for idx, item in enumerate(plans_raw):
        norm = _normalize_plan(item if isinstance(item, dict) else {}, idx)
        if norm:
            plans.append(norm)
    plan_ids = {p["id"] for p in plans}
    out = empty_study_calendar()
    out["plans"] = plans
    out["completions"] = _normalize_completions(saved.get("completions"), plan_ids)
    if saved.get("updated_at"):
        out["updated_at"] = str(saved["updated_at"])
    return out


def update_study_calendar(username: str, body: Dict[str, Any]) -> Dict[str, Any]:
    plans_raw = body.get("plans") if isinstance(body.get("plans"), list) else []
    plans: List[Dict[str, Any]] = []
    for idx, item in enumerate(plans_raw):
        if not isinstance(item, dict):
            continue
        norm = _normalize_plan(item, idx)
        if norm:
            plans.append(norm)
    plan_ids = {p["id"] for p in plans}
    completions = _normalize_completions(body.get("completions"), plan_ids)
    return store.save_study_calendar(username, {"plans": plans, "completions": completions})


TODO_QUADRANTS = ("I", "II", "III", "IV")


def empty_todos() -> Dict[str, Any]:
    return {"items": [], "updated_at": ""}


def _normalize_todo(raw: Dict[str, Any], index: int) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or raw.get("title") or "").strip()
    if not name:
        return None
    quadrant = str(raw.get("quadrant") or "IV").strip().upper()
    if quadrant not in TODO_QUADRANTS:
        quadrant = "IV"
    details = str(raw.get("details") or raw.get("note") or "").strip()
    date = str(raw.get("date") or "").strip()
    if date and not _valid_date(date):
        date = ""
    todo_id = str(raw.get("id") or "").strip() or secrets.token_urlsafe(8)
    created_at = str(raw.get("created_at") or "").strip()
    if not created_at:
        created_at = datetime.now(timezone.utc).isoformat()
    return {
        "id": todo_id,
        "name": name[:80],
        "details": details[:500],
        "date": date,
        "quadrant": quadrant,
        "created_at": created_at,
    }


def get_todos(username: str) -> Dict[str, Any]:
    saved = store.load_todos(username)
    items_raw = saved.get("items") if isinstance(saved.get("items"), list) else []
    items: List[Dict[str, Any]] = []
    for idx, item in enumerate(items_raw):
        norm = _normalize_todo(item if isinstance(item, dict) else {}, idx)
        if norm:
            items.append(norm)
    out = empty_todos()
    out["items"] = items
    if saved.get("updated_at"):
        out["updated_at"] = str(saved["updated_at"])
    return out


def update_todos(username: str, body: Dict[str, Any]) -> Dict[str, Any]:
    items_raw = body.get("items") if isinstance(body.get("items"), list) else []
    items: List[Dict[str, Any]] = []
    for idx, item in enumerate(items_raw):
        if not isinstance(item, dict):
            continue
        norm = _normalize_todo(item, idx)
        if norm:
            items.append(norm)
    return store.save_todos(username, {"items": items})
