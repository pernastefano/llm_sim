/* ═══════════════════════════════════════════════════════════════════════
   index.js — Main query page logic
   Depends on: i18n.js (must be loaded first)
═══════════════════════════════════════════════════════════════════════ */

/* ── Pipeline stage definitions ─────────────────────────────────────── */
const STAGE_KEYS = [
  { icon: "📥", key: "index.stage.0" },
  { icon: "🔧", key: "index.stage.1" },
  { icon: "✂️",  key: "index.stage.2" },
  { icon: "🤔", key: "index.stage.3" },
  { icon: "⚡", key: "index.stage.4" },
  { icon: "✅", key: "index.stage.5" },
];

/* ── Helpers ─────────────────────────────────────────────────────────── */
function esc(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function show(...ids) {
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.remove("hidden");
  });
}

function hide(...ids) {
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.add("hidden");
  });
}

function probCls(p) {
  if (p >= 0.8) return "tok-high";
  if (p >= 0.5) return "tok-mid";
  return "tok-low";
}

/* ── Pipeline stage animation ────────────────────────────────────────── */
function buildStages() {
  document.getElementById("stage-list").innerHTML = STAGE_KEYS.map((s, i) =>
    `<div id="st${i}" class="stage-item pending">
       <span class="stage-icon">${s.icon}</span>
       <span class="stage-name">${esc(t(s.key))}</span>
       <span class="stage-status">—</span>
     </div>`
  ).join("");
}

function markStage(i, cls, status) {
  const el = document.getElementById(`st${i}`);
  if (!el) return;
  el.className = `stage-item ${cls}`;
  el.querySelector(".stage-status").textContent = status;
}

function runStageAnimation() {
  let i = 0;
  const interval = setInterval(() => {
    if (i > 0) markStage(i - 1, "done", "✓");
    if (i < STAGE_KEYS.length) {
      markStage(i, "active", "⚡");
      i++;
    } else {
      clearInterval(interval);
    }
  }, 200);
  return () => {
    clearInterval(interval);
    STAGE_KEYS.forEach((_, j) => markStage(j, "done", "✓"));
  };
}

/* ── Token animation ─────────────────────────────────────────────────── */
function animateTokens(tokens, probs) {
  const container = document.getElementById("token-display");
  container.innerHTML = "";

  if (!tokens.length) {
    container.textContent = "(no tokens generated)";
    return Promise.resolve();
  }

  const delay = Math.min(130, 1500 / tokens.length);

  return new Promise(resolve => {
    tokens.forEach((tok, i) => {
      setTimeout(() => {
        const pct = Math.round(probs[i] * 100);
        const span = document.createElement("span");
        span.className = `tok ${probCls(probs[i])}`;
        span.title = `"${tok}"  ·  probability: ${(probs[i] * 100).toFixed(1)}%`;
        span.innerHTML = `${esc(tok)}<sup>${pct}%</sup>`;
        span.style.cssText = "opacity:0;transform:translateY(5px);transition:opacity 0.15s,transform 0.15s";
        container.appendChild(span);
        requestAnimationFrame(() => requestAnimationFrame(() => {
          span.style.opacity = "1";
          span.style.transform = "translateY(0)";
        }));
        if (i === tokens.length - 1) setTimeout(resolve, 350);
      }, i * delay);
    });
  });
}

/* ── Main flow ───────────────────────────────────────────────────────── */
async function runQuery(query) {
  hide("query-section", "answer-section", "error-section");
  show("loading-section");
  document.getElementById("loading-label").textContent = t("index.loading.label");
  buildStages();
  const completeStages = runStageAnimation();

  try {
    const resp = await fetch("/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
      signal: AbortSignal.timeout(30_000),
    });

    completeStages();
    const data = await resp.json();

    if (!resp.ok) {
      showError(data.error || t("index.err.server") + resp.status);
      return;
    }

    await showAnswer(query, data);

  } catch (err) {
    completeStages();
    if (err.name === "TimeoutError") {
      showError(t("index.err.timeout"));
    } else {
      showError(t("index.err.network") + err.message);
    }
  }
}

async function showAnswer(query, data) {
  hide("loading-section");
  document.getElementById("query-echo-text").textContent = query;

  if (data.tool_used) {
    const isCalc = data.tool_used === "calculator";
    const badgeCls = isCalc ? "badge-calc" : "badge-search";
    const icon     = isCalc ? "🧮" : "🔍";
    const badge    = document.getElementById("tool-badge");
    badge.className = `tool-badge ${badgeCls}`;
    badge.innerHTML = `${icon} ${esc(data.tool_used)}`;
    document.getElementById("tool-output").textContent = data.tool_output ?? "";
    show("tool-section");
  } else {
    hide("tool-section");
  }

  document.getElementById("stat-steps").textContent  = data.total_steps;
  document.getElementById("stat-tokens").textContent = data.tokens.length;

  hide("trace-btn");
  show("answer-section");
  await animateTokens(data.tokens, data.token_probs);
  show("trace-btn");
}

function showError(msg) {
  hide("loading-section");
  document.getElementById("error-box").textContent = msg;
  show("error-section");
}

/* ── Re-build stages when language changes ───────────────────────────── */
document.addEventListener("langchange", () => {
  // Re-apply loading label if visible
  const lbl = document.getElementById("loading-label");
  if (lbl) lbl.textContent = t("index.loading.label");
});

/* ── Event listeners ─────────────────────────────────────────────────── */

// Character counter
document.getElementById("query-input").addEventListener("input", function () {
  const n = this.value.length;
  const counter = document.getElementById("char-counter");
  counter.textContent = `${n} / 500`;
  counter.className = "char-counter" + (n > 440 ? " warn" : "");
});

// Submit on button click
document.getElementById("submit-btn").addEventListener("click", () => {
  const q = document.getElementById("query-input").value.trim();
  if (!q) { document.getElementById("query-input").focus(); return; }
  runQuery(q);
});

// Submit on Ctrl/Cmd + Enter
document.getElementById("query-input").addEventListener("keydown", e => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
    document.getElementById("submit-btn").click();
  }
});

// Example chips fill the textarea
document.querySelectorAll(".chip").forEach(chip => {
  chip.addEventListener("click", () => {
    document.getElementById("query-input").value = chip.dataset.query;
    document.getElementById("query-input").dispatchEvent(new Event("input"));
    document.getElementById("query-input").focus();
  });
});

// "New question" button
document.getElementById("new-query-btn").addEventListener("click", () => {
  hide("answer-section", "error-section");
  show("query-section");
  document.getElementById("query-input").focus();
});

// "Try again" button
document.getElementById("retry-btn").addEventListener("click", () => {
  hide("error-section");
  show("query-section");
  document.getElementById("query-input").focus();
});
