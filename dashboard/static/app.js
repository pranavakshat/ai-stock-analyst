/* ── app.js — AI Stock Analyst Dashboard ──────────────────────────────────── */

"use strict";

// ── State ─────────────────────────────────────────────────────────────────────
let MODELS          = {};   // {key: {display, color}}
let accuracyChart   = null;
let portfolioChart  = null;
let currentSession  = "day"; // "day" or "overnight"

// ── Helpers ───────────────────────────────────────────────────────────────────

async function apiFetch(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
  return res.json();
}

function isoToday() {
  return new Date().toISOString().slice(0, 10);
}

function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso + "T12:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function fmtMoney(v) {
  return "$" + Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtPct(v) {
  const n = parseFloat(v);
  return (n >= 0 ? "+" : "") + n.toFixed(2) + "%";
}

function showToast(msg, duration = 3000) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), duration);
}

// ── Tab routing ───────────────────────────────────────────────────────────────

function switchTab(tabId) {
  document.querySelectorAll(".tab").forEach(t =>
    t.classList.toggle("active", t.dataset.tab === tabId));
  document.querySelectorAll(".tab-content").forEach(s =>
    s.classList.toggle("active", s.id === `tab-${tabId}`));

  if (tabId === "accuracy")  loadLeaderboards(currentPeriod);
  if (tabId === "portfolio") loadPortfolio();
  if (tabId === "history")   loadHistory();
}

// ── Model avatars ─────────────────────────────────────────────────────────────

const MODEL_AVATARS = { claude:"🤖", chatgpt:"💬", grok:"⚡", gemini:"✨" };

// ── Today's Picks ─────────────────────────────────────────────────────────────

async function loadPicks(dateStr, session) {
  if (session === undefined) session = currentSession;
  const snapshotEl = document.getElementById("snapshot-grid");
  const detailEl   = document.getElementById("picks-grid");
  snapshotEl.innerHTML = '<div class="loading">Loading…</div>';
  detailEl.innerHTML   = '<div class="loading">Loading picks…</div>';

  // Update section header label
  const label = document.getElementById("picks-date-label");
  if (label) {
    const sessionLabel = session === "overnight" ? "🌙 Overnight Holds" : "☀️ Day Session Picks";
    label.textContent = `${sessionLabel}`;
  }

  try {
    const data  = await apiFetch(`/api/predictions?date=${dateStr}&session=${session}`);
    const preds = data.predictions || [];

    if (!preds.length) {
      snapshotEl.innerHTML = '<div class="loading">No picks found for this date.</div>';
      detailEl.innerHTML   = "";
      return;
    }

    // Group by model
    const byModel = {};
    preds.forEach(p => {
      if (!byModel[p.model_name]) byModel[p.model_name] = [];
      byModel[p.model_name].push(p);
    });

    // ── Snapshot grid ──────────────────────────────────────────────────────
    snapshotEl.innerHTML = "";
    Object.entries(MODELS).forEach(([key, meta]) => {
      const picks  = (byModel[key] || []).sort((a, b) => a.rank - b.rank);
      const avatar = MODEL_AVATARS[key] || "🤖";
      const card   = document.createElement("div");
      card.className = "snap-card";

      const header = `
        <div class="snap-card-header" style="background:${meta.color}">
          <span class="snap-avatar">${avatar}</span>
          <span class="snap-model-name">${meta.display}</span>
        </div>`;

      let rows = "";
      if (!picks.length) {
        rows = `<div class="snap-empty">No picks</div>`;
      } else {
        rows = picks.map(p => {
          const dir   = (p.direction || "LONG").toUpperCase();
          const isLong = dir === "LONG";
          const conf  = p.confidence || "Medium";
          const alloc = p.allocation_pct != null ? Number(p.allocation_pct).toFixed(0) : "20";
          return `
          <div class="snap-row">
            <span class="snap-arrow ${isLong ? "arrow-up" : "arrow-down"}">${isLong ? "▲" : "▼"}</span>
            <span class="snap-ticker">${p.ticker}</span>
            <span class="snap-badges">
              <span class="badge badge-${conf}">${conf}</span>
              <span class="snap-alloc">${alloc}%</span>
            </span>
          </div>`;
        }).join("");
      }

      card.innerHTML = header + `<div class="snap-body">${rows}</div>`;
      snapshotEl.appendChild(card);
    });

    // ── Detail cards ───────────────────────────────────────────────────────
    detailEl.innerHTML = "";
    Object.entries(MODELS).forEach(([key, meta]) => {
      const picks = (byModel[key] || []).sort((a, b) => a.rank - b.rank);
      const card  = document.createElement("div");
      card.className = "model-card";

      const header = `<div class="model-card-header" style="background:${meta.color}">${MODEL_AVATARS[key] || ""} ${meta.display}</div>`;

      let body = "";
      if (!picks.length) {
        body = `<div class="no-picks">No picks returned for this date.</div>`;
      } else {
        body = picks.map(p => {
          const dir    = (p.direction || "LONG").toUpperCase();
          const isLong = dir === "LONG";
          const dirBg  = isLong ? "#dcfce7" : "#fee2e2";
          const dirFg  = isLong ? "#166534" : "#991b1b";
          const dirLbl = isLong ? "▲ LONG" : "▼ SHORT";
          const alloc  = p.allocation_pct != null ? Number(p.allocation_pct).toFixed(0) + "%" : "20%";
          return `
          <div class="pick-row">
            <div class="pick-rank" style="color:${meta.color}">#${p.rank}</div>
            <div class="pick-body">
              <div>
                <span class="pick-ticker">${p.ticker}</span>
                <span style="background:${dirBg};color:${dirFg};font-size:11px;font-weight:700;
                             padding:2px 8px;border-radius:999px;display:inline-block;margin-left:4px;">${dirLbl}</span>
                <span style="background:#ede9fe;color:#5b21b6;font-size:11px;font-weight:700;
                             padding:2px 8px;border-radius:999px;display:inline-block;margin-left:4px;">${alloc}</span>
                <span class="badge badge-${p.confidence}" style="margin-left:4px;">${p.confidence}</span>
              </div>
              <div class="pick-reasoning">${p.reasoning || ""}</div>
            </div>
          </div>`;
        }).join("");
      }

      card.innerHTML = header + body;
      detailEl.appendChild(card);
    });

    document.getElementById("last-updated").textContent = `Updated ${new Date().toLocaleTimeString()}`;
  } catch (err) {
    snapshotEl.innerHTML = `<div class="loading">Error: ${err.message}</div>`;
    detailEl.innerHTML   = "";
  }
}

// ── Leaderboards ─────────────────────────────────────────────────────────────

let currentPeriod = "all";

async function loadLeaderboards(period = "all") {
  currentPeriod = period;

  // Update active pill
  document.querySelectorAll(".period-btn").forEach(btn =>
    btn.classList.toggle("active", btn.dataset.period === period));

  try {
    const data = await apiFetch(`/api/leaderboard?period=${period}`);

    // ── P&L table ─────────────────────────────────────────────────────────
    const pnlTbody = document.querySelector("#pnl-table tbody");
    const pnlRows  = data.pnl || [];

    if (!pnlRows.length) {
      pnlTbody.innerHTML = '<tr><td colspan="5" class="loading">No portfolio data yet.</td></tr>';
    } else {
      pnlTbody.innerHTML = pnlRows.map((row, i) => {
        const meta    = MODELS[row.model_name] || { display: row.model_name, color: "#6b7280" };
        const gainCls = row.period_gain >= 0 ? "positive" : "negative";
        const retCls  = row.period_gain_pct >= 0 ? "positive" : "negative";
        return `
          <tr>
            <td><strong>${i + 1}</strong></td>
            <td><strong style="color:${meta.color}">${meta.display}</strong></td>
            <td>${fmtMoney(row.current_value)}</td>
            <td class="${gainCls}">${row.period_gain >= 0 ? "+" : ""}${fmtMoney(row.period_gain)}</td>
            <td class="${retCls}">${row.period_gain_pct >= 0 ? "+" : ""}${row.period_gain_pct.toFixed(2)}%</td>
          </tr>
        `;
      }).join("");
    }

    // ── Accuracy table ────────────────────────────────────────────────────
    const accTbody = document.querySelector("#accuracy-table tbody");
    const accRows  = data.accuracy || [];

    if (!accRows.length) {
      accTbody.innerHTML = '<tr><td colspan="5" class="loading">No accuracy data yet — runs after first evening job.</td></tr>';
    } else {
      accTbody.innerHTML = accRows.map((row, i) => {
        const meta = MODELS[row.model_name] || { display: row.model_name, color: "#6b7280" };
        return `
          <tr>
            <td><strong>${i + 1}</strong></td>
            <td><strong style="color:${meta.color}">${meta.display}</strong></td>
            <td><strong>${row.correct_picks}</strong></td>
            <td>${row.total_picks}</td>
            <td>
              <div class="accuracy-bar">
                <div class="bar-track">
                  <div class="bar-fill" style="width:${row.accuracy_pct}%;background:${meta.color}"></div>
                </div>
                <span class="bar-label">${row.accuracy_pct}%</span>
              </div>
            </td>
          </tr>
        `;
      }).join("");
    }

  } catch (err) {
    console.error("Leaderboard load error:", err);
  }

  // ── Accuracy over time chart (always all-time) ─────────────────────────
  try {
    const allDates  = new Set();
    const seriesMap = {};

    for (const [key] of Object.entries(MODELS)) {
      try {
        const r = await apiFetch(`/api/accuracy/${key}`);
        seriesMap[key] = {};
        (r.history || []).forEach(h => {
          seriesMap[key][h.date] = h.daily_accuracy_pct;
          allDates.add(h.date);
        });
      } catch (_) {}
    }

    const labels   = Array.from(allDates).sort();
    const datasets = Object.entries(MODELS).map(([key, meta]) => ({
      label:           meta.display,
      data:            labels.map(d => seriesMap[key]?.[d] ?? null),
      borderColor:     meta.color,
      backgroundColor: meta.color + "22",
      tension:         0.3,
      spanGaps:        true,
    }));

    const ctx = document.getElementById("accuracy-chart").getContext("2d");
    if (accuracyChart) accuracyChart.destroy();
    accuracyChart = new Chart(ctx, {
      type: "line",
      data: { labels: labels.map(fmtDate), datasets },
      options: {
        responsive: true,
        plugins: { legend: { position: "top" } },
        scales: {
          y: { title: { display: true, text: "Daily Accuracy %" }, min: 0, max: 100 },
        },
      },
    });
  } catch (err) {
    console.error("Chart load error:", err);
  }
}

// ── Portfolio ─────────────────────────────────────────────────────────────────

async function loadPortfolio() {
  try {
    const data   = await apiFetch("/api/portfolio");
    const latest = data.portfolio || [];

    const cardsEl = document.getElementById("portfolio-summary");

    if (!latest.length) {
      cardsEl.innerHTML = '<div class="loading">No portfolio data yet — runs after first evening job.</div>';
    } else {
      const byModel = {};
      latest.forEach(r => { byModel[r.model_name] = r; });

      cardsEl.innerHTML = Object.entries(MODELS).map(([key, meta]) => {
        const row      = byModel[key];
        const value    = row ? row.portfolio_value : 10000;
        const gainLoss = row ? row.portfolio_value - 10000 : 0;
        const cls      = gainLoss >= 0 ? "positive" : "negative";

        return `
          <div class="portfolio-card">
            <div class="model-label" style="color:${meta.color}">${meta.display}</div>
            <div class="value">${fmtMoney(value)}</div>
            <div class="change ${cls}">${fmtPct(gainLoss / 100)} &bull; ${fmtMoney(gainLoss)}</div>
          </div>
        `;
      }).join("");
    }

    // Portfolio growth chart — all models over time
    const allDates  = new Set();
    const seriesMap = {};

    for (const [key] of Object.entries(MODELS)) {
      try {
        const r = await apiFetch(`/api/portfolio/${key}`);
        seriesMap[key] = {};
        (r.history || []).forEach(h => {
          seriesMap[key][h.date] = h.portfolio_value;
          allDates.add(h.date);
        });
      } catch (_) {}
    }

    const labels   = Array.from(allDates).sort();
    const datasets = Object.entries(MODELS).map(([key, meta]) => ({
      label:           meta.display,
      data:            labels.map(d => seriesMap[key]?.[d] ?? null),
      borderColor:     meta.color,
      backgroundColor: meta.color + "22",
      tension:         0.3,
      spanGaps:        true,
      fill:            false,
    }));

    const ctx = document.getElementById("portfolio-chart").getContext("2d");
    if (portfolioChart) portfolioChart.destroy();
    portfolioChart = new Chart(ctx, {
      type: "line",
      data: { labels: labels.map(fmtDate), datasets },
      options: {
        responsive: true,
        plugins: { legend: { position: "top" } },
        scales: {
          y: {
            title: { display: true, text: "Portfolio Value ($)" },
            ticks: { callback: v => "$" + v.toLocaleString() },
          },
        },
      },
    });
  } catch (err) {
    console.error("Portfolio load error:", err);
  }
}

// ── History ───────────────────────────────────────────────────────────────────

async function loadHistory() {
  const listEl   = document.getElementById("history-list");
  const filterEl = document.getElementById("history-model-filter");

  listEl.innerHTML = '<div class="loading">Loading…</div>';

  try {
    const datesData = await apiFetch("/api/predictions/dates");
    const dates     = datesData.dates || [];

    if (!dates.length) {
      listEl.innerHTML = '<div class="loading">No historical data yet.</div>';
      return;
    }

    // Populate model filter
    const currentFilter = filterEl.value;
    if (filterEl.options.length <= 1) {
      Object.entries(MODELS).forEach(([key, meta]) => {
        const opt = document.createElement("option");
        opt.value = key; opt.textContent = meta.display;
        filterEl.appendChild(opt);
      });
    }

    // Fetch predictions for all dates (limit to last 30)
    const recentDates = dates.slice(0, 30);
    listEl.innerHTML = "";

    for (const d of recentDates) {
      const data  = await apiFetch(`/api/predictions?date=${d}`);
      const preds = data.predictions || [];

      const filtered = filterEl.value
        ? preds.filter(p => p.model_name === filterEl.value)
        : preds;

      if (!filtered.length) continue;

      // Group by model for this date
      const byModel = {};
      filtered.forEach(p => {
        if (!byModel[p.model_name]) byModel[p.model_name] = [];
        byModel[p.model_name].push(p);
      });

      Object.entries(byModel).forEach(([model, picks]) => {
        const meta = MODELS[model] || { display: model, color: "#6b7280" };

        const card = document.createElement("div");
        card.className = "history-card";

        const header = `
          <div class="history-card-header">
            <strong style="color:${meta.color}">${meta.display}</strong>
            <span>${fmtDate(d)}</span>
          </div>
        `;

        const chips = picks.sort((a, b) => a.rank - b.rank).map(p => {
          const dir    = (p.direction || "LONG").toUpperCase();
          const dirBg  = dir === "LONG" ? "#dcfce7" : "#fee2e2";
          const dirFg  = dir === "LONG" ? "#166534" : "#991b1b";
          const dirLbl = dir === "LONG" ? "▲" : "▼";
          return `
          <div class="pick-chip">
            <span class="chip-ticker">#${p.rank} ${p.ticker}</span>
            <span style="background:${dirBg};color:${dirFg};font-size:10px;
                         font-weight:700;padding:1px 6px;border-radius:999px;">${dirLbl} ${dir}</span>
            <span class="badge badge-${p.confidence}">${p.confidence}</span>
          </div>
          `;
        }).join("");

        card.innerHTML = header + `<div class="history-picks">${chips}</div>`;
        listEl.appendChild(card);
      });
    }
  } catch (err) {
    listEl.innerHTML = `<div class="loading">Error: ${err.message}</div>`;
  }
}

// ── Manual job triggers ───────────────────────────────────────────────────────

async function triggerJob(endpoint, label) {
  showToast(`Starting ${label}…`);
  try {
    await fetch(endpoint, { method: "POST" });
    showToast(`${label} started! Check server logs.`, 4000);
  } catch (err) {
    showToast(`Error: ${err.message}`, 5000);
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────

// ── Dark mode ─────────────────────────────────────────────────────────────────

function initDarkMode() {
  const btn  = document.getElementById("btn-dark-mode");
  const body = document.body;
  const saved = localStorage.getItem("theme");
  if (saved === "dark" || (!saved && window.matchMedia("(prefers-color-scheme: dark)").matches)) {
    body.setAttribute("data-theme", "dark");
    btn.textContent = "☀️";
  }
  btn.addEventListener("click", () => {
    const isDark = body.getAttribute("data-theme") === "dark";
    body.setAttribute("data-theme", isDark ? "light" : "dark");
    btn.textContent = isDark ? "🌙" : "☀️";
    localStorage.setItem("theme", isDark ? "light" : "dark");
  });
}

async function init() {
  initDarkMode();

  // Load model metadata
  try {
    const data = await apiFetch("/api/models");
    MODELS = data.models || {};
  } catch (err) {
    console.error("Could not load model metadata", err);
  }

  // Session toggle buttons
  document.querySelectorAll(".session-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      currentSession = btn.dataset.session;
      document.querySelectorAll(".session-btn").forEach(b =>
        b.classList.toggle("active", b.dataset.session === currentSession));
      loadPicks(document.getElementById("date-picker").value, currentSession);
    });
  });

  // Set date picker to today
  const picker = document.getElementById("date-picker");
  picker.value = isoToday();
  picker.addEventListener("change", () => loadPicks(picker.value, currentSession));

  // Set evening date picker to yesterday by default (most common use case)
  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  document.getElementById("evening-date").value = yesterday.toISOString().slice(0, 10);

  // Tab clicks
  document.querySelectorAll(".tab").forEach(btn => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  // Manual job buttons
  document.getElementById("btn-morning").addEventListener("click", () =>
    triggerJob("/api/run/morning", "Morning Job"));
  document.getElementById("btn-evening").addEventListener("click", () => {
    const d = document.getElementById("evening-date").value || isoToday();
    triggerJob(`/api/run/evening?date=${d}`, `Evening Job (${d})`);
  });

  // Period filter buttons (leaderboard tab)
  document.querySelectorAll(".period-btn").forEach(btn =>
    btn.addEventListener("click", () => loadLeaderboards(btn.dataset.period)));

  // History filter
  document.getElementById("history-model-filter").addEventListener("change", loadHistory);

  // Load initial tab
  loadPicks(isoToday(), currentSession);
}

document.addEventListener("DOMContentLoaded", init);
