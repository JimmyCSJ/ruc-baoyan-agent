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
    assert 'id="todoMatrix"' in _read("web/index.html")


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


def test_long_plan_optional_fields_are_unified_without_region_preference() -> None:
    html = _read("web/index.html")
    app_js = _read("web/app.js")

    long_start = html.index('id="viewLong"')
    long_end = html.index('id="longUseWeb"', long_start)
    long_optional = html[long_start:long_end]

    assert "保研院校地域偏好" not in long_optional
    assert 'name="region_preference" data-lp-opt' not in long_optional
    for label in [
        "科研与竞赛",
        "实习经历",
        "学生工作、社团",
        "未来 3～5 年路径倾向",
        "期望岗位或行业",
        "夏令营 / 预推免 准备进度",
        "当前最大顾虑或短板",
        "备注",
    ]:
        assert label in long_optional
    assert "region_preference: p.region_preference" not in app_js


def test_todos_are_integrated_into_calendar_not_sidebar_nav() -> None:
    html = _read("web/index.html")
    app_js = _read("web/app.js")

    nav_start = html.index('<nav class="sidebar-nav"')
    nav_end = html.index("</nav>", nav_start)
    nav_html = html[nav_start:nav_end]
    calendar_start = html.index('id="viewCalendar"')
    calendar_end = html.index('id="viewProfile"', calendar_start)
    calendar_html = html[calendar_start:calendar_end]

    assert 'data-view="todos"' not in nav_html
    assert "创新待办矩阵" in calendar_html
    assert 'id="todoMatrix"' in calendar_html
    assert 'todos: document.getElementById("viewTodos")' not in app_js
    assert 'viewId === "todos"' not in app_js


def test_long_plan_calendar_sync_uses_timeline_windows_not_day_offsets() -> None:
    app_js = _read("web/app.js")

    assert "function timelineDateForItem" in app_js
    assert "function parseTimelineWindowDate" in app_js
    assert "deadline_or_window" in app_js
    assert "dateKeyFromDateObj(addDays(now, idx))" not in app_js


def test_feature_intro_copy_is_concrete_and_student_facing() -> None:
    html = _read("web/index.html")

    for expected in [
        "把今天要交付的申请动作放在最前面",
        "系统会先查官方文件，再补充经验库和公开网页",
        "生成项目组合、时间线和行动清单",
        "整理可能考什么、怎么复习",
        "三类常见面试场景整理成可复制的开场话术",
        "后续生成规划或辅导时不用重复填写背景",
        "按重要和紧急程度分区",
    ]:
        assert expected in html

    for old_copy in [
        "先看今天要推进什么，再进入月历、问答、笔试辅导和面试辅导。",
        "官方问题会更严谨，咨询类问题会更亲切、更可执行。",
        "一次性填写保研画像（硬指标与选填经历）",
        "个性化参考",
    ]:
        assert old_copy not in html
