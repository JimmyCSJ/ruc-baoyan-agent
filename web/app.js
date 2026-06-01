const queryInput = document.getElementById("queryInput");
const sendBtn = document.getElementById("sendBtn");
const rebuildBtn = document.getElementById("rebuildBtn");
const kbBadge = document.getElementById("kbBadge");
const kbInfo = document.getElementById("kbInfo");
const enableWeb = document.getElementById("enableWeb");
const faqChips = document.getElementById("faqChips");
const examQueryInput = document.getElementById("examQueryInput");
const examSendBtn = document.getElementById("examSendBtn");
const examEnableWeb = document.getElementById("examEnableWeb");
const examFaqChips = document.getElementById("examFaqChips");
const examEmpty = document.getElementById("examEmpty");
const examLoading = document.getElementById("examLoading");
const examAnswerCard = document.getElementById("examAnswerCard");
const examAnswerQuestion = document.getElementById("examAnswerQuestion");
const examAnswerMeta = document.getElementById("examAnswerMeta");
const examAnswerBody = document.getElementById("examAnswerBody");
const examReferencesBox = document.getElementById("examReferencesBox");
const examReferences = document.getElementById("examReferences");
const examExecStepsList = document.getElementById("examExecStepsList");

const longReportPreview = document.getElementById("longReportPreview");
const longReportPlaceholder = document.getElementById("longReportPlaceholder");
const longReportJson = document.getElementById("longReportJson");
const longPlanErr = document.getElementById("longPlanErr");

let lastLongPlanPayload = null;
let lastLongPlanReport = null;
/** 最近一次生成成功的原始 Markdown，用于 PDF 直连转换（避免重复调用模型） */
let lastLongPlanMarkdown = "";
let lastLongPlanHtmlUrl = "";
let lastDocs = [];
let lastLongPlanRefs = [];

const quickEmpty = document.getElementById("quickEmpty");
const quickLoading = document.getElementById("quickLoading");
const quickProgressCaption = document.getElementById("quickProgressCaption");
const quickProgressFill = document.getElementById("quickProgressFill");
const quickProgressSteps = document.getElementById("quickProgressSteps");
const answerCard = document.getElementById("answerCard");
const answerQuestion = document.getElementById("answerQuestion");
const answerMeta = document.getElementById("answerMeta");
const execStepsList = document.getElementById("execStepsList");
const execFilesBox = document.getElementById("execFilesBox");
const secConclusion = document.getElementById("secConclusion");
const secRecommendation = document.getElementById("secRecommendation");
const secRecommendationEmpty = document.getElementById("secRecommendationEmpty");
const secRisks = document.getElementById("secRisks");
const secRisksEmpty = document.getElementById("secRisksEmpty");
const secNext = document.getElementById("secNext");
const secNextEmpty = document.getElementById("secNextEmpty");
const answerRaw = document.getElementById("answerRaw");

const btnAnswerPdf = document.getElementById("btnAnswerPdf");
const secReferencesBox = document.getElementById("secReferencesBox");
const secReferences = document.getElementById("secReferences");
const longPlanProgress = document.getElementById("longPlanProgress");
const progressBarFill = document.getElementById("progressBarFill");
const progressStepLabel = document.getElementById("progressStepLabel");
const evidenceEmpty = document.getElementById("evidenceEmpty");
const evidenceGroups = document.getElementById("evidenceGroups");
const evidenceSubtitle = document.getElementById("evidenceSubtitle");
const appShell = document.querySelector(".app");
const evidencePanel = document.querySelector(".evidence-panel");

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
if (enableWeb) enableWeb.checked = true;

const views = {
  quick: document.getElementById("viewQuick"),
  exam: document.getElementById("viewExam"),
  interview: document.getElementById("viewInterview"),
  long: document.getElementById("viewLong"),
  profile: document.getElementById("viewProfile"),
};

const sidebarUserName = document.getElementById("sidebarUserName");
const btnLogout = document.getElementById("btnLogout");
const btnSaveProfile = document.getElementById("btnSaveProfile");
const btnApplyProfileToLong = document.getElementById("btnApplyProfileToLong");
const profileSaveMsg = document.getElementById("profileSaveMsg");
const profileUpdatedAt = document.getElementById("profileUpdatedAt");

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
  "中国人民大学财政金融学院金融专硕保研一般考察哪些维度？我该怎么分阶段准备？",
  "中国人民大学财政金融学院金融、金融科技、保险、税务等方向近年招收规模和考核差异怎么看？",
  "中国人民大学财政金融学院保研材料怎么准备更有竞争力？简历、科研、英语分别怎么证明？",
  "中国人民大学信息学院电子信息/人工智能方向保研通常看什么？",
  "中国人民大学商学院会计方向保研通常看什么？材料、笔试、面试分别怎么准备？",
  "中国人民大学法学院法律硕士保研接收通常关注哪些能力？",
];

const EXAM_FAQ_LIST = [
  "中国人民大学财政金融学院金融专硕保研笔试考什么？题型和复习重点有哪些？",
  "中国人民大学财政金融学院金融科技方向保研笔试会不会考编程？还会考哪些专业内容？",
  "中国人民大学信息学院电子信息/人工智能方向保研笔试通常考什么？",
  "中国人民大学商学院会计方向保研笔试内容和题型有哪些？",
  "中国人民大学法学院法律硕士保研笔试或专业考核通常怎么准备？",
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

function inlineMarkdown(text) {
  return escapeHtml(text)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\[(\d+)\]/g, "<sup>[$1]</sup>");
}

function stripReferenceSection(text) {
  return String(text || "")
    .replace(/\n?#{1,6}\s*【?参考文献】?[\s\S]*$/m, "")
    .replace(/\n?参考文献\s*\n(?:\[\d+\][\s\S]*)?$/m, "")
    .trim();
}

function renderMarkdownTable(lines) {
  const rows = lines
    .filter((line, idx) => idx !== 1)
    .map((line) =>
      line
        .trim()
        .replace(/^\|/, "")
        .replace(/\|$/, "")
        .split("|")
        .map((cell) => inlineMarkdown(cell.trim())),
    );
  if (!rows.length) return "";
  const head = rows[0].map((cell) => `<th>${cell}</th>`).join("");
  const body = rows
    .slice(1)
    .map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`)
    .join("");
  return `<div class="prose-table-wrap"><table class="prose-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

/** 将模型返回的 Markdown/纯文本转为 HTML 片段（不含外层包装）。 */
function formatAssistantBody(text) {
  const src = stripReferenceSection(text);
  if (!src) return "<p class=\"muted\">（无内容）</p>";

  const lines = src.split("\n");
  const parts = [];
  let paraBuf = [];
  let listBuf = [];
  let listType = "";
  let quoteBuf = [];

  function flushPara() {
    if (!paraBuf.length) return;
    parts.push(`<p>${paraBuf.map((x) => inlineMarkdown(x)).join("<br>")}</p>`);
    paraBuf = [];
  }

  function flushList() {
    if (!listBuf.length) return;
    const tag = listType === "ul" ? "ul" : "ol";
    parts.push(`<${tag}>${listBuf.map((item) => `<li>${inlineMarkdown(item)}</li>`).join("")}</${tag}>`);
    listBuf = [];
    listType = "";
  }

  function flushQuote() {
    if (!quoteBuf.length) return;
    parts.push(`<blockquote>${quoteBuf.map((x) => inlineMarkdown(x)).join("<br>")}</blockquote>`);
    quoteBuf = [];
  }

  function flushAll() {
    flushQuote();
    flushList();
    flushPara();
  }

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    if (!trimmed) {
      flushAll();
      i += 1;
      continue;
    }

    if (trimmed.includes("|") && i + 1 < lines.length && /^\s*\|?\s*:?-{3,}/.test(lines[i + 1])) {
      flushAll();
      const tableLines = [line, lines[i + 1]];
      i += 2;
      while (i < lines.length && lines[i].trim().includes("|")) {
        tableLines.push(lines[i]);
        i += 1;
      }
      parts.push(renderMarkdownTable(tableLines));
      continue;
    }

    const heading = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      flushAll();
      const level = Math.min(4, Math.max(3, heading[1].length + 1));
      parts.push(`<h${level} class="prose-heading">${inlineMarkdown(heading[2])}</h${level}>`);
      i += 1;
      continue;
    }

    if (/^-{3,}$/.test(trimmed)) {
      flushAll();
      parts.push("<hr class=\"prose-hr\" />");
      i += 1;
      continue;
    }

    const quote = trimmed.match(/^>\s?(.*)$/);
    if (quote) {
      flushList();
      flushPara();
      quoteBuf.push(quote[1]);
      i += 1;
      continue;
    }

    const unordered = trimmed.match(/^[-*]\s+(.+)$/);
    if (unordered) {
      flushQuote();
      flushPara();
      if (listType && listType !== "ul") flushList();
      listType = "ul";
      listBuf.push(unordered[1]);
      i += 1;
      continue;
    }

    const ordered = trimmed.match(/^\d+\.\s+(.+)$/);
    if (ordered) {
      flushQuote();
      flushPara();
      if (listType && listType !== "ol") flushList();
      listType = "ol";
      listBuf.push(ordered[1]);
      i += 1;
      continue;
    }

    flushQuote();
    flushList();
    paraBuf.push(line);
    i += 1;
  }

  flushAll();
  return parts.length ? parts.join("") : "<p class=\"muted\">（无内容）</p>";
}

/** 长程规划 Markdown（含 ## / ### / 列表）转为预览 HTML。 */
function formatLongPlanMarkdown(src) {
  const raw = String(src || "").trim();
  if (!raw) return "<p class=\"muted\">（无内容）</p>";
  const lines = raw.split("\n");
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const t = line.trim();
    if (t.startsWith("### ")) {
      blocks.push(`<h3 class="lp-h3">${escapeHtml(t.slice(4))}</h3>`);
      i += 1;
      continue;
    }
    if (t.startsWith("## ")) {
      blocks.push(`<h2 class="lp-h2">${escapeHtml(t.slice(3))}</h2>`);
      i += 1;
      continue;
    }
    if (t === "---") {
      blocks.push("<hr class=\"lp-hr\" />");
      i += 1;
      continue;
    }
    if (t.startsWith("- ") || t.startsWith("* ")) {
      const items = [];
      while (i < lines.length) {
        const li = lines[i].trim();
        if (!li.startsWith("- ") && !li.startsWith("* ")) break;
        let body = escapeHtml(li.slice(2));
        body = body.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
        items.push(`<li>${body}</li>`);
        i += 1;
      }
      blocks.push(`<ul class="lp-ul">${items.join("")}</ul>`);
      continue;
    }
    if (t === "") {
      i += 1;
      continue;
    }
    let para = escapeHtml(line);
    para = para.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    blocks.push(`<p class="lp-p">${para}</p>`);
    i += 1;
  }
  return blocks.join("") || "<p class=\"muted\">（无内容）</p>";
}

const LONG_PLAN_REQUIRED_LABELS = {
  current_school: "当前就读学校",
  grade_year: "就读年级",
  college: "就读学院",
  major: "就读专业",
  gpa: "GPA",
  major_rank_percentile: "专业排名（百分比）",
};

const LONG_PLAN_COMPOSITE_REQUIRED_LABELS = {
  target_school: "目标学校",
  target_college: "目标院校",
  target_degree_type: "目标类型",
  english_scores: "英语成绩",
};

function collectCheckedValues(root, selector) {
  if (!root) return [];
  return Array.from(root.querySelectorAll(selector))
    .filter((el) => el.checked)
    .map((el) => String(el.value || "").trim())
    .filter(Boolean);
}

function compactJoin(parts, sep) {
  return parts.map((x) => String(x || "").trim()).filter(Boolean).join(sep);
}

function collectLongPlanPayload() {
  const use_web = document.getElementById("longUseWeb")?.checked ?? true;
  const required = {};
  const optional = {};
  const root = document.getElementById("viewLong");
  if (root) {
    root.querySelectorAll("[data-lp-req]").forEach((el) => {
      const name = el.getAttribute("name");
      if (!name) return;
      required[name] = String(el.value ?? "").trim();
    });
    root.querySelectorAll("[data-lp-opt]").forEach((el) => {
      const name = el.getAttribute("name");
      if (!name) return;
      optional[name] = String(el.value ?? "").trim();
    });
    const targetSchool = String(root.querySelector("[name='target_school']")?.value ?? "").trim();
    const targetCollege = String(root.querySelector("[name='target_college']")?.value ?? "").trim();
    const targetDegreeTypes = collectCheckedValues(root, "[data-lp-target-degree]");
    const englishIelts = String(root.querySelector("[name='english_ielts']")?.value ?? "").trim();
    const englishToefl = String(root.querySelector("[name='english_toefl']")?.value ?? "").trim();
    const englishCet6 = String(root.querySelector("[name='english_cet6']")?.value ?? "").trim();
    required.target_school = targetSchool;
    required.target_college = targetCollege;
    required.target_degree_type = targetDegreeTypes.join(" / ");
    required.target_destination = compactJoin(
      [targetSchool, targetCollege, targetDegreeTypes.length ? targetDegreeTypes.join(" / ") : ""],
      " · ",
    );
    required.english_scores = compactJoin(
      [
        englishIelts ? `雅思 ${englishIelts}` : "",
        englishToefl ? `托福 ${englishToefl}` : "",
        englishCet6 ? `六级 ${englishCet6}` : "",
      ],
      "；",
    );
  }
  return { use_web, required, optional };
}

/** 仅校验必填模块；选填为空不影响。 */
function missingRequiredLongPlanFields(payload) {
  const missing = [];
  for (const k of Object.keys(LONG_PLAN_REQUIRED_LABELS)) {
    if (!(payload.required[k] || "").trim()) missing.push(LONG_PLAN_REQUIRED_LABELS[k]);
  }
  for (const k of Object.keys(LONG_PLAN_COMPOSITE_REQUIRED_LABELS)) {
    if (!(payload.required[k] || "").trim()) missing.push(LONG_PLAN_COMPOSITE_REQUIRED_LABELS[k]);
  }
  return missing;
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

/** 模型按约定输出的三段结构（### 【检索过程】等） */
function parseTripleHeadingAnswer(text) {
  const raw = String(text || "").trim();
  if (!/【总结回答】/.test(raw) && !/【不确定性/.test(raw) && !/【检索过程】/.test(raw)) {
    return { retrieval: "", summary: "", uncertainty: "", next: "" };
  }
  const lines = raw.split("\n");
  const buckets = { retrieval: [], summary: [], uncertainty: [], next: [] };
  const preamble = [];
  let current = null;
  const headerRes = [
    { re: /^(#{1,6}\s*)?【检索过程】[:：]?\s*$/, key: "retrieval" },
    { re: /^(#{1,6}\s*)?【总结回答】[:：]?\s*$/, key: "summary" },
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
    (buckets.summary.length ? buckets.summary : buckets.retrieval).push(...preamble);
  }

  return {
    retrieval: buckets.retrieval.join("\n").trim(),
    summary: buckets.summary.join("\n").trim(),
    uncertainty: buckets.uncertainty.join("\n").trim(),
    next: buckets.next.join("\n").trim(),
  };
}

function parseAnswerForUICard(text) {
  const triple = parseTripleHeadingAnswer(text);
  if (triple.summary || triple.retrieval || triple.uncertainty || triple.next) {
    return {
      official: triple.summary,
      // Retrieval process is already rendered in dedicated execution blocks.
      // Do not mix it into "经验参考" card.
      experience: "",
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
  if (doc.evidence_model_label) {
    const stars = Number(doc.evidence_model_stars || 3);
    const cls = stars >= 5 ? "badge-cred-high" : stars >= 3 ? "badge-cred-med" : "badge-cred-low";
    return { cls, label: doc.evidence_model_label };
  }
  if (doc.evidence_quality_label) {
    const tier = Number(doc.evidence_quality_tier || 4);
    const cls = tier <= 2 ? "badge-cred-high" : tier === 3 ? "badge-cred-med" : "badge-cred-low";
    return { cls, label: doc.evidence_quality_label };
  }
  const level = doc.credibility_level;
  if (level === "high") return { cls: "badge-cred-high", label: "可信·高" };
  if (level === "medium") return { cls: "badge-cred-med", label: "可信·中" };
  if (level === "low") return { cls: "badge-cred-low", label: "可信·低" };
  return legacyCredibilityFromConfidence(doc.confidence);
}

function starsFromDoc(doc) {
  const n = Math.max(1, Math.min(5, Number(doc.evidence_model_stars || 0)));
  if (!n) return "";
  return `${"★".repeat(n)}${"☆".repeat(5 - n)}`;
}

function reviewBlock(doc) {
  return doc && typeof doc.evidence_model_review === "object" ? doc.evidence_model_review : {};
}

function reviewSubLine(review, key, label) {
  const block = review && typeof review[key] === "object" ? review[key] : null;
  if (!block) return "";
  const level = escapeHtml(block.level || "");
  const explanation = escapeHtml(block.explanation || "");
  if (!level && !explanation) return "";
  return `<p class="evidence-note-line"><strong>${label}${level ? `：${level}` : ""}</strong>${explanation ? `｜${explanation}` : ""}</p>`;
}

function classifySource(doc) {
  const st = doc.source_type;
  if (st === "official_school_document" || doc.source === "official_pdf" || doc.source === "official_brochure") {
    return { kind: "official", groupLabel: "正式文件", badgeClass: "badge-official", badgeText: "正式文件" };
  }
  if (st === "experience_note" || doc.source === "public_info_xhs_excel" || doc.source === "xiaohongshu_excel") {
    return { kind: "experience", groupLabel: "公众信息", badgeClass: "badge-exp", badgeText: "公众" };
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
  if (s === "official_brochure") {
    return { kind: "official_doc", groupLabel: "官方简章", badgeClass: "badge-doc", badgeText: "官方简章" };
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
  evidenceSubtitle.textContent = `共 ${sources.length} 条引用，已由模型逐条判断可信度。`;

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
      const ad = suspectedAd(doc, meta.kind);
      const snip = snippetFromContent(doc.content);
      const href = extractLink(doc.content);
      const role = doc.evidence_role ? roleLabel(doc.evidence_role) : "";
      const reasons = Array.isArray(doc.ad_risk_reasons) ? doc.ad_risk_reasons.filter(Boolean) : [];
      const review = reviewBlock(doc);
      const modelRiskNotes = Array.isArray(review.risk_notes) ? review.risk_notes.filter(Boolean) : [];
      const starText = starsFromDoc(doc);
      const reasonLine =
        modelRiskNotes.length
          ? `<p class="evidence-warn-line">风险提示：${escapeHtml(modelRiskNotes.join("；"))}</p>`
          : ad && reasons.length
            ? `<p class="evidence-warn-line">风险提示：${escapeHtml(reasons.join("；"))}</p>`
            : ad
              ? `<p class="evidence-warn-line">风险提示：命中推广/引流信号，请降权看待。</p>`
              : "";
      const usageLine = review.usage_guidance
        ? `<p class="evidence-note-line"><strong>使用建议：</strong>${escapeHtml(review.usage_guidance)}</p>`
        : "";
      const notesLine =
        review && (review.target_match || review.evidence_strength || review.truthfulness_judgment || review.usage_guidance)
          ? [
              reviewSubLine(review, "target_match", "匹配度"),
              reviewSubLine(review, "evidence_strength", "证据强度"),
              reviewSubLine(review, "truthfulness_judgment", "可信判断"),
              usageLine,
            ].join("")
          : ad
            ? `<p class="evidence-warn-line">风险提示：命中推广/引流信号，请降权看待。</p>`
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
          ${starText ? `<span class="evidence-stars" aria-label="可信星级">${starText}</span>` : ""}
          ${ad ? '<span class="badge badge-ad">推广风险</span>' : ""}
        </div>
        <p class="evidence-item-title">${title}</p>
        <p class="evidence-snippet">${escapeHtml(snip)}</p>
        ${notesLine}
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
  if (!el) return;
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
  // Store for PDF download
  lastQuickAnswerText = stripReferenceSection(data.answer || "");
  lastQuickAnswerRefs = Array.isArray(data.references) ? data.references : [];

  const cleanAnswer = stripReferenceSection(data.answer || "");
  const card = parseAnswerForUICard(cleanAnswer);
  answerQuestion.textContent = query;
  answerMeta.textContent = `问题类型：${data.question_type || "—"} · ${formatTiming(data.timing)}`;

  if (execStepsList) {
    const steps = Array.isArray(data.execution_steps) ? data.execution_steps : [];
    execStepsList.innerHTML = steps.length
      ? steps.map((s) => `<li>${escapeHtml(String(s))}</li>`).join("")
      : `<li class="muted small">（未返回步骤信息）</li>`;
  }
  if (execFilesBox) {
    const files = Array.isArray(data.official_files_read) ? data.official_files_read : [];
    execFilesBox.innerHTML = files.length
      ? `本次参考的官方材料：${files.map((f) => `<code class="code">${escapeHtml(String(f))}</code>`).join(" ")}`
      : `本次参考的官方材料：<span class="muted">（无 / 未命中 / 未启用官方检索）</span>`;
  }

  if (card.official.trim()) {
    secConclusion.innerHTML = formatAssistantBody(card.official);
  } else {
    secConclusion.innerHTML = '<p class="muted">（未解析到「官方结论」段落，请展开下方完整原文。）</p>';
  }

  setSectionContent(secRecommendation, secRecommendationEmpty, card.experience);
  setSectionContent(secRisks, secRisksEmpty, card.uncertainty);
  setSectionContent(secNext, secNextEmpty, card.next);

  answerRaw.innerHTML = formatAssistantBody(cleanAnswer);

  // Render references
  const refs = Array.isArray(data.references) ? data.references : [];
  if (refs.length && secReferencesBox && secReferences) {
    secReferencesBox.classList.remove("hidden");
    secReferences.innerHTML = refs
      .map((r) => {
        const url = r.url || "";
        const entry = escapeHtml(r.entry || "");
        const idx = r.index || "";
        const link = url
          ? ` <a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">[链接]</a>`
          : "";
        return `<div class="ref-entry">[${idx}] ${entry}${link}</div>`;
      })
      .join("");
  } else if (secReferencesBox) {
    secReferencesBox.classList.add("hidden");
  }

  if (btnAnswerPdf) btnAnswerPdf.classList.remove("hidden");

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

let lastQuickAnswerText = "";
let lastQuickAnswerRefs = [];

async function downloadAnswerPdf() {
  if (!btnAnswerPdf) return;
  const query = queryInput ? queryInput.value.trim() : "";
  const answer = lastQuickAnswerText;
  if (!answer) return;
  btnAnswerPdf.disabled = true;
  btnAnswerPdf.textContent = "生成中…";
  try {
    const res = await apiFetch("/api/chat/pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        answer,
        references: lastQuickAnswerRefs,
      }),
    });
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(errText || res.statusText);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "ruc-baoyan-answer.pdf";
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    window.alert("PDF 生成失败：" + (e.message || e));
  } finally {
    btnAnswerPdf.disabled = false;
    btnAnswerPdf.textContent = "下载 PDF";
  }
}

function setActiveView(viewId) {
  navButtons.forEach((btn) => {
    btn.classList.toggle("active", btn.getAttribute("data-view") === viewId);
  });
  Object.entries(views).forEach(([id, el]) => {
    if (!el) return;
    el.classList.toggle("hidden", id !== viewId);
  });
  const showEvidence = viewId === "quick" || viewId === "exam";
  appShell?.classList.toggle("evidence-hidden", !showEvidence);
  evidencePanel?.classList.toggle("hidden", !showEvidence);
  if (viewId === "profile") {
    loadUserProfile().catch(() => {});
  }
}

function collectProfilePayload() {
  const body = {};
  document.querySelectorAll("[data-profile]").forEach((el) => {
    const name = el.getAttribute("name");
    if (!name) return;
    body[name] = String(el.value ?? "").trim();
  });
  body.target_degree_types = [];
  document.querySelectorAll("[data-profile-degree]:checked").forEach((el) => {
    body.target_degree_types.push(el.value);
  });
  return body;
}

function fillProfileForm(profile) {
  if (!profile) return;
  document.querySelectorAll("[data-profile]").forEach((el) => {
    const name = el.getAttribute("name");
    if (!name || profile[name] === undefined) return;
    el.value = String(profile[name] ?? "");
  });
  const degrees = profile.target_degree_types || [];
  document.querySelectorAll("[data-profile-degree]").forEach((el) => {
    el.checked = degrees.includes(el.value);
  });
  if (profileUpdatedAt) {
    profileUpdatedAt.textContent = profile.updated_at
      ? `上次保存：${profile.updated_at}`
      : "尚未保存过个人信息";
  }
}

function applyProfileToLongPlanForm(profile) {
  const p = profile || {};
  const root = document.getElementById("viewLong");
  if (!root) return;
  const map = {
    current_school: p.current_school,
    grade_year: p.grade_year,
    college: p.college,
    major: p.major,
    gpa: p.gpa,
    major_rank_percentile: p.major_rank_percentile,
    target_school: p.target_school,
    target_college: p.target_college,
    english_ielts: p.english_ielts,
    english_toefl: p.english_toefl,
    english_cet6: p.english_cet6,
    research_and_competitions: p.research_and_competitions,
    internships: p.internships,
    region_preference: p.region_preference,
    student_work_clubs: p.student_work_clubs,
    career_path_3_5y: p.career_path_3_5y,
    expected_roles_or_industry: p.expected_roles_or_industry,
    admission_prep_stage: p.admission_prep_stage,
    main_concerns: p.main_concerns,
  };
  Object.entries(map).forEach(([name, val]) => {
    const el = root.querySelector(`[name="${name}"]`);
    if (el && val !== undefined) el.value = String(val || "");
  });
  const degrees = p.target_degree_types || [];
  root.querySelectorAll("[data-lp-target-degree]").forEach((el) => {
    el.checked = degrees.includes(el.value);
  });
}

async function loadUserProfile() {
  const res = await apiFetch("/api/auth/profile");
  if (!res.ok) throw new Error("加载个人信息失败");
  const profile = await res.json();
  fillProfileForm(profile);
  return profile;
}

async function saveUserProfile() {
  const body = collectProfilePayload();
  const res = await apiFetch("/api/auth/profile", {
    method: "PUT",
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    throw new Error(typeof detail === "string" ? detail : "保存失败");
  }
  fillProfileForm(data);
  if (profileSaveMsg) {
    profileSaveMsg.textContent = "已保存";
    profileSaveMsg.classList.remove("hidden");
    profileSaveMsg.classList.add("ok");
  }
  return data;
}

async function ensureAuthenticated() {
  const ok = await verifyAuthSession();
  if (!ok) {
    window.location.href = "/";
    return false;
  }
  const user = getAuthUser();
  if (sidebarUserName) sidebarUserName.textContent = user || "已登录";
  try {
    await loadUserProfile();
  } catch {
    /* profile may be empty on first visit */
  }
  return true;
}

navButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    const v = btn.getAttribute("data-view");
    if (v) setActiveView(v);
  });
});

document.querySelectorAll("[data-copy-target]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const targetId = btn.getAttribute("data-copy-target");
    const target = targetId ? document.getElementById(targetId) : null;
    const text = target ? String(target.value || target.textContent || "") : "";
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      const old = btn.textContent;
      btn.textContent = "已复制";
      window.setTimeout(() => {
        btn.textContent = old;
      }, 1200);
    } catch {
      if (target && typeof target.select === "function") target.select();
      window.alert("复制失败，请手动复制文本框内容。");
    }
  });
});

function renderFaqChips() {
  if (!faqChips || !queryInput) return;
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

function renderExamFaqChips() {
  if (!examFaqChips || !examQueryInput) return;
  examFaqChips.innerHTML = "";
  EXAM_FAQ_LIST.forEach((q) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip";
    b.textContent = q;
    b.addEventListener("click", () => {
      examQueryInput.value = q;
      examQueryInput.focus();
    });
    examFaqChips.appendChild(b);
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
    const res = await apiFetch("/api/kb/status");
    const data = await res.json();
    if (kbBadge) kbBadge.textContent = data.loaded ? "知识库：已加载" : "知识库：未加载";
    if (kbInfo)
      kbInfo.textContent = `经验索引条数 ${data.row_count} · 正式 ${data.official_chunk_count ?? "—"} · 经验 ${data.experience_chunk_count ?? "—"} · 更新 ${data.loaded_at || "—"} · 指纹 ${data.checksum || "—"}`;
    renderKbGroupCards(data.kb_groups);
  } catch (err) {
    if (kbBadge) kbBadge.textContent = "知识库：读取失败";
    if (kbInfo) kbInfo.textContent = String(err);
  }
}

async function rebuildKb() {
  if (!rebuildBtn) return;
  rebuildBtn.disabled = true;
  rebuildBtn.textContent = "重建中…";
  try {
    const res = await apiFetch("/api/kb/rebuild", { method: "POST" });
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

async function consumeNdjsonResponse(res, onEvent) {
  if (!res.ok) {
    const errText = await res.text();
    let detail = errText;
    try {
      const j = JSON.parse(errText);
      detail = j.detail || errText;
    } catch {
      /* plain text */
    }
    throw new Error(typeof detail === "string" ? detail : res.statusText || "请求失败");
  }
  const reader = res.body?.getReader();
  if (!reader) throw new Error("浏览器不支持流式响应");
  const decoder = new TextDecoder();
  let buf = "";
  let streamErr = null;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop() ?? "";
    for (const line of lines) {
      const s = line.trim();
      if (!s) continue;
      let ev;
      try {
        ev = JSON.parse(s);
      } catch {
        continue;
      }
      if (ev.stream_error) streamErr = ev.stream_error;
      if (onEvent) onEvent(ev);
    }
  }
  if (streamErr) throw new Error(streamErr);
}

function setQuickProgress(label, pct, steps, files) {
  if (quickProgressCaption) quickProgressCaption.textContent = label || "处理中…";
  if (quickProgressFill && typeof pct === "number") {
    quickProgressFill.style.width = `${Math.min(100, Math.max(0, pct))}%`;
  }
  if (quickProgressSteps) {
    const items = [];
    if (Array.isArray(steps) && steps.length) items.push(...steps);
    if (Array.isArray(files) && files.length) {
      items.push(`已读官方文件：${files.slice(0, 5).join("、")}${files.length > 5 ? " 等" : ""}`);
    }
    if (!items.length && label) items.push(label);
    quickProgressSteps.innerHTML = items
      .map((s) => `<li>${escapeHtml(String(s))}</li>`)
      .join("");
  }
}

async function sendQuery() {
  const query = queryInput.value.trim();
  if (!query) return;

  sendBtn.disabled = true;
  quickEmpty.classList.add("hidden");
  answerCard.classList.add("hidden");
  quickLoading.classList.remove("hidden");
  setQuickProgress("正在提交问题…", 5, ["正在连接服务…"]);
  resetEvidencePanelPlaceholder();
  evidenceSubtitle.textContent = "正在检索并整理引用…";

  try {
    const res = await apiFetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        enable_web_search: enableWeb.checked,
        kb_scope: kbScope,
      }),
    });
    let finalData = null;
    await consumeNdjsonResponse(res, (ev) => {
      if (ev.stage === "progress") {
        setQuickProgress(
          ev.label || "处理中…",
          ev.pct,
          ev.execution_steps,
          ev.official_files_read,
        );
        if (ev.label) evidenceSubtitle.textContent = ev.label;
      }
      if (ev.stage === "done" && ev.data) finalData = ev.data;
    });
    if (!finalData) throw new Error("未收到完整回答");
    showAnswerCard(query, finalData);
  } catch (err) {
    quickLoading.classList.add("hidden");
    answerCard.classList.remove("hidden");
    answerQuestion.textContent = query;
    answerMeta.textContent = "请求失败";
    const msg = err && err.message ? err.message : String(err);
    secConclusion.innerHTML = `<p class="muted">${escapeHtml(msg)}</p>`;
    setSectionContent(secRecommendation, secRecommendationEmpty, "");
    setSectionContent(secRisks, secRisksEmpty, "");
    setSectionContent(secNext, secNextEmpty, "");
    answerRaw.innerHTML = "";
    renderEvidencePanel([]);
    evidenceSubtitle.textContent = "请求失败，无引用。";
  } finally {
    if (sendBtn) sendBtn.disabled = false;
    queryInput?.focus();
  }
}

function showExamAnswer(query, data) {
  if (!examAnswerCard || !examAnswerBody) return;
  examAnswerQuestion.textContent = query;
  examAnswerMeta.textContent = `笔试辅导 · ${data.latency_ms ?? "—"}ms`;
  examAnswerBody.innerHTML = formatAssistantBody(data.answer || "");
  if (examExecStepsList) {
    const steps = Array.isArray(data.execution_steps) ? data.execution_steps : [];
    examExecStepsList.innerHTML = steps.length
      ? steps.map((s) => `<li>${escapeHtml(String(s))}</li>`).join("")
      : `<li class="muted small">（未返回步骤信息）</li>`;
  }
  const refs = Array.isArray(data.references) ? data.references : [];
  if (refs.length && examReferencesBox && examReferences) {
    examReferencesBox.classList.remove("hidden");
    examReferences.innerHTML = refs
      .map((r) => {
        const url = r.url || "";
        const entry = escapeHtml(r.entry || "");
        const idx = r.index || "";
        const link = url
          ? ` <a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">[链接]</a>`
          : "";
        return `<div class="ref-entry">[${idx}] ${entry}${link}</div>`;
      })
      .join("");
  } else if (examReferencesBox) {
    examReferencesBox.classList.add("hidden");
  }
  examEmpty?.classList.add("hidden");
  examLoading?.classList.add("hidden");
  examAnswerCard.classList.remove("hidden");
  renderEvidencePanel(data.sources || []);
  if (evidenceSubtitle) evidenceSubtitle.textContent = `笔试辅导共引用 ${data.sources?.length || 0} 条资料，经验库优先。`;
}

async function sendExamQuery() {
  const query = examQueryInput ? examQueryInput.value.trim() : "";
  if (!query) return;
  if (examSendBtn) examSendBtn.disabled = true;
  examEmpty?.classList.add("hidden");
  examAnswerCard?.classList.add("hidden");
  examLoading?.classList.remove("hidden");
  resetEvidencePanelPlaceholder();
  if (evidenceSubtitle) evidenceSubtitle.textContent = "正在检索笔试相关经验…";

  try {
    const res = await apiFetch("/api/exam-tutoring", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        enable_web_search: examEnableWeb ? examEnableWeb.checked : false,
      }),
    });
    const data = await parseJsonResponse(res);
    if (!res.ok) {
      const detail = data.detail;
      throw new Error(typeof detail === "string" ? detail : data.detail || res.statusText);
    }
    showExamAnswer(query, data);
  } catch (err) {
    examLoading?.classList.add("hidden");
    examAnswerCard?.classList.remove("hidden");
    if (examAnswerQuestion) examAnswerQuestion.textContent = query;
    if (examAnswerMeta) examAnswerMeta.textContent = "请求失败";
    if (examAnswerBody) examAnswerBody.innerHTML = `<p class="muted">${escapeHtml(String(err.message || err))}</p>`;
    renderEvidencePanel([]);
  } finally {
    if (examSendBtn) examSendBtn.disabled = false;
    examQueryInput?.focus();
  }
}

if (sendBtn) sendBtn.addEventListener("click", sendQuery);
if (examSendBtn) examSendBtn.addEventListener("click", sendExamQuery);
if (rebuildBtn) rebuildBtn.addEventListener("click", rebuildKb);
if (queryInput) {
  queryInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendQuery();
    }
  });
}
if (examQueryInput) {
  examQueryInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendExamQuery();
    }
  });
}

const LONG_PLAN_STREAM_LABELS = {
  hydrate_long_plan: "初始化…",
  retrieve_long_plan_kb: "检索知识库…",
  generate_long_plan_part1: "1/5 目标院校…",
  generate_long_plan_part2: "2/5 诊断定位…",
  generate_long_plan_part3: "3/5 时间轴…",
  generate_long_plan_part4: "4/5 行动指南…",
  generate_long_plan_part5: "5/5 项目准备…",
  merge_long_plan: "汇总报告…",
};

const LONG_PLAN_PROGRESS = {
  hydrate_long_plan: { pct: 5, label: "初始化表单…" },
  retrieve_long_plan_kb: { pct: 15, label: "检索知识库与联网…" },
  generate_long_plan_part1: { pct: 30, label: "1/5 分析目标院校与项目…" },
  generate_long_plan_part2: { pct: 45, label: "2/5 核心诊断与定位评级…" },
  generate_long_plan_part3: { pct: 60, label: "3/5 规划关键时间轴…" },
  generate_long_plan_part4: { pct: 75, label: "4/5 梳理核心行动指南…" },
  generate_long_plan_part5: { pct: 90, label: "5/5 项目准备建议…" },
  merge_long_plan: { pct: 100, label: "汇总报告…" },
};

async function runLongPlanReport() {
  const payload = collectLongPlanPayload();
  const missing = missingRequiredLongPlanFields(payload);
  if (missing.length) {
    const tip = `请先填写必填项：${missing.join("、")}`;
    if (longPlanErr) {
      longPlanErr.textContent = tip;
      longPlanErr.classList.remove("hidden");
    } else {
      window.alert(tip);
    }
    return;
  }

  lastLongPlanPayload = payload;
  lastLongPlanMarkdown = "";
  if (lastLongPlanHtmlUrl) {
    URL.revokeObjectURL(lastLongPlanHtmlUrl);
    lastLongPlanHtmlUrl = "";
  }
  lastDocs = [];
  lastLongPlanRefs = [];

  if (longPlanErr) {
    longPlanErr.textContent = "";
    longPlanErr.classList.add("hidden");
  }
  const triggerBtn = document.getElementById("btnReport");
  const htmlBtn = document.getElementById("btnReportHtml");
  const dlBtn = document.getElementById("btnDownloadHtml");
  if (triggerBtn) triggerBtn.disabled = true;
  if (htmlBtn) htmlBtn.disabled = true;
  if (dlBtn) dlBtn.disabled = true;

  // Show progress bar, hide placeholder and preview
  if (longPlanProgress) longPlanProgress.style.display = "block";
  if (progressBarFill) progressBarFill.style.width = "0%";
  if (progressStepLabel) progressStepLabel.textContent = "初始化…";
  if (longReportPlaceholder) longReportPlaceholder.classList.add("hidden");
  if (longReportPreview) {
    longReportPreview.classList.add("hidden");
    longReportPreview.innerHTML = "";
  }
  // Scroll to progress bar
  if (longPlanProgress) longPlanProgress.scrollIntoView({ behavior: "smooth", block: "nearest" });
  const t0 = performance.now();
  try {
    const res = await apiFetch("/api/long-chat/report/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(errText || res.statusText);
    }
    const reader = res.body?.getReader();
    if (!reader) throw new Error("浏览器不支持流式响应");
    const decoder = new TextDecoder();
    let buf = "";
    let lastMd = "";
    let lastReport = null;
    let streamErr = null;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop() ?? "";
      for (const line of lines) {
        const s = line.trim();
        if (!s) continue;
        let ev;
        try {
          ev = JSON.parse(s);
        } catch {
          continue;
        }
        if (ev.stream_error) streamErr = ev.stream_error;
        const nodeName = Object.keys(ev)[0];
        const patch = nodeName ? ev[nodeName] : null;
        if (LONG_PLAN_STREAM_LABELS[nodeName] && longReportPlaceholder) {
          longReportPlaceholder.textContent = LONG_PLAN_STREAM_LABELS[nodeName];
          longReportPlaceholder.classList.remove("hidden");
        }
        // Update progress bar
        if (LONG_PLAN_PROGRESS[nodeName]) {
          const step = LONG_PLAN_PROGRESS[nodeName];
          if (progressBarFill) progressBarFill.style.width = step.pct + "%";
          if (progressStepLabel) progressStepLabel.textContent = step.label;
        }
        if (nodeName === "merge_long_plan" && patch) {
          lastMd = patch.report_markdown || "";
          lastReport = patch.report ?? null;
          // Capture evidence for right panel
          if (patch.retrieved_docs && patch.retrieved_docs.length) {
            lastDocs = patch.retrieved_docs;
          }
          if (patch.references) {
            lastLongPlanRefs = patch.references;
          }
        }
      }
    }
    if (streamErr) throw new Error(streamErr);
    const latency_ms = Math.round(performance.now() - t0);
    if (!lastMd && !lastReport) {
      const res2 = await apiFetch("/api/long-chat/report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res2.json();
      if (!res2.ok) {
        const detail = data.detail || data;
        const msg =
          typeof detail === "object" && detail.errors
            ? detail.errors.join("；")
            : JSON.stringify(detail);
        throw new Error(msg || res2.statusText);
      }
      lastMd = data.report_markdown || "";
      lastReport = data.report;
      if (data.retrieved_docs && data.retrieved_docs.length) lastDocs = data.retrieved_docs;
      if (data.references) lastLongPlanRefs = data.references;
      if (longReportJson) {
        let txt = JSON.stringify(lastReport, null, 2);
        if (data.latency_ms != null) txt += `\n\n// latency_ms: ${data.latency_ms}`;
        if (data.error) txt += `\n\n// error: ${data.error}`;
        longReportJson.textContent = txt;
      }
    } else {
      if (longReportJson) {
        let txt = JSON.stringify(lastReport, null, 2);
        txt += `\n\n// latency_ms (client): ${latency_ms}`;
        longReportJson.textContent = txt;
      }
    }
    lastLongPlanMarkdown = typeof lastMd === "string" ? lastMd : "";
    lastLongPlanReport = lastReport && typeof lastReport === "object" ? lastReport : null;
    if (lastLongPlanMarkdown || lastReport) {
      await prepareLongPlanHtmlLink(lastLongPlanMarkdown, lastReport);
    }
    // Hide progress bar, then show report
    if (longPlanProgress) {
      if (progressBarFill) progressBarFill.style.width = "100%";
      if (progressStepLabel) progressStepLabel.textContent = "生成完成，正在渲染预览…";
      longPlanProgress.style.display = "none";
    }
    if (longReportPreview) {
      longReportPreview.innerHTML = lastLongPlanHtmlUrl
        ? `<iframe class="lp-preview-frame" title="规划报告预览" src="${lastLongPlanHtmlUrl}"></iframe>`
        : formatLongPlanMarkdown(lastLongPlanMarkdown || "");
      longReportPreview.classList.remove("hidden");
      longReportPreview.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
    if (longReportPlaceholder) longReportPlaceholder.classList.add("hidden");
    if (htmlBtn) htmlBtn.disabled = !lastLongPlanHtmlUrl;
    if (dlBtn) dlBtn.disabled = !(lastLongPlanHtmlUrl || lastLongPlanMarkdown || lastLongPlanReport);
  } catch (e) {
    if (longPlanProgress) longPlanProgress.style.display = "none";
    if (longPlanErr) {
      longPlanErr.textContent = String(e.message || e);
      longPlanErr.classList.remove("hidden");
    }
    if (longReportPlaceholder) {
      longReportPlaceholder.classList.remove("hidden");
      longReportPlaceholder.textContent = "生成失败，请检查必填项与后端配置。";
    }
    if (longReportJson) longReportJson.textContent = String(e);
  } finally {
    const b = document.getElementById("btnReport");
    if (b) b.disabled = false;
    const hb = document.getElementById("btnReportHtml");
    if (hb) hb.disabled = !lastLongPlanHtmlUrl;
    const db = document.getElementById("btnDownloadHtml");
    if (db) db.disabled = !(lastLongPlanHtmlUrl || lastLongPlanMarkdown || lastLongPlanReport);
  }
}

function longPlanHtmlFilename() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `ruc-baoyan-plan-${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}.html`;
}

async function downloadLongPlanHtmlReport() {
  if (!lastLongPlanMarkdown && !lastLongPlanReport && !lastLongPlanHtmlUrl) {
    window.alert("请先生成规划报告后再下载 HTML。");
    return;
  }
  const dlBtn = document.getElementById("btnDownloadHtml");
  if (dlBtn) dlBtn.disabled = true;
  try {
    const body = lastLongPlanReport && typeof lastLongPlanReport === "object"
      ? {
          report: lastLongPlanReport,
          report_markdown: lastLongPlanMarkdown || "",
          references: lastLongPlanRefs || [],
          download: true,
        }
      : { report_markdown: lastLongPlanMarkdown || "", download: true };
    const res = await apiFetch("/api/long-chat/report/html", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(errText || res.statusText);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = longPlanHtmlFilename();
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    if (longPlanErr) {
      longPlanErr.textContent = `HTML 下载失败：${e.message || e}`;
      longPlanErr.classList.remove("hidden");
    } else {
      window.alert(`HTML 下载失败：${e.message || e}`);
    }
  } finally {
    if (dlBtn) dlBtn.disabled = !(lastLongPlanHtmlUrl || lastLongPlanMarkdown || lastLongPlanReport);
  }
}

async function prepareLongPlanHtmlLink(markdown, report = null) {
  const body = report && typeof report === "object"
    ? { report, report_markdown: markdown || "", references: lastLongPlanRefs || [] }
    : { report_markdown: markdown || "" };
  const res = await apiFetch("/api/long-chat/report/html", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(errText || res.statusText);
  }
  const blob = await res.blob();
  if (lastLongPlanHtmlUrl) URL.revokeObjectURL(lastLongPlanHtmlUrl);
  lastLongPlanHtmlUrl = URL.createObjectURL(blob);
}

async function openLongPlanHtmlReport() {
  const mdCached =
    typeof lastLongPlanMarkdown === "string" ? lastLongPlanMarkdown.trim() : "";

  const payload = collectLongPlanPayload();
  const missing = missingRequiredLongPlanFields(payload);

  if (!mdCached && missing.length) {
    const tip = `请先填写必填项并生成报告后再打开 HTML 报告：${missing.join("、")}`;
    if (longPlanErr) {
      longPlanErr.textContent = tip;
      longPlanErr.classList.remove("hidden");
    } else {
      window.alert(tip);
    }
    return;
  }

  lastLongPlanPayload = payload;

  const htmlBtn = document.getElementById("btnReportHtml");
  const genBtn = document.getElementById("btnReport");
  if (htmlBtn) htmlBtn.disabled = true;
  if (genBtn) genBtn.disabled = true;
  if (longPlanErr) {
    longPlanErr.textContent = "";
    longPlanErr.classList.add("hidden");
  }
  try {
    if (!lastLongPlanHtmlUrl) {
      if (mdCached || lastLongPlanReport) await prepareLongPlanHtmlLink(mdCached, lastLongPlanReport);
      else {
        const res = await apiFetch("/api/long-chat/report/html", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!res.ok) {
          const errText = await res.text();
          throw new Error(errText || res.statusText);
        }
        const blob = await res.blob();
        lastLongPlanHtmlUrl = URL.createObjectURL(blob);
      }
    }
    window.open(lastLongPlanHtmlUrl, "_blank", "noopener,noreferrer");
  } catch (e) {
    if (longPlanErr) {
      longPlanErr.textContent = `HTML 报告生成失败：${e.message || e}`;
      longPlanErr.classList.remove("hidden");
    }
  } finally {
    if (htmlBtn) htmlBtn.disabled = !lastLongPlanHtmlUrl;
    const dlBtn = document.getElementById("btnDownloadHtml");
    if (dlBtn) dlBtn.disabled = !lastLongPlanHtmlUrl;
    if (genBtn) genBtn.disabled = false;
  }
}

(function wireLongPlanPanel() {
  const root = document.getElementById("viewLong");
  if (!root) return;
  /** 点击按钮标签文字时 target 多为 Text 节点，需归一到 Element 再 closest。 */
  function eventTargetElement(ev) {
    const n = ev.target;
    if (n instanceof Element) return n;
    const p = n?.parentElement;
    return p instanceof Element ? p : null;
  }
  root.addEventListener("click", (e) => {
    const start = eventTargetElement(e);
    if (!start) return;
    const btn = start.closest("#btnReport, #btnReportHtml, #btnDownloadHtml");
    if (!btn || !root.contains(btn)) return;
    e.preventDefault();
    if (btn.id === "btnReport") void runLongPlanReport();
    else if (btn.id === "btnReportHtml") void openLongPlanHtmlReport();
    else void downloadLongPlanHtmlReport();
  });
})();

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
      const res = await apiFetch("/api/kb/debug");
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
      const res = await apiFetch("/api/kb/xiaohongshu/verify", {
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
      const res = await apiFetch("/api/kb/official/verify", {
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
      const res = await apiFetch("/api/web-access/test", {
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
      let res = await apiFetch("/api/kb/debug/trace", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: q,
          enable_web_search: kbDebugWeb ? kbDebugWeb.checked : false,
          kb_scope: kbDebugScope,
        }),
      });
      if (res.status === 404) {
        res = await apiFetch("/api/kb/retrieve-preview", {
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

if (btnLogout) {
  btnLogout.addEventListener("click", async () => {
    try {
      await apiFetch("/api/auth/logout", { method: "POST" });
    } catch {
      /* ignore */
    }
    clearAuthSession();
    window.location.href = "/";
  });
}

if (btnSaveProfile) {
  btnSaveProfile.addEventListener("click", async () => {
    if (profileSaveMsg) {
      profileSaveMsg.classList.remove("ok");
      profileSaveMsg.classList.add("hidden");
    }
    try {
      await saveUserProfile();
    } catch (e) {
      if (profileSaveMsg) {
        profileSaveMsg.textContent = e.message || String(e);
        profileSaveMsg.classList.remove("hidden", "ok");
      }
    }
  });
}

if (btnApplyProfileToLong) {
  btnApplyProfileToLong.addEventListener("click", async () => {
    try {
      const profile = await loadUserProfile();
      applyProfileToLongPlanForm(profile);
      setActiveView("long");
      if (profileSaveMsg) {
        profileSaveMsg.textContent = "已同步到长程规划表单";
        profileSaveMsg.classList.remove("hidden");
        profileSaveMsg.classList.add("ok");
      }
    } catch (e) {
      if (profileSaveMsg) {
        profileSaveMsg.textContent = e.message || String(e);
        profileSaveMsg.classList.remove("hidden", "ok");
      }
    }
  });
}

ensureAuthenticated().then((ok) => {
  if (!ok) return;
  renderFaqChips();
  renderExamFaqChips();
  setActiveView("quick");
});

// Wire quick Q&A PDF download button
if (btnAnswerPdf) {
  btnAnswerPdf.addEventListener("click", downloadAnswerPdf);
}

// Evidence panel disclaimer
(function addEvidenceDisclaimer() {
  const panel = document.querySelector(".evidence-panel");
  if (!panel) return;
  const disc = document.createElement("div");
  disc.className = "evidence-disclaimer";
  disc.innerHTML =
    '注：带有网络溯源的内容提取自过往经验分享，仅供参考。最新招生要求请以人大陆续发布的官方文件为准。';
  panel.appendChild(disc);
})();
