"""Static UI contract tests for the student workbench."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_calendar_view_is_today_workbench_with_shortcuts_and_month_calendar() -> None:
    html = _read("web/index.html")
    app_js = _read("web/app.js")

    assert "今日工作台" in html
    assert 'id="wbTodayList"' in html
    assert 'id="wbWeekList"' in html
    assert 'id="wbQuickAskBtn"' in html
    assert 'id="wbExamBtn"' in html
    assert 'id="wbInterviewBtn"' in html
    assert 'id="calGrid"' in html

    assert "function renderTodayWorkbench" in app_js
    assert 'apiFetch("/api/auth/study-calendar")' in app_js
    assert 'apiFetch("/api/auth/todos")' in app_js
    assert 'setActiveView("quick")' in app_js
    assert 'setActiveView("exam")' in app_js
    assert 'setActiveView("interview")' in app_js


def test_long_plan_can_be_converted_into_calendar_and_todos() -> None:
    html = _read("web/index.html")
    app_js = _read("web/app.js")

    assert 'id="btnPlanToCalendar"' in html
    assert 'id="btnPlanToTodos"' in html
    assert "function addLongPlanToCalendar" in app_js
    assert "function addLongPlanToTodos" in app_js
    assert "action_guidelines" in app_js
    assert "timeline" in app_js


def test_profile_nudge_is_part_of_today_workbench() -> None:
    html = _read("web/index.html")
    app_js = _read("web/app.js")

    assert 'id="wbProfileNudge"' in html
    assert 'id="btnWorkbenchProfile"' in html
    assert "function profileIsIncomplete" in app_js
    assert 'setActiveView("profile")' in app_js


def test_dated_todos_are_rendered_on_calendar() -> None:
    calendar_js = _read("web/study-calendar.js")

    assert "let todos" in calendar_js
    assert "function todosForDate" in calendar_js
    assert 'apiFetch("/api/auth/todos")' in calendar_js
    assert "cal-todo-chip" in calendar_js


def test_calendar_nav_is_first_and_non_evidence_views_expand() -> None:
    html = _read("web/index.html")
    css = _read("web/style.css")

    nav_start = html.index('<nav class="sidebar-nav"')
    first_calendar = html.index('data-view="calendar"', nav_start)
    first_quick = html.index('data-view="quick"', nav_start)
    assert first_calendar < first_quick

    assert ".app.evidence-hidden .view" in css
    assert "max-width: none" in css
    assert ".app.evidence-hidden .view-long .lp-form-grid" in css
