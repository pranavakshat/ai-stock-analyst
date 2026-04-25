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

function sessionLabel(date, session) {
  const d = new Date(date + "T12:00:00");
  const base = d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  return base + (session === "day" ? " M" : " O");
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

  // ── Accuracy over time chart (bar + avg line, toggle cumulative/rolling) ──
  try {
    const allDates  = new Set();
    const seriesMap = {};   // key → { label → accuracy_pct }
    const rawOrder  = [];   // chronological labels (excluding Start)

    for (const [key] of Object.entries(MODELS)) {
      try {
        const r = await apiFetch(`/api/accuracy/${key}`);
        seriesMap[key] = {};
        (r.history || []).forEach(h => {
          const lbl = sessionLabel(h.date, h.session);
          seriesMap[key][lbl] = h.daily_accuracy_pct;
          allDates.add(lbl);
        });
      } catch (_) {}
    }

    const sortedLabels = Array.from(allDates).sort();
    sortedLabels.forEach(l => { if (!rawOrder.includes(l)) rawOrder.push(l); });

    // Avg line helpers
    function cumulativeAvg(key) {
      let correct = 0, total = 0;
      return rawOrder.map(lbl => {
        const pct = seriesMap[key]?.[lbl];
        if (pct == null) return null;
        correct += pct / 100 * 5;
        total   += 5;
        return Math.round(correct / total * 100);
      });
    }
    function rollingAvg(key, n = 5) {
      const vals = rawOrder.map(lbl => seriesMap[key]?.[lbl] ?? null);
      return vals.map((_, i) => {
        const slice = vals.slice(Math.max(0, i - n + 1), i + 1).filter(v => v != null);
        if (!slice.length) return null;
        return Math.round(slice.reduce((a, b) => a + b, 0) / slice.length);
      });
    }

    // Build datasets: bar (daily) + line (avg) per model
    function buildDatasets(mode) {
      const out = [];
      Object.entries(MODELS).forEach(([key, meta]) => {
        // bar — daily session accuracy
        out.push({
          type:            "bar",
          label:           meta.display,
          data:            rawOrder.map(lbl => seriesMap[key]?.[lbl] ?? null),
          backgroundColor: meta.color + "55",
          borderColor:     meta.color,
          borderWidth:     1,
          borderRadius:    3,
          order:           2,
          spanGaps:        false,
        });
        // line — avg
        out.push({
          type:            "line",
          label:           meta.display + " avg",
          data:            mode === "cumulative" ? cumulativeAvg(key) : rollingAvg(key),
          borderColor:     meta.color,
          backgroundColor: "transparent",
          borderWidth:     2.5,
          borderDash:      [5, 3],
          pointRadius:     3,
          tension:         0.3,
          spanGaps:        true,
          order:           1,
        });
      });
      return out;
    }

    const ctx = document.getElementById("accuracy-chart").getContext("2d");
    if (accuracyChart) accuracyChart.destroy();
    accuracyChart = new Chart(ctx, {
      data: { labels: rawOrder, datasets: buildDatasets("cumulative") },
      options: {
        responsive: true,
        plugins: {
          legend: {
            labels: {
              filter: item => !item.label.endsWith(" avg"),
              usePointStyle: true,
            },
          },
          tooltip: {
            callbacks: {
              label: ctx => ctx.dataset.label + ": " + (ctx.parsed.y != null ? ctx.parsed.y + "%" : "—"),
            },
          },
        },
        scales: {
          y: { title: { display: true, text: "Accuracy %" }, min: 0, max: 100 },
          x: { ticks: { maxRotation: 35, autoSkip: false } },
        },
      },
    });

    // Expose toggle function globally
    window._accuracyRawLabels   = rawOrder;
    window._accuracyBuildDatasets = buildDatasets;
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
          const lbl = sessionLabel(h.date, h.session);
          seriesMap[key][lbl] = h.portfolio_value;
          allDates.add(lbl);
        });
      } catch (_) {}
    }

    // Always start every line at $10,000 before the first real data point
    const START_LABEL = "Start";
    allDates.add(START_LABEL);
    const labels = [START_LABEL, ...Array.from(allDates).filter(l => l !== START_LABEL).sort()];

    const datasets = Object.entries(MODELS).map(([key, meta]) => ({
      label:           meta.display,
      data:            labels.map(l => l === START_LABEL ? 10000 : (seriesMap[key]?.[l] ?? null)),
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
      data: { labels, datasets },
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
  const listEl      = document.getElementById("history-list");
  const filterEl    = document.getElementById("history-model-filter");
  const startDate   = document.getElementById("history-start-date").value;
  const endDate     = document.getElementById("history-end-date").value;
  const modelFilter = filterEl.value;

  listEl.innerHTML = '<div class="loading">Loading…</div>';

  try {
    const { dates } = await apiFetch("/api/predictions/dates");
    if (!dates || !dates.length) {
      listEl.innerHTML = '<div class="loading">No historical data yet.</div>';
      return;
    }

    // Populate model filter dropdown once
    if (filterEl.options.length <= 1) {
      Object.entries(MODELS).forEach(([key, meta]) => {
        const opt = document.createElement("option");
        opt.value = key; opt.textContent = meta.display;
        filterEl.appendChild(opt);
      });
    }

    // Filter by date range
    const filtered = dates.filter(d =>
      (!startDate || d >= startDate) && (!endDate || d <= endDate)
    );

    if (!filtered.length) {
      listEl.innerHTML = '<div class="loading">No entries in selected date range.</div>';
      return;
    }

    // Update export link to match selected range
    const exportEl = document.getElementById("export-csv-btn");
    const expStart = startDate || filtered[filtered.length - 1];
    const expEnd   = endDate   || filtered[0];
    exportEl.href  = `/api/export/csv?start=${expStart}&end=${expEnd}`;

    listEl.innerHTML = "";

    filtered.forEach((d, idx) => {
      const isFirst = idx === 0;
      const group   = document.createElement("div");
      group.className = "history-date-group";
      group.innerHTML = `
        <div class="history-date-header" data-open="${isFirst}">
          <span class="history-date-chevron">${isFirst ? "▼" : "▶"}</span>
          <span class="history-date-label">${fmtDate(d)}</span>
        </div>
        <div class="history-date-body"${isFirst ? "" : ' style="display:none"'}>
          <div class="loading" style="padding:16px 0">Loading…</div>
        </div>`;

      listEl.appendChild(group);

      const header  = group.querySelector(".history-date-header");
      const body    = group.querySelector(".history-date-body");
      const chevron = group.querySelector(".history-date-chevron");

      if (isFirst) loadDateSessions(d, body, modelFilter);

      header.addEventListener("click", () => {
        const open = header.dataset.open === "true";
        header.dataset.open = String(!open);
        chevron.textContent  = open ? "▶" : "▼";
        body.style.display   = open ? "none" : "block";
        if (!open && !body.dataset.loaded) loadDateSessions(d, body, modelFilter);
      });
    });

  } catch (err) {
    listEl.innerHTML = `<div class="loading">Error: ${err.message}</div>`;
  }
}

async function loadDateSessions(d, bodyEl, modelFilter) {
  bodyEl.dataset.loaded = "true";
  try {
    const [dayData, nightData, dayScores, nightScores] = await Promise.all([
      apiFetch(`/api/predictions?date=${d}&session=day`),
      apiFetch(`/api/predictions?date=${d}&session=overnight`),
      apiFetch(`/api/accuracy/scores?date=${d}&session=day`),
      apiFetch(`/api/accuracy/scores?date=${d}&session=overnight`),
    ]);

    bodyEl.innerHTML = "";

    [
      { label: "☀️ Morning", data: dayData,   scoresData: dayScores   },
      { label: "🌙 Evening", data: nightData, scoresData: nightScores },
    ].forEach(({ label, data, scoresData }) => {
      const preds  = (data.predictions || []).filter(p =>
        !modelFilter || p.model_name === modelFilter
      );
      const scores = scoresData.scores || {};  // {prediction_id: {is_correct, actual_change_pct}}

      const section  = document.createElement("div");
      section.className = "history-session-group";

      const modelCount = new Set(preds.map(p => p.model_name)).size;
      const countLabel = preds.length ? `${modelCount} model${modelCount !== 1 ? "s" : ""}` : "No data";

      const sHeader = document.createElement("div");
      sHeader.className = "history-session-header";
      sHeader.innerHTML = `
        <span class="session-chevron">▼</span>
        <span class="session-label">${label}</span>
        <span class="session-count">${countLabel}</span>`;

      const sBody = document.createElement("div");
      sBody.className = "history-session-body";

      if (!preds.length) {
        sBody.innerHTML = '<div class="history-no-session">No picks for this session.</div>';
      } else {
        const byModel = {};
        preds.forEach(p => {
          if (!byModel[p.model_name]) byModel[p.model_name] = [];
          byModel[p.model_name].push(p);
        });

        Object.entries(MODELS).forEach(([mkey, meta]) => {
          if (modelFilter && mkey !== modelFilter) return;
          const picks = (byModel[mkey] || []).sort((a, b) => a.rank - b.rank);
          if (!picks.length) return;

          const row = document.createElement("div");
          row.className = "history-model-row";

          const chips = picks.map(p => {
            const isLong  = (p.direction || "LONG").toUpperCase() === "LONG";
            const alloc   = p.allocation_pct != null ? Number(p.allocation_pct).toFixed(0) : "20";
            const score   = scores[p.id];
            const scored  = score != null;
            const correct = scored && score.is_correct === 1;
            const chipCls = scored ? (correct ? " h-chip-correct" : " h-chip-wrong") : "";
            const changeLbl = scored
              ? `<span class="h-chip-chg ${correct ? "chg-pos" : "chg-neg"}">${score.actual_change_pct >= 0 ? "+" : ""}${Number(score.actual_change_pct).toFixed(2)}%</span>`
              : "";
            return `<div class="h-chip${chipCls}" data-id="${p.id}">
              <span class="h-chip-arrow ${isLong ? "arrow-up" : "arrow-down"}">${isLong ? "▲" : "▼"}</span>
              <span class="h-chip-ticker">${p.ticker}</span>
              <span class="h-chip-alloc">${alloc}%</span>
              ${changeLbl}
              <span class="badge badge-${p.confidence}">${p.confidence}</span>
            </div>`;
          }).join("");

          row.innerHTML = `
            <div class="h-model-label" style="color:${meta.color}">${MODEL_AVATARS[mkey] || "🤖"} ${meta.display}</div>
            <div class="h-chips">${chips}</div>`;
          sBody.appendChild(row);
        });
      }

      let open = true;
      sHeader.addEventListener("click", () => {
        open = !open;
        sBody.style.display = open ? "block" : "none";
        sHeader.querySelector(".session-chevron").textContent = open ? "▼" : "▶";
      });

      section.appendChild(sHeader);
      section.appendChild(sBody);
      bodyEl.appendChild(section);
    });

  } catch (err) {
    bodyEl.innerHTML = `<div class="loading">Error: ${err.message}</div>`;
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



// ── Accuracy chart avg-mode toggle ───────────────────────────────────────────

function setAvgMode(mode) {
  document.getElementById("avg-cumulative").classList.toggle("active", mode === "cumulative");
  document.getElementById("avg-rolling").classList.toggle("active", mode === "rolling");
  if (!accuracyChart || !window._accuracyBuildDatasets) return;
  accuracyChart.data.datasets = window._accuracyBuildDatasets(mode);
  accuracyChart.update();
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

  // History filters
  document.getElementById("history-model-filter").addEventListener("change", loadHistory);
  document.getElementById("history-apply-btn").addEventListener("click", loadHistory);

  // Default date range: last 30 days
  const histEnd   = new Date();
  const histStart = new Date();
  histStart.setDate(histStart.getDate() - 30);
  document.getElementById("history-end-date").value   = histEnd.toISOString().slice(0, 10);
  document.getElementById("history-start-date").value = histStart.toISOString().slice(0, 10);

  // Load initial tab
  loadPicks(isoToday(), currentSession);
}

document.addEventListener("DOMContentLoaded", init);
