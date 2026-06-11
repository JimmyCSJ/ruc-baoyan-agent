/** Study calendar: 2020–2035 monthly view with recurring / one-time plans. */
(function () {
  const MIN_YEAR = 2020;
  const MAX_YEAR = 2035;
  const PLAN_COLORS = [
    "#2563eb",
    "#16a34a",
    "#d97706",
    "#dc2626",
    "#7c3aed",
    "#0891b2",
    "#db2777",
  ];
  const WEEKDAY_LABELS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];

  let plans = [];
  let todos = [];
  let completions = {};
  let viewYear = new Date().getFullYear();
  let viewMonth = new Date().getMonth();
  let selectedDate = null;
  let dirty = false;
  let loadedForUser = "";
  let controlsBound = false;
  let saveInFlight = null;

  const root = document.getElementById("viewCalendar");
  if (!root) return;

  const gridEl = document.getElementById("calGrid");
  const monthLabel = document.getElementById("calMonthLabel");
  const yearSelect = document.getElementById("calYearSelect");
  const planListEl = document.getElementById("calPlanList");
  const dayPanel = document.getElementById("calDayPanel");
  const dayPanelTitle = document.getElementById("calDayPanelTitle");
  const dayPlanList = document.getElementById("calDayPlanList");
  const saveMsg = document.getElementById("calSaveMsg");
  const updatedAtEl = document.getElementById("calUpdatedAt");

  const formTitle = document.getElementById("calPlanTitle");
  const formType = document.getElementById("calPlanType");
  const formColor = document.getElementById("calPlanColor");
  const formNote = document.getElementById("calPlanNote");
  const formWeekdays = document.getElementById("calPlanWeekdays");
  const formStartDate = document.getElementById("calPlanStartDate");
  const formEndDate = document.getElementById("calPlanEndDate");
  const formOnceDate = document.getElementById("calPlanOnceDate");
  const recurringFields = document.getElementById("calRecurringFields");
  const onceFields = document.getElementById("calOnceFields");

  function pad2(n) {
    return n < 10 ? `0${n}` : String(n);
  }

  function dateKey(y, m, d) {
    return `${y}-${pad2(m + 1)}-${pad2(d)}`;
  }

  function dateKeyFromDate(date) {
    return dateKey(date.getFullYear(), date.getMonth(), date.getDate());
  }

  function defaultStartDate() {
    return dateKeyFromDate(new Date());
  }

  function defaultEndDate() {
    const now = new Date();
    const end = new Date(now.getFullYear(), now.getMonth() + 3, now.getDate());
    return dateKeyFromDate(end);
  }

  function parseDateKey(key) {
    const [y, m, d] = key.split("-").map(Number);
    return new Date(y, m - 1, d);
  }

  /** Monday-first weekday index: 0=Mon … 6=Sun */
  function weekdayIndex(date) {
    return (date.getDay() + 6) % 7;
  }

  function clampViewDate() {
    if (viewYear < MIN_YEAR) {
      viewYear = MIN_YEAR;
      viewMonth = 0;
    }
    if (viewYear > MAX_YEAR) {
      viewYear = MAX_YEAR;
      viewMonth = 11;
    }
  }

  function inRange(key) {
    return key >= `${MIN_YEAR}-01-01` && key <= `${MAX_YEAR}-12-31`;
  }

  function planAppliesOnDate(plan, key) {
    if (!inRange(key)) return false;
    if (plan.type === "once") return plan.date === key;
    if (key < plan.start_date || key > plan.end_date) return false;
    const wd = weekdayIndex(parseDateKey(key));
    return (plan.weekdays || []).includes(wd);
  }

  function plansForDate(key) {
    return plans.filter((p) => planAppliesOnDate(p, key));
  }

  function todosForDate(key) {
    return todos.filter((t) => t && t.date === key);
  }

  function isPlanCompleted(planId, key) {
    return Boolean(completions[key]?.[planId]);
  }

  function setPlanCompleted(planId, key, done) {
    if (!completions[key]) completions[key] = {};
    if (done) {
      completions[key][planId] = true;
    } else {
      delete completions[key][planId];
      if (!Object.keys(completions[key]).length) delete completions[key];
    }
  }

  function dayCompletionStats(key) {
    const dayPlans = plansForDate(key);
    const dayTodos = todosForDate(key);
    const done = dayPlans.filter((p) => isPlanCompleted(p.id, key)).length;
    return { total: dayPlans.length + dayTodos.length, done, pending: dayPlans.length - done };
  }

  function renderDayPlanRow(plan, key, done) {
    const typeLabel = plan.type === "once" ? "单次" : "重复";
    const noteHtml = plan.note ? ` · ${escapeHtml(plan.note)}` : "";
    const actionLabel = done ? "标记未完成" : "标记完成";
    const actionClass = done ? "btn-ghost" : "btn-secondary";
    return `
      <div class="cal-day-plan ${done ? "cal-day-plan-done" : ""}" data-plan-id="${escapeHtml(plan.id)}">
        <span class="cal-plan-dot" style="background:${escapeHtml(plan.color)}"></span>
        <div class="cal-day-plan-body">
          <strong>${escapeHtml(plan.title)}</strong>
          <p class="muted small">${escapeHtml(typeLabel)}${noteHtml}</p>
        </div>
        <button type="button" class="btn btn-sm ${actionClass} cal-toggle-done"
          data-plan-id="${escapeHtml(plan.id)}" data-done="${done ? "1" : "0"}">${actionLabel}</button>
      </div>`;
  }

  function renderDayTodoRow(todo) {
    const detail = todo.details ? ` · ${escapeHtml(todo.details)}` : "";
    return `
      <div class="cal-day-plan cal-day-todo" data-todo-id="${escapeHtml(todo.id)}">
        <span class="cal-plan-dot cal-todo-dot"></span>
        <div class="cal-day-plan-body">
          <strong>${escapeHtml(todo.name || "待办事项")}</strong>
          <p class="muted small">待办${detail}</p>
        </div>
      </div>`;
  }

  function genId() {
    return `p_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
  }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatWeekdaySummary(plan) {
    if (plan.type !== "recurring") return plan.date || "";
    const days = (plan.weekdays || [])
      .map((i) => WEEKDAY_LABELS[i])
      .join("、");
    return `每${days} · ${plan.start_date} 至 ${plan.end_date}`;
  }

  function populateYearSelect() {
    if (!yearSelect) return;
    yearSelect.innerHTML = "";
    for (let y = MIN_YEAR; y <= MAX_YEAR; y += 1) {
      const opt = document.createElement("option");
      opt.value = String(y);
      opt.textContent = `${y} 年`;
      if (y === viewYear) opt.selected = true;
      yearSelect.appendChild(opt);
    }
  }

  function renderCalendar() {
    clampViewDate();
    populateYearSelect();
    if (monthLabel) {
      monthLabel.textContent = `${viewYear} 年 ${viewMonth + 1} 月`;
    }

    const first = new Date(viewYear, viewMonth, 1);
    const startPad = weekdayIndex(first);
    const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
    const todayKey = dateKey(
      new Date().getFullYear(),
      new Date().getMonth(),
      new Date().getDate(),
    );

    if (!gridEl) return;
    gridEl.innerHTML = "";

    WEEKDAY_LABELS.forEach((label) => {
      const head = document.createElement("div");
      head.className = "cal-weekday";
      head.textContent = label;
      gridEl.appendChild(head);
    });

    for (let i = 0; i < startPad; i += 1) {
      const empty = document.createElement("div");
      empty.className = "cal-cell cal-cell-empty";
      gridEl.appendChild(empty);
    }

    for (let day = 1; day <= daysInMonth; day += 1) {
      const key = dateKey(viewYear, viewMonth, day);
      const dayPlans = plansForDate(key);
      const dayTodos = todosForDate(key);
      const cell = document.createElement("button");
      cell.type = "button";
      cell.className = "cal-cell";
      if (key === todayKey) cell.classList.add("cal-cell-today");
      if (selectedDate === key) cell.classList.add("cal-cell-selected");
      cell.dataset.date = key;

      const num = document.createElement("span");
      num.className = "cal-day-num";
      num.textContent = String(day);
      cell.appendChild(num);

      const stats = dayCompletionStats(key);
      if (stats.total) {
        const progress = document.createElement("span");
        progress.className = "cal-day-progress";
        progress.textContent = `${stats.done}/${stats.total}`;
        cell.appendChild(progress);
      }

      if (dayPlans.length || dayTodos.length) {
        const chips = document.createElement("div");
        chips.className = "cal-chips";
        const shownPlans = dayPlans.slice(0, 3);
        shownPlans.forEach((p) => {
          const done = isPlanCompleted(p.id, key);
          const chip = document.createElement("span");
          chip.className = `cal-chip${done ? " cal-chip-done" : ""}`;
          chip.style.backgroundColor = done ? "hsl(142 45% 42%)" : (p.color || PLAN_COLORS[0]);
          chip.textContent = (done ? "✓ " : "") + p.title;
          chips.appendChild(chip);
        });
        const remainingSlots = Math.max(0, 3 - shownPlans.length);
        dayTodos.slice(0, remainingSlots).forEach((todo) => {
          const chip = document.createElement("span");
          chip.className = "cal-chip cal-todo-chip";
          chip.textContent = `待办 ${todo.name || "事项"}`;
          chips.appendChild(chip);
        });
        const hiddenCount = dayPlans.length + dayTodos.length - chips.children.length;
        if (hiddenCount > 0) {
          const more = document.createElement("span");
          more.className = "cal-chip cal-chip-more";
          more.textContent = `+${hiddenCount}`;
          chips.appendChild(more);
        }
        cell.appendChild(chips);
      }

      cell.addEventListener("click", () => selectDate(key));
      gridEl.appendChild(cell);
    }
  }

  function renderPlanList() {
    if (!planListEl) return;
    if (!plans.length) {
      planListEl.innerHTML = '<p class="muted small">暂无学习计划，请在下方添加。</p>';
      return;
    }
    planListEl.innerHTML = plans
      .map(
        (p) => `
        <article class="cal-plan-item" data-plan-id="${escapeHtml(p.id)}">
          <div class="cal-plan-dot" style="background:${escapeHtml(p.color)}"></div>
          <div class="cal-plan-body">
            <strong>${escapeHtml(p.title)}</strong>
            <p class="muted small">${escapeHtml(formatWeekdaySummary(p))}</p>
            ${p.note ? `<p class="muted small">${escapeHtml(p.note)}</p>` : ""}
          </div>
          <button type="button" class="btn btn-ghost btn-sm cal-plan-del" data-plan-id="${escapeHtml(p.id)}">删除</button>
        </article>`,
      )
      .join("");

    planListEl.querySelectorAll(".cal-plan-del").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-plan-id");
        plans = plans.filter((p) => p.id !== id);
        Object.keys(completions).forEach((dateKey) => {
          if (completions[dateKey]?.[id]) {
            delete completions[dateKey][id];
            if (!Object.keys(completions[dateKey]).length) delete completions[dateKey];
          }
        });
        dirty = true;
        renderAll();
        void autoSave();
      });
    });
  }

  function renderDayPanel() {
    if (!dayPanel || !dayPanelTitle || !dayPlanList) return;
    if (!selectedDate) {
      dayPanel.classList.add("hidden");
      return;
    }
    dayPanel.classList.remove("hidden");
    const stats = dayCompletionStats(selectedDate);
    dayPanelTitle.textContent = `${selectedDate} 的学习安排（${stats.done}/${stats.total} 已完成）`;
    const dayPlans = plansForDate(selectedDate);
    if (!dayPlans.length) {
      dayPlanList.innerHTML = '<p class="muted small">这一天暂无计划。</p>';
      return;
    }
    const pending = dayPlans.filter((p) => !isPlanCompleted(p.id, selectedDate));
    const done = dayPlans.filter((p) => isPlanCompleted(p.id, selectedDate));
    const dayTodos = todosForDate(selectedDate);

    let html = "";
    html += `<div class="cal-day-group">
      <h4 class="cal-day-group-title">当天待办 <span class="muted">(${dayTodos.length})</span></h4>`;
    if (!dayTodos.length) {
      html += '<p class="muted small cal-day-group-empty">这一天暂无带日期的待办。</p>';
    } else {
      html += dayTodos.map(renderDayTodoRow).join("");
    }
    html += "</div>";

    html += `<div class="cal-day-group">
      <h4 class="cal-day-group-title">未完成 <span class="muted">(${pending.length})</span></h4>`;
    if (!pending.length) {
      html += '<p class="muted small cal-day-group-empty">全部完成 🎉</p>';
    } else {
      html += pending.map((p) => renderDayPlanRow(p, selectedDate, false)).join("");
    }
    html += "</div>";

    html += `<div class="cal-day-group">
      <h4 class="cal-day-group-title cal-day-group-title-done">已完成 <span class="muted">(${done.length})</span></h4>`;
    if (!done.length) {
      html += '<p class="muted small cal-day-group-empty">暂无已完成计划</p>';
    } else {
      html += done.map((p) => renderDayPlanRow(p, selectedDate, true)).join("");
    }
    html += "</div>";

    dayPlanList.innerHTML = html;

    dayPlanList.querySelectorAll(".cal-toggle-done").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const planId = btn.getAttribute("data-plan-id");
        const currentlyDone = btn.getAttribute("data-done") === "1";
        setPlanCompleted(planId, selectedDate, !currentlyDone);
        dirty = true;
        renderAll();
        void autoSave();
      });
    });
  }

  function renderAll() {
    renderCalendar();
    renderPlanList();
    renderDayPanel();
  }

  function selectDate(key) {
    selectedDate = key;
    if (formOnceDate) formOnceDate.value = key;
    renderAll();
  }

  function togglePlanTypeFields() {
    const type = formType ? formType.value : "recurring";
    recurringFields?.classList.toggle("hidden", type !== "recurring");
    onceFields?.classList.toggle("hidden", type !== "once");
  }

  function getSelectedWeekdays() {
    if (!formWeekdays) return [];
    return Array.from(formWeekdays.querySelectorAll("input:checked")).map((el) =>
      Number(el.value),
    );
  }

  function resetForm() {
    if (formTitle) formTitle.value = "";
    if (formNote) formNote.value = "";
    if (formType) formType.value = "recurring";
    if (formColor) formColor.value = PLAN_COLORS[plans.length % PLAN_COLORS.length];
    if (formStartDate) formStartDate.value = defaultStartDate();
    if (formEndDate) formEndDate.value = defaultEndDate();
    if (formOnceDate) formOnceDate.value = selectedDate || defaultStartDate();
    formWeekdays?.querySelectorAll("input").forEach((el) => {
      el.checked = false;
    });
    togglePlanTypeFields();
  }

  function addPlanFromForm() {
    const title = (formTitle?.value || "").trim();
    if (!title) {
      window.alert("请填写计划名称");
      return;
    }
    const type = formType?.value === "once" ? "once" : "recurring";
    const color = formColor?.value || PLAN_COLORS[0];
    const note = (formNote?.value || "").trim();

    if (type === "once") {
      const date = (formOnceDate?.value || "").trim();
      if (!date || !inRange(date)) {
        window.alert(`请选择 ${MIN_YEAR}–${MAX_YEAR} 范围内的日期`);
        return;
      }
      plans.push({
        id: genId(),
        title,
        color,
        type: "once",
        date,
        note,
        created_at: new Date().toISOString(),
      });
    } else {
      const weekdays = getSelectedWeekdays();
      if (!weekdays.length) {
        window.alert("请至少选择一个星期");
        return;
      }
      const startDate = (formStartDate?.value || defaultStartDate()).trim();
      const endDate = (formEndDate?.value || defaultEndDate()).trim();
      plans.push({
        id: genId(),
        title,
        color,
        type: "recurring",
        weekdays,
        start_date: startDate,
        end_date: endDate,
        note,
        created_at: new Date().toISOString(),
      });
    }
    dirty = true;
    resetForm();
    renderAll();
    void autoSave();
  }

  function showSaveStatus(text, ok) {
    if (!saveMsg) return;
    saveMsg.textContent = text;
    saveMsg.classList.remove("hidden");
    saveMsg.classList.toggle("ok", ok);
  }

  async function loadFromServer() {
    const res = await apiFetch("/api/auth/study-calendar");
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    const todoRes = await apiFetch("/api/auth/todos");
    const todoData = todoRes.ok ? await todoRes.json() : {};
    plans = Array.isArray(data.plans) ? data.plans : [];
    todos = Array.isArray(todoData.items) ? todoData.items : [];
    completions =
      data.completions && typeof data.completions === "object" ? data.completions : {};
    dirty = false;
    loadedForUser = getAuthUser();
    if (updatedAtEl) {
      updatedAtEl.textContent = data.updated_at
        ? `上次保存：${data.updated_at}`
        : "尚未保存过学习计划";
    }
    renderAll();
  }

  async function saveToServer() {
    const res = await apiFetch("/api/auth/study-calendar", {
      method: "PUT",
      body: JSON.stringify({ plans, completions }),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    plans = Array.isArray(data.plans) ? data.plans : plans;
    completions =
      data.completions && typeof data.completions === "object"
        ? data.completions
        : completions;
    dirty = false;
    loadedForUser = getAuthUser();
    if (updatedAtEl && data.updated_at) {
      updatedAtEl.textContent = `上次保存：${data.updated_at}`;
    }
    renderAll();
    return data;
  }

  async function autoSave() {
    if (saveInFlight) {
      try {
        await saveInFlight;
      } catch {
        /* prior save failed; retry below */
      }
    }
    saveInFlight = (async () => {
      await saveToServer();
      showSaveStatus("已自动保存", true);
    })();
    try {
      await saveInFlight;
    } catch (e) {
      showSaveStatus("自动保存失败，请点击「保存计划」重试", false);
      throw e;
    } finally {
      saveInFlight = null;
    }
  }

  function bindControls() {
    document.getElementById("calPrevMonth")?.addEventListener("click", () => {
      viewMonth -= 1;
      if (viewMonth < 0) {
        viewMonth = 11;
        viewYear -= 1;
      }
      clampViewDate();
      renderCalendar();
    });

    document.getElementById("calNextMonth")?.addEventListener("click", () => {
      viewMonth += 1;
      if (viewMonth > 11) {
        viewMonth = 0;
        viewYear += 1;
      }
      clampViewDate();
      renderCalendar();
    });

    document.getElementById("calToday")?.addEventListener("click", () => {
      const now = new Date();
      viewYear = Math.min(MAX_YEAR, Math.max(MIN_YEAR, now.getFullYear()));
      viewMonth = now.getMonth();
      selectedDate = dateKey(now.getFullYear(), now.getMonth(), now.getDate());
      renderAll();
    });

    yearSelect?.addEventListener("change", () => {
      viewYear = Number(yearSelect.value) || MIN_YEAR;
      clampViewDate();
      renderCalendar();
    });

    formType?.addEventListener("change", togglePlanTypeFields);

    document.getElementById("calAddPlan")?.addEventListener("click", addPlanFromForm);

    document.getElementById("calSavePlans")?.addEventListener("click", async () => {
      showSaveStatus("正在保存…", true);
      try {
        await saveToServer();
        showSaveStatus("已保存", true);
      } catch (e) {
        showSaveStatus("保存失败：" + (e.message || e), false);
      }
    });

    document.getElementById("calAddPlanForDay")?.addEventListener("click", () => {
      if (!selectedDate) return;
      if (formType) formType.value = "once";
      if (formOnceDate) formOnceDate.value = selectedDate;
      togglePlanTypeFields();
      formTitle?.focus();
    });
  }

  function ensureControls() {
    if (controlsBound) return;
    resetForm();
    bindControls();
    controlsBound = true;
  }

  function isLoadedForCurrentUser() {
    return loadedForUser && loadedForUser === getAuthUser();
  }

  function preloadStudyCalendar() {
    ensureControls();
    if (isLoadedForCurrentUser()) return Promise.resolve();
    return loadFromServer();
  }

  function initStudyCalendar() {
    clampViewDate();
    ensureControls();
    if (isLoadedForCurrentUser()) {
      renderAll();
      return Promise.resolve();
    }
    return loadFromServer();
  }

  window.initStudyCalendar = initStudyCalendar;
  window.preloadStudyCalendar = preloadStudyCalendar;
  window.reloadStudyCalendar = loadFromServer;
  window.studyCalendarDirty = () => dirty;
})();
