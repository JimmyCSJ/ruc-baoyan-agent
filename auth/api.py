"""FastAPI routes for authentication and user profiles."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from auth import service

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class AuthResponse(BaseModel):
    token: str
    username: str


class MeResponse(BaseModel):
    username: str
    auth_required: bool


class ProfilePayload(BaseModel):
    display_name: str = ""
    current_school: str = ""
    grade_year: str = ""
    college: str = ""
    major: str = ""
    gpa: str = ""
    major_rank_percentile: str = ""
    target_school: str = ""
    target_college: str = ""
    target_degree_types: List[str] = Field(default_factory=list)
    english_ielts: str = ""
    english_toefl: str = ""
    english_cet6: str = ""
    research_and_competitions: str = ""
    internships: str = ""
    region_preference: str = ""
    student_work_clubs: str = ""
    career_path_3_5y: str = ""
    expected_roles_or_industry: str = ""
    admission_prep_stage: str = ""
    main_concerns: str = ""
    notes: str = ""


def _extract_bearer(authorization: Optional[str]) -> str:
    if not authorization:
        return ""
    parts = authorization.strip().split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return authorization.strip()


def get_current_user_optional(
    authorization: Optional[str] = Header(default=None),
) -> Optional[str]:
    token = _extract_bearer(authorization)
    if not token:
        return None
    return service.resolve_token(token)


def require_current_user(
    authorization: Optional[str] = Header(default=None),
) -> str:
    if not service.is_auth_required():
        return "__anonymous__"
    user = get_current_user_optional(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="未登录或会话已过期，请重新登录")
    return user


@router.get("/config")
def auth_config() -> dict:
    return {"auth_required": service.is_auth_required()}


@router.post("/register", response_model=AuthResponse)
def register(payload: RegisterRequest) -> AuthResponse:
    username = payload.username.strip()
    ok, msg = service.register(username, payload.password)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    token, err = service.login(username, payload.password)
    if not token:
        raise HTTPException(status_code=500, detail=err or "注册成功但登录失败")
    return AuthResponse(token=token, username=username)


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest) -> AuthResponse:
    token, err = service.login(payload.username.strip(), payload.password)
    if not token:
        raise HTTPException(status_code=401, detail=err or "登录失败")
    return AuthResponse(token=token, username=payload.username.strip())


@router.post("/logout")
def logout(
    authorization: Optional[str] = Header(default=None),
) -> dict:
    token = _extract_bearer(authorization)
    if token:
        service.logout(token)
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
def me(user: Optional[str] = Depends(get_current_user_optional)) -> MeResponse:
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return MeResponse(username=user, auth_required=service.is_auth_required())


@router.get("/profile")
def get_profile(user: str = Depends(require_current_user)) -> Dict[str, Any]:
    if user == "__anonymous__":
        return service.empty_profile()
    return service.get_profile(user)


@router.put("/profile")
def put_profile(
    payload: ProfilePayload,
    user: str = Depends(require_current_user),
) -> Dict[str, Any]:
    if user == "__anonymous__":
        raise HTTPException(status_code=401, detail="未登录")
    body = payload.model_dump()
    return service.update_profile(user, body)


class StudyPlanPayload(BaseModel):
    id: str = ""
    title: str = Field(min_length=1, max_length=80)
    color: str = ""
    type: Literal["recurring", "once"] = "recurring"
    weekdays: List[int] = Field(default_factory=list)
    start_date: str = ""
    end_date: str = ""
    date: str = ""
    note: str = ""
    created_at: str = ""


class StudyCalendarPayload(BaseModel):
    plans: List[StudyPlanPayload] = Field(default_factory=list)
    completions: Dict[str, Dict[str, bool]] = Field(default_factory=dict)


@router.get("/study-calendar")
def get_study_calendar(user: str = Depends(require_current_user)) -> Dict[str, Any]:
    if user == "__anonymous__":
        return service.empty_study_calendar()
    return service.get_study_calendar(user)


@router.put("/study-calendar")
def put_study_calendar(
    payload: StudyCalendarPayload,
    user: str = Depends(require_current_user),
) -> Dict[str, Any]:
    if user == "__anonymous__":
        raise HTTPException(status_code=401, detail="未登录")
    body = {
        "plans": [p.model_dump() for p in payload.plans],
        "completions": payload.completions,
    }
    return service.update_study_calendar(user, body)


class TodoItemPayload(BaseModel):
    id: str = ""
    name: str = Field(min_length=1, max_length=80)
    details: str = ""
    date: str = ""
    quadrant: Literal["I", "II", "III", "IV"] = "IV"
    created_at: str = ""


class TodosPayload(BaseModel):
    items: List[TodoItemPayload] = Field(default_factory=list)


@router.get("/todos")
def get_todos(user: str = Depends(require_current_user)) -> Dict[str, Any]:
    if user == "__anonymous__":
        return service.empty_todos()
    return service.get_todos(user)


@router.put("/todos")
def put_todos(
    payload: TodosPayload,
    user: str = Depends(require_current_user),
) -> Dict[str, Any]:
    if user == "__anonymous__":
        raise HTTPException(status_code=401, detail="未登录")
    body = {"items": [item.model_dump() for item in payload.items]}
    return service.update_todos(user, body)
