const queryInput = document.getElementById("queryInput");
const sendBtn = document.getElementById("sendBtn");
const rebuildBtn = document.getElementById("rebuildBtn");
const kbBadge = document.getElementById("kbBadge");
const kbInfo = document.getElementById("kbInfo");
const enableWeb = document.getElementById("enableWeb");
const faqChips = document.getElementById("faqChips");

const longGoal = document.getElementById("longGoal");
const longIntakeJson = document.getElementById("longIntakeJson");
const longReportOut = document.getElementById("longReportOut");
const longUseWeb = document.getElementById("longUseWeb");
const btnClarify = document.getElementById("btnClarify");
const btnLoadTemplate = document.getElementById("btnLoadTemplate");
const btnReport = document.getElementById("btnReport");
const clarifyBox = document.getElementById("clarifyBox");

const quickEmpty = document.getElementById("quickEmpty");
const quickLoading = document.getElementById("quickLoading");
const answerCard = document.getElementById("answerCard");
const answerQuestion = document.getElementById("answerQuestion");
const answerMeta = document.getElementById("answerMeta");
const secConclusion = document.getElementById("secConclusion");
const secRecommendation = document.getElementById("secRecommendation");
const secRecommendationEmpty = document.getElementById("secRecommendationEmpty");
const secRisks = document.getElementById("secRisks");
const secRisksEmpty = document.getElementById("secRisksEmpty");
const secNext = document.getElementById("secNext");
const secNextEmpty = document.getElementById("secNextEmpty");
const answerRaw = document.getElementById("answerRaw");

const evidenceEmpty = document.getElementById("evidenceEmpty");
const evidenceGroups = document.getElementById("evidenceGroups");
const evidenceSubtitle = document.getElementById("evidenceSubtitle");

const kbScopeSeg = document.getElementById("kbScopeSeg");
const kbGroupCards = document.getElementById("kbGroupCards");
const kbDebugLoadSnap = document.getElementById("kbDebugLoadSnap");
const kbDebugSnapOut = document.getElementById("kbDebugSnapOut");
const kbDebugQuery = document.getElementById("kbDebugQuery");
const kbDebugScopeSeg = document.getElementById("kbDebugScopeSeg");
const kbDebugWeb = document.getElementById("kbDebugWeb");
const kbDebugRunTrace = document.getElementById("kbDebugRunTrace");
const kbDebugTraceOut = document.getElementById("kbDebugTraceOut");
const xhsVerifyQuery = document.getElementById("xhsVerifyQuery");
const xhsVerifyTopK = document.getElementById("xhsVerifyTopK");
const xhsVerifyRow = document.getElementById("xhsVerifyRow");
const xhsVerifyRun = document.getElementById("xhsVerifyRun");
const xhsVerifyOut = document.getElementById("xhsVerifyOut");
const officialVerifyRun = document.getElementById("officialVerifyRun");
const officialVerifyOut = document.getElementById("officialVerifyOut");
const waTestQuery = document.getElementById("waTestQuery");
const waTestScenario = document.getElementById("waTestScenario");
const waForceFallback = document.getElementById("waForceFallback");
const waTestRun = document.getElementById("waTestRun");
const waTestOut = document.getElementById("waTestOut");

let kbScope = "hybrid";
let kbDebugScope = "hybrid";

const views = {
  quick: document.getElementById("viewQuick"),
  long: document.getElementById("viewLong"),
  kb: document.getElementById("viewKb"),
  kbdebug: document.getElementById("viewKbDebug"),
  official: document.getElementById("viewOfficial"),
  experience: document.getElementById("viewExperience"),
  settings: document.getElementById("viewSettings"),
};

const navButtons = document.querySelectorAll(".nav-item");

function wireScopeSegment(container, onSelect) {
  if (!container) return;
  container.querySelectorAll(".scope-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      container.querySelectorAll(".scope-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      onSelect(btn.getAttribute("data-kb-scope"));
    });
  });
}

const FAQ_LIST = [
  "中国人民大学保研申请条件有哪些？",
  "人大金融专硕夏令营一般考察什么？",
  "保研简历里科研经历怎么写？",
  "预推免和夏令营有什么区别？",
  "保研经验：如何准备面试？",
];

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatTiming(t) {
  if (!t) return "";
  return `路由 ${t.route_ms}ms · 检索 ${t.retrieve_ms}ms · 回答 ${t.answer_ms}ms · 合计 ${t.total_ms}ms`;
}

/** 将模型返回的纯文本转为 HTML 片段（不含外层包装）。 */
function formatAssistantBody(text) {
  const src = String(text || "");
  let t = escapeHtml(src);
  t = t.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");

  const lines = t.split("\n");
  const parts = [];
  let textBuf = [];

  function flushText() {
    if (!textBuf.length) return;
    if (textBuf.length === 1) {
      const chunk = textBuf[0];
      const idx = chunk.search(/\d+\.\s+/);
      const head = idx > 0 ? chunk.slice(0, idx).trim() : "";
      const tail = idx >= 0 ? chunk.slice(idx > 0 ? idx : 0) : chunk;
      const splitPoints = tail.split(/\s+(?=\d+\.\s+)/).filter(Boolean);
      if (splitPoints.length >= 1) {
        const items = [];
        let allMatch = true;
        for (const p of splitPoints) {
          const m = p.match(/^\d+\.\s+(.*)$/);
          if (!m) {
            allMatch = false;
            break;
          }
          items.push(m[1]);
        }
        if (allMatch && items.length >= 2) {
          if (head) parts.push(`<p>${head}</p>`);
          parts.push(`<ol>${items.map((x) => `<li>${x}</li>`).join("")}</ol>`);
          textBuf = [];
          return;
        }
        if (allMatch && items.length === 1 && head) {
          parts.push(`<p>${head}</p>`);
          parts.push(`<ol>${items.map((x) => `<li>${x}</li>`).join("")}</ol>`);
          textBuf = [];
          return;
        }
      }
    }
    parts.push(`<p>${textBuf.join("<br>")}</p>`);
    textBuf = [];
  }
  let listBuf = [];
  function flushList() {
    if (!listBuf.length) return;
    parts.push(`<ol>${listBuf.map((item) => `<li>${item}</li>`).join("")}</ol>`);
    listBuf = [];
  }

  for (const line of lines) {
    const m = line.match(/^\s*(\d+)\.\s+(.*)$/);
    if (m) {
      flushText();
      listBuf.push(m[2]);
    } else {
      flushList();
      if (line.trim() === "") {
        flushText();
      } else {
        textBuf.push(line);
      }
    }
  }
  flushList();
  flushText();

  return parts.length ? parts.join("") : "<p class=\"muted\">（无内容）</p>";
}

function parseAnswerSections(text) {
  const raw = String(text || "").trim();
  const lines = raw.split("\n");
  const buckets = { conclusion: [], recommendation: [], risks: [], nextSteps: [] };
  let current = "conclusion";
  const headerRes = [
    { re: /^(#{1,3}\s*)?(结论|总结|核心结论|要点概览)[:：]?\s*$/i, key: "conclusion" },
    { re: /^(#{1,3}\s*)?(建议|推荐|策略|行动建议|规划建议)[:：]?\s*$/i, key: "recommendation" },
    { re: /^(#{1,3}\s*)?(风险|注意|注意事项|免责声明|提醒)[:：]?\s*$/i, key: "risks" },
    { re: /^(#{1,3}\s*)?(下一步|后续步骤|时间线|待办)[:：]?\s*$/i, key: "nextSteps" },
  ];

  for (const line of lines) {
    const trimmed = line.trim();
    let hit = null;
    for (const { re, key } of headerRes) {
      if (re.test(trimmed)) {
        hit = key;
        break;
      }
    }
    if (hit) {
      current = hit;
      continue;
    }
    buckets[current].push(line);
  }

  const out = {
    conclusion: buckets.conclusion.join("\n").trim(),
    recommendation: buckets.recommendation.join("\n").trim(),
    risks: buckets.risks.join("\n").trim(),
    nextSteps: buckets.nextSteps.join("\n").trim(),
  };

  if (!out.conclusion && !out.recommendation && !out.risks && !out.nextSteps && raw) {
    out.conclusion = raw;
  }
  if (!out.conclusion && (out.recommendation || out.risks || out.nextSteps)) {
    out.conclusion = "本条回答未单独标注「结论」小节，请结合下列结构化段落阅读。";
  }
  return out;
}

/** 模型按约定输出的三段结构（### 【官方结论】等） */
function parseTripleHeadingAnswer(text) {
  const raw = String(text || "").trim();
  if (!/【官方结论】/.test(raw) && !/【经验参考】/.test(raw)) {
    return { official: "", experience: "", uncertainty: "", next: "" };
  }
  const lines = raw.split("\n");
  const buckets = { official: [], experience: [], uncertainty: [], next: [] };
  const preamble = [];
  let current = null;
  const headerRes = [
    { re: /^(#{1,6}\s*)?【官方结论】[:：]?\s*$/, key: "official" },
    { re: /^(#{1,6}\s*)?【经验参考】[:：]?\s*$/, key: "experience" },
    { re: /^(#{1,6}\s*)?【不确定性\s*\/\s*冲突说明】[:：]?\s*$/, key: "uncertainty" },
    { re: /^(#{1,6}\s*)?【不确定性/, key: "uncertainty" },
    { re: /^(#{1,6}\s*)?【下一步/, key: "next" },
  ];

  for (const line of lines) {
    const trimmed = line.trim();
    let hit = null;
    for (const { re, key } of headerRes) {
      if (re.test(trimmed)) {
        hit = key;
        break;
      }
    }
    if (hit) {
      if (current === null && preamble.length) {
        buckets[hit].push(...preamble.splice(0));
      }
      current = hit;
      continue;
    }
    if (current === null) preamble.push(line);
    else buckets[current].push(line);
  }
  if (preamble.length) {
    (buckets.official.length ? buckets.official : buckets.experience).push(...preamble);
  }

  return {
    official: buckets.official.join("\n").trim(),
    experience: buckets.experience.join("\n").trim(),
    uncertainty: buckets.uncertainty.join("\n").trim(),
    next: buckets.next.join("\n").trim(),
  };
}

function parseAnswerForUICard(text) {
  const triple = parseTripleHeadingAnswer(text);
  if (triple.official || triple.experience || triple.uncertainty || triple.next) {
    return {
      official: triple.official,
      experience: triple.experience,
      uncertainty: triple.uncertainty,
      next: triple.next,
    };
  }
  const leg = parseAnswerSections(text);
  return {
    official: leg.conclusion,
    experience: leg.recommendation,
    uncertainty: leg.risks,
    next: leg.nextSteps,
  };
}

function legacyCredibilityFromConfidence(conf) {
  const c = Number(conf);
  if (Number.isNaN(c)) return { cls: "badge-cred-med", label: "可信度：未知" };
  if (c >= 0.82) return { cls: "badge-cred-high", label: "可信度：较高" };
  if (c >= 0.6) return { cls: "badge-cred-med", label: "可信度：中等" };
  return { cls: "badge-cred-low", label: "可信度：偏低" };
}

function credibilityBadgeFromDoc(doc) {
  const level = doc.credibility_level;
  if (level === "high") return { cls: "badge-cred-high", label: "可信·高" };
  if (level === "medium") return { cls: "badge-cred-med", label: "可信·中" };
  if (level === "low") return { cls: "badge-cred-low", label: "可信·低" };
  return legacyCredibilityFromConfidence(doc.confidence);
}

function freshnessBadgeFromDoc(doc) {
  const f = doc.freshness;
  if (f === "possibly_outdated") return { cls: "badge-fresh-old", label: "可能过时" };
  if (f === "web_unverified") return { cls: "badge-fresh-web", label: "网页未验证" };
  if (f === "indexed_campus_doc") return { cls: "badge-fresh-indexed", label: "校本索引" };
  return null;
}

function classifySource(doc) {
  const st = doc.source_type;
  if (st === "official_school_document" || doc.source === "official_pdf") {
    return { kind: "official", groupLabel: "正式文件", badgeClass: "badge-official", badgeText: "正式文件" };
  }
  if (st === "experience_note" || doc.source === "xiaohongshu_excel") {
    return { kind: "experience", groupLabel: "经验笔记", badgeClass: "badge-exp", badgeText: "经验" };
  }
  const s = String(doc.source || "").toLowerCase();
  if (st === "web_citation" || s.startsWith("web_")) {
    const sub =
      s === "web_ruc"
        ? "人大域名"
        : s === "web_zhihu"
          ? "知乎"
          : s === "web_wechat"
            ? "微信"
            : s === "web_xhs"
              ? "小红书"
              : "网页";
    return { kind: "web", groupLabel: "联网网页", badgeClass: "badge-web", badgeText: "联网", sub };
  }
  if (s === "brochure") {
    return { kind: "official_doc", groupLabel: "简章类", badgeClass: "badge-doc", badgeText: "简章" };
  }
  if (s === "fallback") {
    return { kind: "model", groupLabel: "系统提示", badgeClass: "badge-model", badgeText: "模型" };
  }
  return { kind: "other", groupLabel: "其他", badgeClass: "badge-neutral", badgeText: s || "来源" };
}

function suspectedAd(doc, kind) {
  if (doc.suspected_ad === true) return true;
  const t = `${doc.title || ""}\n${doc.content || ""}`;
  if (/推广|广告|加微|私信我|扫码|带货|优惠券/i.test(t)) return true;
  if ((kind === "experience" || doc.source === "web_xhs") && Number(doc.confidence) < 0.56) return true;
  return false;
}

function snippetFromContent(content, maxLen = 220) {
  const c = String(content || "").replace(/\s+/g, " ").trim();
  const linkIdx = c.lastIndexOf("链接：");
  let body = c;
  if (linkIdx >= 0) body = c.slice(0, linkIdx).trim();
  if (body.length <= maxLen) return body;
  return `${body.slice(0, maxLen - 1)}…`;
}

function extractLink(content) {
  const c = String(content || "");
  const m = c.match(/链接：(https?:\/\/[^\s]+)/);
  return m ? m[1] : "";
}

function renderEvidencePanel(sources) {
  if (!sources || !sources.length) {
    evidenceEmpty.classList.remove("hidden");
    evidenceGroups.classList.add("hidden");
    evidenceGroups.innerHTML = "";
    evidenceSubtitle.textContent = "本次回答未返回结构化引用。";
    return;
  }

  evidenceEmpty.classList.add("hidden");
  evidenceGroups.classList.remove("hidden");
  evidenceSubtitle.textContent = `共 ${sources.length} 条引用，已按类型分组。`;

  const grouped = new Map();
  const order = ["official", "official_doc", "experience", "web", "model", "other"];

  function roleLabel(role) {
    const m = {
      primary_policy: "主证据·政策",
      supplementary_experience: "补充·经验",
      supplementary_web: "补充·网页",
      system: "系统",
    };
    return m[role] || "";
  }

  for (const doc of sources) {
    const meta = classifySource(doc);
    const k = meta.kind;
    if (!grouped.has(k)) grouped.set(k, { meta, items: [] });
    grouped.get(k).items.push({ doc, meta });
  }

  const frag = document.createDocumentFragment();

  for (const kind of order) {
    const g = grouped.get(kind);
    if (!g) continue;
    const wrap = document.createElement("div");
    wrap.className = "evidence-group";
    const h = document.createElement("h3");
    h.className = "evidence-group-title";
    h.textContent = g.meta.groupLabel;
    wrap.appendChild(h);

    for (const { doc, meta } of g.items) {
      const cred = credibilityBadgeFromDoc(doc);
      const fresh = freshnessBadgeFromDoc(doc);
      const ad = suspectedAd(doc, meta.kind);
      const snip = snippetFromContent(doc.content);
      const href = extractLink(doc.content);
      const role = doc.evidence_role ? roleLabel(doc.evidence_role) : "";
      const reasons = Array.isArray(doc.ad_risk_reasons) ? doc.ad_risk_reasons.filter(Boolean) : [];
      const reasonLine =
        ad && reasons.length
          ? `<p class="evidence-warn-line">推广风险线索：${escapeHtml(reasons.join("；"))}</p>`
          : ad
            ? `<p class="evidence-warn-line">启发式命中推广/引流风险，请自行甄别。</p>`
            : "";

      const item = document.createElement("div");
      item.className = "evidence-item";
      const title = escapeHtml(doc.title || "(无标题)");
      const subBadge =
        meta.kind === "web" && meta.sub
          ? `<span class="badge badge-web" style="font-size:0.6rem">${escapeHtml(meta.sub)}</span>`
          : "";
      const roleBadge = role
        ? `<span class="badge badge-neutral" style="font-size:0.6rem;text-transform:none">${escapeHtml(role)}</span>`
        : "";
      const freshHtml = fresh ? `<span class="badge ${fresh.cls}">${escapeHtml(fresh.label)}</span>` : "";
      const kbGroupBadge = doc.kb_group
        ? `<span class="badge badge-neutral" style="font-size:0.6rem;text-transform:none" title="KB 分组">${escapeHtml(
            doc.kb_group,
          )}</span>`
        : "";

      item.innerHTML = `
        <div class="evidence-item-head">
          <span class="badge ${meta.badgeClass}">${escapeHtml(meta.badgeText)}</span>
          ${kbGroupBadge}
          ${subBadge}
          ${roleBadge}
          <span class="badge ${cred.cls}">${escapeHtml(cred.label)}</span>
          ${freshHtml}
          ${ad ? '<span class="badge badge-ad">推广风险</span>' : ""}
        </div>
        <p class="evidence-item-title">${title}</p>
        <p class="evidence-snippet">${escapeHtml(snip)}</p>
        ${reasonLine}
        ${
          href
            ? `<div class="evidence-meta-row"><a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer" class="muted small">打开原文</a></div>`
            : ""
        }
      `;
      wrap.appendChild(item);
    }
    frag.appendChild(wrap);
  }

  evidenceGroups.innerHTML = "";
  evidenceGroups.appendChild(frag);
}

function setSectionContent(el, emptyEl, text) {
  const t = String(text || "").trim();
  if (t) {
    el.innerHTML = formatAssistantBody(t);
    if (emptyEl) emptyEl.classList.add("hidden");
  } else {
    el.innerHTML = "";
    if (emptyEl) emptyEl.classList.remove("hidden");
  }
}

function showAnswerCard(query, data) {
  const card = parseAnswerForUICard(data.answer || "");
  answerQuestion.textContent = query;
  answerMeta.textContent = `问题类型：${data.question_type || "—"} · ${formatTiming(data.timing)}`;

  if (card.official.trim()) {
    secConclusion.innerHTML = formatAssistantBody(card.official);
  } else {
    secConclusion.innerHTML = '<p class="muted">（未解析到「官方结论」段落，请展开下方完整原文。）</p>';
  }

  setSectionContent(secRecommendation, secRecommendationEmpty, card.experience);
  setSectionContent(secRisks, secRisksEmpty, card.uncertainty);
  setSectionContent(secNext, secNextEmpty, card.next);

  answerRaw.innerHTML = formatAssistantBody(data.answer || "");

  quickEmpty.classList.add("hidden");
  quickLoading.classList.add("hidden");
  answerCard.classList.remove("hidden");
  renderEvidencePanel(data.sources || []);
}

function resetEvidencePanelPlaceholder() {
  evidenceEmpty.classList.remove("hidden");
  evidenceGroups.classList.add("hidden");
  evidenceGroups.innerHTML = "";
  evidenceSubtitle.textContent = "在「快问快答」生成回答后，此处展示分层引用。";
}

function setActiveView(viewId) {
  navButtons.forEach((btn) => {
    btn.classList.toggle("active", btn.getAttribute("data-view") === viewId);
  });
  Object.entries(views).forEach(([id, el]) => {
    if (!el) return;
    el.classList.toggle("hidden", id !== viewId);
  });
}

navButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    const v = btn.getAttribute("data-view");
    if (v) setActiveView(v);
  });
});

function renderFaqChips() {
  faqChips.innerHTML = "";
  FAQ_LIST.forEach((q) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip";
    b.textContent = q;
    b.addEventListener("click", () => {
      queryInput.value = q;
      queryInput.focus();
    });
    faqChips.appendChild(b);
  });
}

function renderKbGroupCards(groups) {
  if (!kbGroupCards) return;
  kbGroupCards.innerHTML = "";
  if (!groups || !groups.length) {
    kbGroupCards.innerHTML = '<p class="muted small">暂无分组统计；可点击「重建索引」。</p>';
    return;
  }
  for (const g of groups) {
    const card = document.createElement("div");
    card.className = "kb-group-card";
    const title = g.label || g.kb_group || "分组";
    const bits = [];
    if (g.kb_group) bits.push(`分组 ID：${g.kb_group}`);
    if (g.file_kind) bits.push(`类型：${g.file_kind}`);
    if (g.chunk_count != null) bits.push(`索引条数：${g.chunk_count}`);
    if (g.file_count != null) bits.push(`PDF 文件：${g.file_count}`);
    if (g.source_rows != null) bits.push(`Excel 行：${g.source_rows}`);
    card.innerHTML = `<h3>${escapeHtml(title)}</h3><p class="kb-group-meta">${escapeHtml(bits.join(" · "))}</p>`;
    kbGroupCards.appendChild(card);
  }
}

async function fetchKbStatus() {
  try {
    const res = await fetch("/api/kb/status");
    const data = await res.json();
    kbBadge.textContent = data.loaded ? "知识库：已加载" : "知识库：未加载";
    kbInfo.textContent = `经验索引条数 ${data.row_count} · 正式 ${data.official_chunk_count ?? "—"} · 经验 ${data.experience_chunk_count ?? "—"} · 更新 ${data.loaded_at || "—"} · 指纹 ${data.checksum || "—"}`;
    renderKbGroupCards(data.kb_groups);
  } catch (err) {
    kbBadge.textContent = "知识库：读取失败";
    kbInfo.textContent = String(err);
  }
}

async function rebuildKb() {
  rebuildBtn.disabled = true;
  rebuildBtn.textContent = "重建中…";
  try {
    const res = await fetch("/api/kb/rebuild", { method: "POST" });
    const data = await res.json();
    await fetchKbStatus();
    kbInfo.textContent += ` · 已重建，当前 ${data.row_count} 条`;
  } catch (err) {
    kbInfo.textContent = `重建失败：${err}`;
  } finally {
    rebuildBtn.disabled = false;
    rebuildBtn.textContent = "重建索引";
  }
}

async function sendQuery() {
  const query = queryInput.value.trim();
  if (!query) return;

  sendBtn.disabled = true;
  quickEmpty.classList.add("hidden");
  answerCard.classList.add("hidden");
  quickLoading.classList.remove("hidden");
  resetEvidencePanelPlaceholder();
  evidenceSubtitle.textContent = "正在检索并整理引用…";

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        enable_web_search: enableWeb.checked,
        kb_scope: kbScope,
      }),
    });
    const data = await res.json();
    showAnswerCard(query, data);
  } catch (err) {
    quickLoading.classList.add("hidden");
    answerCard.classList.remove("hidden");
    answerQuestion.textContent = query;
    answerMeta.textContent = "请求失败";
    const msg = String(err);
    secConclusion.innerHTML = `<p class="muted">${escapeHtml(msg)}</p>`;
    setSectionContent(secRecommendation, secRecommendationEmpty, "");
    setSectionContent(secRisks, secRisksEmpty, "");
    setSectionContent(secNext, secNextEmpty, "");
    answerRaw.innerHTML = "";
    renderEvidencePanel([]);
    evidenceSubtitle.textContent = "请求失败，无引用。";
  } finally {
    sendBtn.disabled = false;
    queryInput.focus();
  }
}

sendBtn.addEventListener("click", sendQuery);
rebuildBtn.addEventListener("click", rebuildKb);
queryInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendQuery();
  }
});

btnLoadTemplate.addEventListener("click", async () => {
  try {
    const res = await fetch("/api/long-chat/templates");
    const data = await res.json();
    const intake = data.intake || {};
    if (longGoal.value.trim()) {
      intake.meta = intake.meta || {};
      intake.meta.goal = longGoal.value.trim();
    }
    longIntakeJson.value = JSON.stringify(intake, null, 2);
  } catch (e) {
    longIntakeJson.value = `// 加载模板失败：${e}`;
  }
});

btnClarify.addEventListener("click", async () => {
  const goal = longGoal.value.trim();
  if (!goal) {
    clarifyBox.textContent = "请先填写目标描述。";
    clarifyBox.classList.remove("hidden");
    return;
  }
  btnClarify.disabled = true;
  try {
    let partial = null;
    try {
      partial = JSON.parse(longIntakeJson.value || "{}");
    } catch {
      partial = null;
    }
    const res = await fetch("/api/long-chat/clarify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ goal, partial_intake: partial }),
    });
    const data = await res.json();
    const qs = (data.questions || []).map((q, i) => `${i + 1}. ${q}`).join("\n");
    clarifyBox.textContent = qs || "（未返回追问）";
    clarifyBox.classList.remove("hidden");
  } catch (e) {
    clarifyBox.textContent = `追问生成失败：${e}`;
    clarifyBox.classList.remove("hidden");
  } finally {
    btnClarify.disabled = false;
  }
});

btnReport.addEventListener("click", async () => {
  const goal = longGoal.value.trim();
  if (!goal) {
    longReportOut.textContent = "请先填写目标描述。";
    return;
  }
  let intake;
  try {
    intake = JSON.parse(longIntakeJson.value || "{}");
  } catch (e) {
    longReportOut.textContent = `JSON 解析失败：${e}`;
    return;
  }
  intake.meta = intake.meta || {};
  intake.meta.goal = goal;
  btnReport.disabled = true;
  longReportOut.textContent = "生成中…";
  try {
    const res = await fetch("/api/long-chat/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        goal,
        intake,
        use_web: longUseWeb.checked,
      }),
    });
    const data = await res.json();
    longReportOut.textContent = JSON.stringify(data.report, null, 2);
    if (data.latency_ms != null) {
      longReportOut.textContent += `\n\n// latency_ms: ${data.latency_ms}`;
    }
  } catch (e) {
    longReportOut.textContent = `请求失败：${e}`;
  } finally {
    btnReport.disabled = false;
  }
});

wireScopeSegment(kbScopeSeg, (s) => {
  kbScope = s;
});
wireScopeSegment(kbDebugScopeSeg, (s) => {
  kbDebugScope = s;
});

if (kbDebugLoadSnap && kbDebugSnapOut) {
  kbDebugLoadSnap.addEventListener("click", async () => {
    kbDebugSnapOut.textContent = "加载中…";
    try {
      const res = await fetch("/api/kb/debug");
      const raw = await res.text();
      if (!res.ok) {
        kbDebugSnapOut.textContent = `HTTP ${res.status}（404 时需 ENABLE_KB_ADMIN=true）\n${raw}`;
        return;
      }
      kbDebugSnapOut.textContent = JSON.stringify(JSON.parse(raw), null, 2);
    } catch (e) {
      kbDebugSnapOut.textContent = String(e);
    }
  });
}

if (xhsVerifyRun && xhsVerifyOut) {
  xhsVerifyRun.addEventListener("click", async () => {
    const q = xhsVerifyQuery ? xhsVerifyQuery.value.trim() : "";
    const topK = xhsVerifyTopK ? Math.max(1, parseInt(xhsVerifyTopK.value, 10) || 8) : 8;
    const rowRaw = xhsVerifyRow && xhsVerifyRow.value.trim() !== "" ? parseInt(xhsVerifyRow.value, 10) : null;
    const checkRow = rowRaw != null && !Number.isNaN(rowRaw) ? rowRaw : null;
    xhsVerifyOut.textContent = "运行中…";
    try {
      const res = await fetch("/api/kb/xiaohongshu/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: q,
          top_k: topK,
          check_excel_row: checkRow,
          sample_count: 5,
        }),
      });
      const text = await res.text();
      try {
        xhsVerifyOut.textContent = JSON.stringify(JSON.parse(text), null, 2);
      } catch {
        xhsVerifyOut.textContent = text;
      }
    } catch (e) {
      xhsVerifyOut.textContent = String(e);
    }
  });
}

if (officialVerifyRun && officialVerifyOut) {
  officialVerifyRun.addEventListener("click", async () => {
    officialVerifyOut.textContent = "运行中…";
    try {
      const res = await fetch("/api/kb/official/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sample_chunks_per_pdf: 3, top_k_per_question: 5 }),
      });
      const text = await res.text();
      try {
        officialVerifyOut.textContent = JSON.stringify(JSON.parse(text), null, 2);
      } catch {
        officialVerifyOut.textContent = text;
      }
    } catch (e) {
      officialVerifyOut.textContent = String(e);
    }
  });
}

if (waTestRun && waTestOut) {
  waTestRun.addEventListener("click", async () => {
    const q = waTestQuery ? waTestQuery.value.trim() : "";
    if (!q) {
      waTestOut.textContent = "请先输入测试查询。";
      return;
    }
    waTestOut.textContent = "运行中…";
    try {
      const res = await fetch("/api/web-access/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: q,
          scenario: waTestScenario ? waTestScenario.value : "auto",
          force_fallback: waForceFallback ? waForceFallback.checked : false,
        }),
      });
      const text = await res.text();
      try {
        waTestOut.textContent = JSON.stringify(JSON.parse(text), null, 2);
      } catch {
        waTestOut.textContent = text;
      }
    } catch (e) {
      waTestOut.textContent = String(e);
    }
  });
}

if (kbDebugRunTrace && kbDebugTraceOut && kbDebugQuery) {
  kbDebugRunTrace.addEventListener("click", async () => {
    const q = kbDebugQuery.value.trim();
    if (!q) {
      kbDebugTraceOut.textContent = "请先输入测试查询。";
      return;
    }
    kbDebugTraceOut.textContent = "运行中…";
    try {
      let res = await fetch("/api/kb/debug/trace", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: q,
          enable_web_search: kbDebugWeb ? kbDebugWeb.checked : false,
          kb_scope: kbDebugScope,
        }),
      });
      if (res.status === 404) {
        res = await fetch("/api/kb/retrieve-preview", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query: q,
            enable_web_search: kbDebugWeb ? kbDebugWeb.checked : false,
            kb_scope: kbDebugScope,
          }),
        });
      }
      const text = await res.text();
      try {
        kbDebugTraceOut.textContent = JSON.stringify(JSON.parse(text), null, 2);
      } catch {
        kbDebugTraceOut.textContent = text;
      }
    } catch (e) {
      kbDebugTraceOut.textContent = String(e);
    }
  });
}

renderFaqChips();
fetchKbStatus();
setActiveView("quick");
