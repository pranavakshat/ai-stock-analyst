# AI Stock Analyst Agent — Multi-Model Daily Tracker

Every morning and evening, five AI models are each given a rich live market briefing — compiled from up to 12 concurrent data sources — and asked for their top 5 stock picks of the session. Long or short, any market (including international), conviction-weighted. Results land in your inbox as a polished email digest and are tracked on a live dashboard showing each model's accuracy and a simulated $10,000 portfolio.

**Live dashboard:** https://ai-stock-analyst-production-868a.up.railway.app

---

## What It Does

Two scheduled jobs run automatically every trading day:

**8 AM CT — Morning Job**
1. Scores the previous evening's overnight picks using pre-market prices (via `yf.fast_info`)
2. Compiles full market context from up to 12 concurrent data sources
3. Injects each model's own track record + cross-model picks into the prompt
4. Queries all AI models concurrently for their top 5 **day-session** picks (open → close)
5. Saves picks to SQLite, sends morning email digest, auto-backs up to CSV

**6 PM CT — Evening Job**
1. Fetches end-of-day prices for every picked stock
2. Scores today's day-session picks (correct direction = win)
3. Updates the $10,000 portfolio simulation using conviction weighting
4. Queries all models for **overnight** picks (close → next open)
5. Sends evening email digest, auto-backs up to CSV

---

## AI Models

| Key | Model | Provider | Notes |
|-----|-------|----------|-------|
| `claude` | claude-opus-4-6 | Anthropic | Extended thinking enabled |
| `chatgpt` | gpt-4o | OpenAI | JSON mode enforced |
| `grok` | grok-3 | xAI | OpenAI-compatible API |
| `gemini` | gemini-2.5-flash | Google | Extended thinking enabled |
| `copilot` | gpt-4o (Azure) | Microsoft | Optional; Azure OpenAI endpoint |

Models without a configured API key are skipped gracefully. The rest still run.

Model versions are configurable via env vars without redeploying (`CLAUDE_MODEL`, `CHATGPT_MODEL`, `GROK_MODEL`).

---

## Market Context — 12 Concurrent Modules

All modules run in parallel (75-second timeout). Each fails gracefully if the source is unavailable.

| Module | Source | What It Provides |
|--------|--------|------------------|
| `macro` | yfinance | SPY / QQQ / VIX / DXY / TNX / GLD / OIL snapshot |
| `sector` | yfinance | All 11 SPDR sector ETF performances |
| `fear_greed` | yfinance (VIX proxy) | Market sentiment score 0–100 |
| `news` | NewsAPI | Top financial headlines (free, 100 req/day) |
| `earnings` | NASDAQ public API | Rolling 7-day upcoming earnings (BMO/AMC tagged) + past-week reactions with % moves |
| `technicals` | yfinance (batch) | RSI(14), MACD cross, 50/200 MA alignment, relative volume, 52-week proximity for 28 tickers |
| `options` | yfinance | CBOE equity + composite put/call ratios; per-stock nearest-expiry skew |
| `short_interest` | yfinance `.info` | Short % of float + days-to-cover — highlights squeeze/drop candidates (≥10% float) |
| `finnhub_context` | Finnhub API | Insider transactions, news sentiment, analyst consensus buy/hold/sell (optional) |
| `analyst` | yfinance | Recent upgrades/downgrades/initiations |
| `movers` | yfinance | Pre-session top gainers and losers |
| `overnight` | all of the above | After-hours movers + gap analysis for the overnight session |

### Cross-Model Learning

Before each model generates picks, it receives:
- **Its own 14-day track record**: accuracy % and recent picks by date
- **Other models' most recent picks**: with a note to think independently, not follow consensus

This is built by `models/track_record.py` and injected automatically in `models/runner.py`.

### International Stocks

The prompt explicitly allows globally-listed tickers in yfinance format:
- `9984.T` — SoftBank (Tokyo)
- `SHOP.TO` — Shopify (Toronto)
- `0700.HK` — Tencent (Hong Kong)

---

## How Picks Work

Each model returns exactly 5 picks in structured JSON:

```json
{
  "picks": [
    {
      "rank": 1,
      "ticker": "NVDA",
      "direction": "LONG",
      "allocation_pct": 40,
      "reasoning": "Specific catalyst or technical signal...",
      "confidence": "High"
    }
  ]
}
```

- **direction** — `LONG` (profit if stock rises) or `SHORT` (profit if stock falls)
- **allocation_pct** — Portfolio % for this pick; all 5 must sum to ~100
- **confidence** — `High`, `Medium`, or `Low`

The system prompt tells models to seek specific catalysts — earnings setups, technical breakouts, short squeeze setups, macro regime plays — and avoid defaulting to household names without a clear reason.

---

## Dual Sessions

The system runs **two sessions per day**:

| Session | Window | Scored Against |
|---------|--------|----------------|
| `day` | Market open → close | EOD close vs. open price |
| `overnight` | Close → next open | Pre-market price at 8 AM vs. prior close |

The dashboard has a **☀️ Day / 🌙 Overnight toggle** to filter picks by session.

---

## Portfolio Simulation

Each model manages a simulated **$10,000 portfolio**. Every session:

1. Each pick's `allocation_pct` determines its dollar position
2. LONG: `position × (1 + change_pct)`
3. SHORT: `position × (1 − change_pct)` — profits when the stock falls
4. A `TRADE_FEE_PCT` (default `0.0003` = 0.03%) is deducted per trade, matching Robinhood's SEC + FINRA TAF structure
5. Portfolio value compounds session over session

---

## Accuracy Scoring

A pick is **correct** if the stock moved in the predicted direction:
- LONG → stock closed higher ✓
- SHORT → stock closed lower ✓

The leaderboard tracks correct picks, total picks, accuracy %, and average return % — filterable by: All Time / 1Y / 3M / 1M / 1W / 1D.

---

## Email Digest

Sent via [Resend](https://resend.com) (free tier: 100 emails/day, 3,000/month).

- **Above-the-fold snapshot card** per model: tickers, direction arrows, confidence badges, allocation %
- **Full reasoning section**: detailed explanation per pick
- **Session-aware subject**: `☀️ Day Session` or `🌙 Overnight`
- **Live dashboard link** embedded in the header (set `DASHBOARD_URL` in Railway)

---

## Data Storage & Backup

SQLite database at `DATABASE_PATH` (default `data/predictions.db`).

**Tables**: `predictions`, `stock_results`, `accuracy_scores`, `portfolio_values`

**Railway-safe backup/restore**: Railway wipes ephemeral disks on every redeploy. This is handled automatically:
- After every job, a full CSV snapshot is written to `backups/` (absolute path alongside the DB)
- On startup, if the DB is empty, the **most recent** backup is restored automatically (the latest file is always cumulative, so only that one is loaded)
- The `backups/` folder is git-tracked so backups survive redeployments

---

## API Reference

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/` | Dashboard HTML |
| GET | `/health` | Health check |
| GET | `/api/predictions?date=YYYY-MM-DD&session=day` | Picks for a date (session optional: `day` or `overnight`) |
| GET | `/api/predictions/dates` | All dates that have predictions |
| GET | `/api/leaderboard?period=1m` | P&L + accuracy leaderboard (periods: `1d 1w 1m 3m 1y all`) |
| GET | `/api/accuracy` | All-time per-model accuracy summary |
| GET | `/api/accuracy/<model>` | Daily accuracy history for one model |
| GET | `/api/portfolio` | Latest portfolio value per model |
| GET | `/api/portfolio/<model>` | Full portfolio history for one model |
| GET | `/api/models` | Model metadata (names, colours) |
| POST | `/api/run/morning` | Manually trigger morning job |
| POST | `/api/run/evening?date=YYYY-MM-DD` | Manually trigger evening job (optional date override) |
| GET | `/api/export/csv?start=&end=` | Download all predictions as CSV |
| POST | `/api/import/predictions` | Import predictions from a CSV file |

---

## Folder Structure

```
├── app.py                      # Flask app + API routes + scheduler bootstrap
├── scheduler.py                # APScheduler morning (8 AM) / evening (6 PM) jobs
├── config.py                   # All env var loading (single source of truth)
├── requirements.txt
├── railway.toml
│
├── models/
│   ├── runner.py               # ThreadPoolExecutor — calls all adapters concurrently
│   ├── prompt.py               # System + user prompt templates (JSON schema enforced)
│   ├── base.py                 # parse_picks(), fallback_picks() shared helpers
│   ├── track_record.py         # Per-model history + cross-model context injection
│   ├── claude_model.py         # Anthropic Claude (extended thinking)
│   ├── chatgpt.py              # OpenAI ChatGPT (JSON mode)
│   ├── grok.py                 # xAI Grok (OpenAI-compatible)
│   ├── gemini.py               # Google Gemini (extended thinking)
│   └── copilot.py              # Azure OpenAI / Copilot
│
├── market_context/
│   ├── fetcher.py              # Orchestrates all modules concurrently (12 workers, 75s timeout)
│   ├── macro.py                # SPY/QQQ/VIX/DXY/TNX/GLD/OIL snapshot
│   ├── news.py                 # NewsAPI headlines
│   ├── sector.py               # SPDR sector ETF performance
│   ├── fear_greed.py           # VIX-based sentiment score
│   ├── earnings.py             # Rolling 7-day calendar + past reactions (NASDAQ API, no key)
│   ├── technicals.py           # RSI / MACD / MA / relative volume (batch yfinance download)
│   ├── options.py              # CBOE P/C ratios + per-stock put/call skew
│   ├── short_interest.py       # Short % of float + squeeze candidates
│   ├── finnhub_context.py      # Insider trades / sentiment / analyst consensus (optional)
│   ├── analyst.py              # Recent upgrades/downgrades/initiations
│   ├── movers.py               # Pre-session top gainers and losers
│   └── overnight.py            # After-hours context for overnight session
│
├── accuracy/
│   └── tracker.py              # score_predictions(), update_portfolios(),
│                               # score_overnight_picks() (pre-market prices via fast_info)
│
├── stock_data/
│   └── fetcher.py              # fetch_eod_prices(), fetch_premarket_prices()
│
├── email_service/
│   └── emailer.py              # HTML + plain-text digest builder + Resend sender
│
├── database/
│   ├── db.py                   # All SQLite CRUD + backup/restore
│   └── schema.sql              # Tables + indexes
│
├── dashboard/
│   ├── templates/index.html    # Single-page dashboard (day/overnight toggle, dark mode)
│   └── static/
│       ├── app.js              # API calls + chart rendering + session state
│       └── style.css           # Responsive layout + dark mode
│
└── backups/                    # Auto-generated CSV snapshots (git-tracked for Railway)
    └── predictions_YYYY-MM-DD.csv
```

---

## Setup

### 1. Clone & install

```bash
git clone https://github.com/pranavakshat/ai-stock-analyst.git
cd ai-stock-analyst
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment variables

Copy `.env.example` to `.env` and fill in your keys:

```env
# ── Required ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY=        # console.anthropic.com
OPENAI_API_KEY=           # platform.openai.com/api-keys
RESEND_API_KEY=           # resend.com — free tier fine
EMAIL_RECIPIENT=          # Where to send the daily digest
EMAIL_FROM=               # Verified sender in Resend (e.g. picks@yourdomain.com)

# ── Recommended ───────────────────────────────────────────────────────────────
XAI_API_KEY=              # console.x.ai
GOOGLE_API_KEY=           # aistudio.google.com/app/apikey
FINNHUB_API_KEY=          # finnhub.io — free, 60 req/min, no card needed
NEWS_API_KEY=             # newsapi.org — free, 100 req/day
DASHBOARD_URL=            # Your deployed Railway URL (embeds link in email)

# ── Azure OpenAI / Copilot (optional) ─────────────────────────────────────────
AZURE_OPENAI_KEY=
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_DEPLOY=gpt-4o

# ── Model version overrides (change without redeploying) ──────────────────────
CLAUDE_MODEL=claude-opus-4-6
CHATGPT_MODEL=gpt-4o
GROK_MODEL=grok-3

# ── Scheduler ─────────────────────────────────────────────────────────────────
MORNING_HOUR=8            # 8 AM — set in Railway Variables
EVENING_HOUR=18           # 6 PM
TIMEZONE=America/Chicago

# ── Portfolio ─────────────────────────────────────────────────────────────────
STARTING_PORTFOLIO_VALUE=10000
TRADE_FEE_PCT=0.0003      # ~0.03% regulatory fee per trade
```

### 3. Run locally

```bash
python app.py
```

Dashboard at `http://localhost:5000`. Trigger jobs manually:

```bash
curl -X POST http://localhost:5000/api/run/morning
curl -X POST http://localhost:5000/api/run/evening
```

---

## Deploy to Railway

1. Push to GitHub (`.env` is gitignored — never commit secrets)
2. Railway → New Project → Deploy from GitHub repo
3. Set all environment variables in Railway → Variables
4. Set `MORNING_HOUR=8` (Railway runs in UTC by default; set `TIMEZONE` to match)
5. Railway auto-detects `railway.toml` — no Dockerfile needed

The startup restore logic will reload all predictions from `backups/` automatically if the DB is wiped.

---

## Adding a New Model

1. Create `models/your_model.py` with a `get_picks(market_context, system_prompt_override, user_prompt_builder)` function returning `(picks: list[dict], raw: str)`
2. Import and register it in `models/runner.py` → `ADAPTERS`
3. Add metadata to `MODELS` in `config.py`
4. Add an avatar emoji in `email_service/emailer.py` → `MODEL_AVATARS`
5. Redeploy

---

## Troubleshooting

**Gemini returning no picks:** Check billing at aistudio.google.com. Free tier quota can be 0 on some project types. Create a fresh API key in AI Studio and add credits if needed.

**Email not arriving:** Check Railway logs around job time for Resend errors. Verify `RESEND_API_KEY` is set and `EMAIL_FROM` is a verified sender in your Resend dashboard. Check spam on first send.

**yfinance returning empty data:** Markets are closed on weekends and US holidays. The evening job logs a warning and skips — expected behaviour.

**Market context sections missing:** Each module logs at WARNING level on failure. Check Railway logs around 8 AM for `market_context.*` warnings to see which sources timed out or errored.

**Pre-market prices empty:** `fast_info.pre_market_price` returns `None` outside pre-market hours. The fetcher falls back to `regular_market_price` → `last_price` → previous close automatically.

---

## Disclaimer

This project is for educational and research purposes only. Nothing produced by this system constitutes financial advice. AI model predictions are experimental and should not be used for real investment decisions. Past simulated performance does not guarantee future results.
