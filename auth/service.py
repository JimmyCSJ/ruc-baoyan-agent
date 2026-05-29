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
