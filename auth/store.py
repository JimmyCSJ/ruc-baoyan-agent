"""JSON file persistence for users, sessions, and profiles."""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_LOCK = threading.RLock()
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,32}$")


def _data_root() -> Path:
    raw = os.getenv("AUTH_DATA_DIR", "").strip()
    if raw:
        return Path(raw).resolve()
    return (Path(__file__).resolve().parent.parent / "data" / "auth").resolve()


def _users_file() -> Path:
    return _data_root() / "users.json"


def _sessions_file() -> Path:
    return _data_root() / "sessions.json"


def _profiles_dir() -> Path:
    return _data_root() / "profiles"


def _ensure_dirs() -> None:
    root = _data_root()
    root.mkdir(parents=True, exist_ok=True)
    _profiles_dir().mkdir(parents=True, exist_ok=True)


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def _write_json(path: Path, data: Any) -> None:
    _ensure_dirs()
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def validate_username(username: str) -> Optional[str]:
    u = (username or "").strip()
    if not _USERNAME_RE.match(u):
        return "用户名须为 3–32 位字母、数字或下划线"
    return None


def user_exists(username: str) -> bool:
    users = _read_json(_users_file(), {})
    return username in users


def create_user(username: str, password_hash: str, salt: str) -> None:
    with _LOCK:
        users = _read_json(_users_file(), {})
        if username in users:
            raise ValueError("用户名已存在")
        now = datetime.now(timezone.utc).isoformat()
        users[username] = {
            "password_hash": password_hash,
            "salt": salt,
            "created_at": now,
        }
        _write_json(_users_file(), users)


def get_user_record(username: str) -> Optional[Dict[str, str]]:
    users = _read_json(_users_file(), {})
    rec = users.get(username)
    return rec if isinstance(rec, dict) else None


def save_session(token: str, username: str, expires_at: float) -> None:
    with _LOCK:
        sessions = _read_json(_sessions_file(), {})
        sessions[token] = {"username": username, "expires_at": expires_at}
        _write_json(_sessions_file(), sessions)


def delete_session(token: str) -> None:
    with _LOCK:
        sessions = _read_json(_sessions_file(), {})
        if token in sessions:
            del sessions[token]
            _write_json(_sessions_file(), sessions)


def resolve_session(token: str) -> Optional[str]:
    if not token:
        return None
    with _LOCK:
        sessions = _read_json(_sessions_file(), {})
        rec = sessions.get(token)
        if not isinstance(rec, dict):
            return None
        exp = float(rec.get("expires_at") or 0)
        if exp < datetime.now(timezone.utc).timestamp():
            del sessions[token]
            _write_json(_sessions_file(), sessions)
            return None
        username = str(rec.get("username") or "").strip()
        return username or None


def profile_path(username: str) -> Path:
    safe = re.sub(r"[^\w\-]", "_", username)
    return _profiles_dir() / f"{safe}.json"


def load_profile(username: str) -> Dict[str, Any]:
    path = profile_path(username)
    data = _read_json(path, {})
    return data if isinstance(data, dict) else {}


def save_profile(username: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    with _LOCK:
        path = profile_path(username)
        profile = dict(profile)
        profile["updated_at"] = datetime.now(timezone.utc).isoformat()
        _write_json(path, profile)
        return profile
