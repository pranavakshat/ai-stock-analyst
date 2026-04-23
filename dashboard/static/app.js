/* ── app.js — AI Stock Analyst Dashboard ──────────────────────────────────── */

"use strict";

// ── State ─────────────────────────────────────────────────────────────────────
let MODELS     = {};   // {key: {display, color}}
let accuracyChart  = null;
let portfolioChart = null;

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

  if (tabId === "accuracy")  loadAccuracy();
  if (tabId === "portfolio") loadPortfolio();
  if (tabId === "history")   loadHistory();
}

// ── Today's Picks ─────────────────────────────────────────────────────────────

async function loadPicks(dateStr) {
  const grid = document.getElementById("picks-grid");
  grid.innerHTML = '<div class="loading">Loading picks…</div>';

  try {
    const data = await apiFetch(`/api/predictions?date=${dateStr}`);
    const preds = data.predictions || [];

    if (!preds.length) {
      grid.innerHTML = '<div class="loading">No picks found for this date.</div>';
      return;
    }

    // Group by model
    const byModel = {};
    preds.forEach(p => {
      if (!byModel[p.model_name]) byModel[p.model_name] = [];
      byModel[p.model_name].push(p);
    });

    grid.innerHTML = "";
    Object.entries(MODELS).forEach(([key, meta]) => {
      const picks = (byModel[key] || []).sort((a, b) => a.rank - b.rank);
      const card  = document.createElement("div");
      card.className = "model-card";

      const header = `<div class="model-card-header" style="background:${meta.color}">${meta.display}</div>`;

      let body = "";
      if (!picks.length) {
        body = `<div class="no-picks">No picks returned for this date.</div>`;
      } else {
        body = picks.map(p => `
          <div class="pick-row">
            <div class="pick-rank" style="color:${meta.color}">#${p.rank}</div>
            <div class="pick-body">
              <div>
                <span class="pick-ticker">${p.ticker}</span>
                <span class="badge badge-${p.confidence}">${p.confidence}</span>
              </div>
              <div class="pick-reasoning">${p.reasoning || ""}</div>
            </div>
          </div>
        `).join("");
      }

      card.innerHTML = header + body;
      grid.appendChild(card);
    });

    document.getElementById("last-updated").textContent = `Updated ${new Date().toLocaleTimeString()}`;
  } catch (err) {
    grid.innerHTML = `<div class="loading">Error loading picks: ${err.message}</div>`;
  }
}

// ── Accuracy ──────────────────────────────────────────────────────────────────

async function loadAccuracy() {
  try {
    const data    = await apiFetch("/api/accuracy");
    const summary = data.accuracy || [];

    // Build table
    const tbody = document.querySelector("#accuracy-table tbody");
    if (!summary.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="loading">No accuracy data yet — runs after first evening job.</td></tr>';
      return;
    }

    tbody.innerHTML = summary.map((row, i) => {
      const meta   = MODELS[row.model_name] || { display: row.model_name, color: "#6b7280" };
      const retCls = row.avg_return_pct >= 0 ? "positive" : "negative";
      return `
        <tr>
          <td>${i + 1}</td>
          <td><strong style="color:${meta.color}">${meta.display}</strong></td>
          <td>${row.total_picks}</td>
          <td>${row.correct_picks}</td>
          <td>
            <div class="accuracy-bar">
              <div class="bar-track">
                <div class="bar-fill" style="width:${row.accuracy_pct}%;background:${meta.color}"></div>
              </div>
              <span class="bar-label">${row.accuracy_pct}%</span>
            </div>
          </td>
          <td class="${retCls}">${fmtPct(row.avg_return_pct)}</td>
        </tr>
      `;
    }).join("");

    // Build accuracy-over-time chart
    const allDates  = new Set();
    const seriesMap = {};  // model → {date → accuracy_pct}

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
    console.error("Accuracy load error:", err);
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

        const chips = picks.sort((a, b) => a.rank - b.rank).map(p => `
          <div class="pick-chip">
            <span class="chip-ticker">#${p.rank} ${p.ticker}</span>
            <span class="badge badge-${p.confidence}">${p.confidence}</span>
          </div>
        `).join("");

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

async function init() {
  // Load model metadata
  try {
    const data = await apiFetch("/api/models");
    MODELS = data.models || {};
  } catch (err) {
    console.error("Could not load model metadata", err);
  }

  // Set date picker to today
  const picker = document.getElementById("date-picker");
  picker.value = isoToday();
  picker.addEventListener("change", () => loadPicks(picker.value));

  // Tab clicks
  document.querySelectorAll(".tab").forEach(btn => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  // Manual job buttons
  document.getElementById("btn-morning").addEventListener("click", () =>
    triggerJob("/api/run/morning", "Morning Job"));
  document.getElementById("btn-evening").addEventListener("click", () =>
    triggerJob("/api/run/evening", "Evening Job"));

  // History filter
  document.getElementById("history-model-filter").addEventListener("change", loadHistory);

  // Load initial tab
  loadPicks(isoToday());
}

document.addEventListener("DOMContentLoaded", init);
