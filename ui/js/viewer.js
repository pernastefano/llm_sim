/* ═══════════════════════════════════════════════════════════════════════
   viewer.js — Trace Viewer page logic
   Depends on: i18n.js (must be loaded first)
═══════════════════════════════════════════════════════════════════════ */

/* ── Utility helpers ─────────────────────────────────────────────────── */
function escHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/* ── JSON syntax highlighter ─────────────────────────────────────────── */
function renderJson(val, depth) {
  depth = depth || 0;
  const pad  = "  ".repeat(depth);
  const pad1 = "  ".repeat(depth + 1);

  if (val === null) return '<span class="j-null">null</span>';
  if (typeof val === "boolean") return `<span class="j-bool">${val}</span>`;
  if (typeof val === "number")  return `<span class="j-num">${val}</span>`;
  if (typeof val === "string")  return `<span class="j-str">"${escHtml(val)}"</span>`;

  if (Array.isArray(val)) {
    if (val.length === 0) return "[]";
    if (val.every(v => typeof v !== "object" || v === null) && val.length <= 8) {
      return "[" + val.map(v => renderJson(v, 0)).join(", ") + "]";
    }
    const items = val.map(v => pad1 + renderJson(v, depth + 1));
    return "[\n" + items.join(",\n") + "\n" + pad + "]";
  }

  if (typeof val === "object") {
    const keys = Object.keys(val);
    if (keys.length === 0) return "{}";
    const entries = keys.map(k =>
      pad1 + `<span class="j-key">"${escHtml(k)}"</span>: ` + renderJson(val[k], depth + 1)
    );
    return "{\n" + entries.join(",\n") + "\n" + pad + "}";
  }

  return escHtml(String(val));
}

/* ── Step-type metadata ──────────────────────────────────────────────── */
const STEP_META = {
  "input":               { icon: "📥", color: "#58a6ff" },
  "prompt_construction": { icon: "🔧", color: "#ffa657" },
  "tokenization":        { icon: "✂️",  color: "#d2a8ff" },
  "agent_reasoning":     { icon: "🤔", color: "#f2cc60" },
  "generation_start":    { icon: "▶️",  color: "#3fb950" },
  "final_answer":        { icon: "✅", color: "#3fb950" },
  _gen_step:             { icon: "⚡", color: "#bc8cff" },
};

function metaFor(name) {
  if (name.startsWith("generation_step_")) return STEP_META._gen_step;
  return STEP_META[name] || { icon: "📋", color: "#8b949e" };
}

/* ── Specialised renderers ───────────────────────────────────────────── */
function renderAgentReasoning(data) {
  let html = "";
  if (data.reasoning_steps && data.reasoning_steps.length) {
    html += `<strong style="color:var(--muted);font-size:12px">${escHtml(t("viewer.reasoning.title"))}</strong>`;
    html += "<ul class='reasoning-list'>";
    data.reasoning_steps.forEach(s => { html += `<li>${escHtml(s)}</li>`; });
    html += "</ul>";
  }
  const rest = Object.fromEntries(Object.entries(data).filter(([k]) => k !== "reasoning_steps"));
  if (Object.keys(rest).length) {
    html += "<div class='json-block' style='margin-top:10px'>" + renderJson(rest) + "</div>";
  }
  return html;
}

function renderGenerationStep(data) {
  const selected = data.selected_token;
  let html = `<div style="margin-bottom:8px;font-size:12px;color:var(--muted)">
    ${escHtml(t("viewer.step.context"))} <code style="color:var(--text)">${escHtml(data.context_preview)}</code><br/>
    ${escHtml(t("viewer.step.partial"))} <code style="color:var(--green)">${escHtml(data.partial_output)}</code>
  </div>`;

  if (data.candidates && data.candidates.length) {
    html += `<table class="prob-table">
      <thead><tr>
        <th>${escHtml(t("viewer.col.rank"))}</th>
        <th>${escHtml(t("viewer.col.token"))}</th>
        <th>${escHtml(t("viewer.col.score"))}</th>
        <th>${escHtml(t("viewer.col.probability"))}</th>
        <th class="prob-bar-cell">${escHtml(t("viewer.col.bar"))}</th>
      </tr></thead>
      <tbody>`;
    data.candidates.forEach((c, i) => {
      const isSelected = c.token === selected;
      const barPct = Math.round(c.probability * 100);
      html += `<tr class="${isSelected ? "selected" : ""}">
        <td>${i + 1}</td>
        <td><code>${escHtml(c.token)}</code>${isSelected ? " " + escHtml(t("viewer.selected")) : ""}</td>
        <td>${c.score}</td>
        <td>${(c.probability * 100).toFixed(2)}%</td>
        <td class="prob-bar-cell">
          <div class="prob-bar-track">
            <div class="prob-bar-fill ${isSelected ? "selected" : ""}" data-pct="${barPct}"></div>
          </div>
        </td>
      </tr>`;
    });
    html += "</tbody></table>";
  }
  return html;
}

/* ── Main renderer ───────────────────────────────────────────────────── */
function renderStep(step, index) {
  const meta    = metaFor(step.name);
  const details = document.createElement("details");
  details.className   = "step-card";
  details.dataset.name = step.name;

  const summary = document.createElement("summary");
  summary.innerHTML = `
    <span class="step-icon">${meta.icon}</span>
    <span class="step-index">${String(index).padStart(2, "0")}</span>
    <span class="step-name" style="color:${meta.color}">${escHtml(step.name)}</span>
    <span class="step-desc">${escHtml(step.description)}</span>
  `;

  const body = document.createElement("div");
  body.className = "step-body";

  let inner = "";
  if (step.name === "agent_reasoning") {
    inner = renderAgentReasoning(step.data);
  } else if (step.name.startsWith("generation_step_")) {
    inner = renderGenerationStep(step.data);
  } else {
    inner = "<div class='json-block'>" + renderJson(step.data) + "</div>";
  }
  body.innerHTML = inner;
  body.querySelectorAll(".prob-bar-fill[data-pct]").forEach(el => {
    el.style.width = el.dataset.pct + "%";
  });

  details.appendChild(summary);
  details.appendChild(body);
  return details;
}

function renderSummary(steps) {
  const genSteps = steps.filter(s => s.name.startsWith("generation_step_")).length;
  const query    = (steps.find(s => s.name === "input") || {}).data?.user_query || "—";
  const toolUsed = (steps.find(s => s.name === "agent_reasoning") || {}).data?.tool_used || "none";
  document.getElementById("summary").innerHTML = `
    <div class="stat">
      <span class="stat-label">${escHtml(t("viewer.stat.totalsteps"))}</span>
      <span class="stat-value">${steps.length}</span>
    </div>
    <div class="stat">
      <span class="stat-label">${escHtml(t("viewer.stat.gensteps"))}</span>
      <span class="stat-value">${genSteps}</span>
    </div>
    <div class="stat">
      <span class="stat-label">${escHtml(t("viewer.stat.toolused"))}</span>
      <span class="stat-value">${escHtml(String(toolUsed))}</span>
    </div>
    <div class="stat">
      <span class="stat-label">${escHtml(t("viewer.stat.query"))}</span>
      <span class="stat-value" style="font-size:13px;max-width:400px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escHtml(query)}</span>
    </div>
  `;
  document.getElementById("summary").style.display = "flex";
}

let _allCards = [];

function renderTrace(traceData) {
  const steps     = traceData.steps || [];
  const container = document.getElementById("trace-container");
  container.innerHTML = "";
  _allCards = [];

  renderSummary(steps);

  if (!steps.length) {
    container.innerHTML = `<p style="color:var(--muted)">${escHtml(t("viewer.err.notrace"))}</p>`;
    return;
  }

  steps.forEach((step, i) => {
    const card = renderStep(step, i);
    _allCards.push(card);
    container.appendChild(card);
  });

  document.getElementById("filter-bar").classList.add("visible");
  document.getElementById("expand-all-btn").style.display = "";
}

/* ── Loading logic ───────────────────────────────────────────────────── */
function loadTrace(json) {
  try {
    const data = typeof json === "string" ? JSON.parse(json) : json;
    renderTrace(data);
  } catch (e) {
    showViewerError(t("viewer.err.parsefail") + e.message);
  }
}

function showViewerError(msg) {
  document.getElementById("trace-container").innerHTML =
    `<div class="error-banner">⚠️ ${escHtml(msg)}</div>`;
}

/* ── Re-render summary if language changes while a trace is loaded ───── */
document.addEventListener("langchange", () => {
  if (_allCards.length) {
    // Re-render reasoning titles and generation step labels inline
    document.querySelectorAll(".step-body").forEach(body => {
      const card = body.closest(".step-card");
      if (!card) return;
      const name = card.dataset.name;
      const stepIndex = _allCards.indexOf(card);
      if (stepIndex === -1) return;
      // Only re-render typed steps with i18n strings
      if (name === "agent_reasoning" || name.startsWith("generation_step_")) {
        const steps = (window._currentTrace || {}).steps || [];
        const step  = steps[stepIndex];
        if (step) {
          body.innerHTML = name === "agent_reasoning"
            ? renderAgentReasoning(step.data)
            : renderGenerationStep(step.data);
          body.querySelectorAll(".prob-bar-fill[data-pct]").forEach(el => {
            el.style.width = el.dataset.pct + "%";
          });
        }
      }
    });
    // Re-render summary stats labels
    if (window._currentTrace) renderSummary(window._currentTrace.steps || []);
  }
});

/* ── Event listeners ─────────────────────────────────────────────────── */

// Auto-load button
document.getElementById("auto-load-btn").addEventListener("click", function () {
  fetch("../llm_trace.json")
    .then(r => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    })
    .then(data => {
      window._currentTrace = data;
      renderTrace(data);
    })
    .catch(err => {
      if (location.protocol === "file:") {
        showViewerError(t("viewer.err.autoload.file"));
      } else {
        showViewerError(
          t("viewer.err.autoload.net") + err.message + t("viewer.err.autoload.hint")
        );
      }
    });
});

// Expand-all toggle
let _expanded = false;
document.getElementById("expand-all-btn").addEventListener("click", function () {
  _expanded = !_expanded;
  _allCards.forEach(c => { c.open = _expanded; });
  this.textContent = _expanded ? t("viewer.btn.collapseall") : t("viewer.btn.expandall");
  // Keep data-i18n in sync so applyTranslations won't override
  this.dataset.i18n = _expanded ? "viewer.btn.collapseall" : "viewer.btn.expandall";
});

// Filter input
document.getElementById("filter-input").addEventListener("input", applyFilter);
document.querySelectorAll(".filter-tag").forEach(btn => {
  btn.addEventListener("click", function () {
    document.querySelectorAll(".filter-tag").forEach(b => b.classList.remove("active"));
    this.classList.add("active");
    document.getElementById("filter-input").value = this.dataset.filter;
    applyFilter();
  });
});

function applyFilter() {
  const q = document.getElementById("filter-input").value.toLowerCase();
  _allCards.forEach(card => {
    card.style.display = card.dataset.name.includes(q) ? "" : "none";
  });
}

// Auto-load when opened with ?autoload in the URL
if (new URLSearchParams(window.location.search).has("autoload")) {
  document.getElementById("auto-load-btn").click();
}
