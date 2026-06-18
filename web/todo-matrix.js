/** Todo matrix: Eisenhower-style four-quadrant todo board (I–IV). */
(function () {
  const QUADRANTS = ["I", "II", "III", "IV"];
  /** Grid order: top-left → top-right → bottom-left → bottom-right */
  const MATRIX_ORDER = ["II", "I", "IV", "III"];
  const QUADRANT_META = {
    I: { label: "I 级", hint: "重要且紧急", color: "#dc2626" },
    II: { label: "II 级", hint: "重要不紧急", color: "#2563eb" },
    III: { label: "III 级", hint: "紧急不重要", color: "#d97706" },
    IV: { label: "IV 级", hint: "不重要不紧急", color: "#64748b" },
  };
  const APP_FIXED_NOW_ISO = "2026-05-01T09:00:00+08:00";

  function appNowDate() {
    return new Date(APP_FIXED_NOW_ISO);
  }

  let items = [];
  let dirty = false;
  let loadedForUser = "";
  let controlsBound = false;
  let saveInFlight = null;

  const root = document.getElementById("calendarTodoSection") || document.getElementById("viewTodos");
  if (!root) return;

  const matrixEl = document.getElementById("todoMatrix");
  const listEl = document.getElementById("todoList");
  const saveMsg = document.getElementById("todoSaveMsg");
  const updatedAtEl = document.getElementById("todoUpdatedAt");
  const detailPanel = document.getElementById("todoDetailPanel");
  const detailTitle = document.getElementById("todoDetailTitle");
  const detailBody = document.getElementById("todoDetailBody");

  const formName = document.getElementById("todoFormName");
  const formDetails = document.getElementById("todoFormDetails");
  const formDate = document.getElementById("todoFormDate");
  const formQuadrant = document.getElementById("todoFormQuadrant");

  function genId() {
    return `t_${appNowDate().getTime().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
  }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function itemsForQuadrant(q) {
    return items.filter((item) => item.quadrant === q);
  }

  function renderMatrix() {
    if (!matrixEl) return;
    matrixEl.innerHTML = MATRIX_ORDER.map((q) => {
      const meta = QUADRANT_META[q];
      const qItems = itemsForQuadrant(q);
      const chips = qItems.length
        ? qItems
            .map(
              (item) =>
                `<button type="button" class="todo-chip" data-todo-id="${escapeHtml(item.id)}" title="点击查看详情">${escapeHtml(item.name)}</button>`,
            )
            .join("")
        : '<p class="todo-quadrant-empty muted small">暂无事项</p>';
      return `
        <div class="todo-quadrant todo-quadrant-${q.toLowerCase()}" data-quadrant="${q}">
          <div class="todo-quadrant-head">
            <span class="todo-quadrant-badge" style="background:${meta.color}">${escapeHtml(meta.label)}</span>
            <span class="muted small">${escapeHtml(meta.hint)}</span>
          </div>
          <div class="todo-quadrant-items">${chips}</div>
        </div>`;
    }).join("");

    matrixEl.querySelectorAll(".todo-chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-todo-id");
        showDetail(id);
      });
    });
  }

  function renderList() {
    if (!listEl) return;
    if (!items.length) {
      listEl.innerHTML = '<p class="muted small">暂无待办，请在下方添加。</p>';
      return;
    }
    const sorted = [...items].sort((a, b) => {
      const qDiff = QUADRANTS.indexOf(a.quadrant) - QUADRANTS.indexOf(b.quadrant);
      if (qDiff !== 0) return qDiff;
      return (a.date || "").localeCompare(b.date || "");
    });
    listEl.innerHTML = sorted
      .map((item) => {
        const meta = QUADRANT_META[item.quadrant] || QUADRANT_META.IV;
        const dateLabel = item.date ? ` · ${escapeHtml(item.date)}` : "";
        return `
          <article class="todo-list-item" data-todo-id="${escapeHtml(item.id)}">
            <span class="todo-quadrant-badge todo-list-badge" style="background:${meta.color}">${escapeHtml(item.quadrant)}</span>
            <div class="todo-list-body">
              <strong>${escapeHtml(item.name)}</strong>
              <p class="muted small">${escapeHtml(meta.hint)}${dateLabel}</p>
            </div>
            <button type="button" class="btn btn-ghost btn-sm todo-list-del" data-todo-id="${escapeHtml(item.id)}">删除</button>
          </article>`;
      })
      .join("");

    listEl.querySelectorAll(".todo-list-del").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-todo-id");
        items = items.filter((item) => item.id !== id);
        dirty = true;
        hideDetail();
        renderAll();
        void autoSave();
      });
    });

    listEl.querySelectorAll(".todo-list-item").forEach((row) => {
      row.addEventListener("click", (e) => {
        if (e.target.closest(".todo-list-del")) return;
        const id = row.getAttribute("data-todo-id");
        showDetail(id);
      });
    });
  }

  function showDetail(id) {
    const item = items.find((t) => t.id === id);
    if (!item || !detailPanel) return;
    const meta = QUADRANT_META[item.quadrant] || QUADRANT_META.IV;
    if (detailTitle) detailTitle.textContent = item.name;
    if (detailBody) {
      detailBody.innerHTML = `
        <p><span class="muted">重要程度：</span>${escapeHtml(meta.label)}（${escapeHtml(meta.hint)}）</p>
        <p><span class="muted">日期：</span>${item.date ? escapeHtml(item.date) : "未设置"}</p>
        <p><span class="muted">细节：</span></p>
        <p class="todo-detail-text">${item.details ? escapeHtml(item.details) : "（无）"}</p>
        <button type="button" class="btn btn-ghost btn-sm" id="todoDetailClose">关闭</button>
        <button type="button" class="btn btn-ghost btn-sm todo-detail-del" data-todo-id="${escapeHtml(item.id)}">删除此项</button>`;
      detailBody.querySelector("#todoDetailClose")?.addEventListener("click", hideDetail);
      detailBody.querySelector(".todo-detail-del")?.addEventListener("click", () => {
        items = items.filter((t) => t.id !== item.id);
        dirty = true;
        hideDetail();
        renderAll();
        void autoSave();
      });
    }
    detailPanel.classList.remove("hidden");
  }

  function hideDetail() {
    detailPanel?.classList.add("hidden");
  }

  function renderAll() {
    renderMatrix();
    renderList();
  }

  function resetForm() {
    if (formName) formName.value = "";
    if (formDetails) formDetails.value = "";
    if (formDate) formDate.value = "";
    if (formQuadrant) formQuadrant.value = "II";
  }

  function addFromForm() {
    const name = (formName?.value || "").trim();
    if (!name) {
      window.alert("请填写待办名称");
      return;
    }
    const quadrant = (formQuadrant?.value || "IV").toUpperCase();
    items.push({
      id: genId(),
      name,
      details: (formDetails?.value || "").trim(),
      date: (formDate?.value || "").trim(),
      quadrant: QUADRANTS.includes(quadrant) ? quadrant : "IV",
      created_at: appNowDate().toISOString(),
    });
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
    const res = await apiFetch("/api/auth/todos");
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    items = Array.isArray(data.items) ? data.items : [];
    dirty = false;
    loadedForUser = getAuthUser();
    if (updatedAtEl) {
      updatedAtEl.textContent = data.updated_at
        ? `上次保存：${data.updated_at}`
        : "尚未保存过待办事项";
    }
    hideDetail();
    renderAll();
  }

  async function saveToServer() {
    const res = await apiFetch("/api/auth/todos", {
      method: "PUT",
      body: JSON.stringify({ items }),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    items = Array.isArray(data.items) ? data.items : items;
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
        /* retry below */
      }
    }
    saveInFlight = (async () => {
      await saveToServer();
      showSaveStatus("已自动保存", true);
    })();
    try {
      await saveInFlight;
    } catch (e) {
      showSaveStatus("自动保存失败，请点击「保存待办」重试", false);
      throw e;
    } finally {
      saveInFlight = null;
    }
  }

  function bindControls() {
    document.getElementById("todoAddBtn")?.addEventListener("click", addFromForm);
    document.getElementById("todoSaveBtn")?.addEventListener("click", async () => {
      showSaveStatus("正在保存…", true);
      try {
        await saveToServer();
        showSaveStatus("已保存", true);
      } catch (e) {
        showSaveStatus("保存失败：" + (e.message || e), false);
      }
    });
    document.getElementById("todoDetailDismiss")?.addEventListener("click", hideDetail);
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

  function preloadTodoMatrix() {
    ensureControls();
    if (isLoadedForCurrentUser()) return Promise.resolve();
    return loadFromServer();
  }

  function initTodoMatrix() {
    ensureControls();
    if (isLoadedForCurrentUser()) {
      renderAll();
      return Promise.resolve();
    }
    return loadFromServer();
  }

  window.initTodoMatrix = initTodoMatrix;
  window.preloadTodoMatrix = preloadTodoMatrix;
  window.reloadTodoMatrix = loadFromServer;
  window.todoMatrixDirty = () => dirty;
})();
