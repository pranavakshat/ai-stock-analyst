# AI Stock Analyst — Multi-Model Daily Tracker

Every morning at 5 AM (Chicago time), four AI models are each given a rich live market briefing and asked for their top US stock picks of the day — long or short, any market cap, with a conviction-weighted portfolio allocation. Results land in your inbox and are tracked on a live dashboard showing accuracy and a simulated $10,000 portfolio per model.

**Live dashboard:** https://ai-stock-analyst-production-868a.up.railway.app

---

## What it does

**Morning job (5 AM CT):**
1. Fetches live market context from 8 data sources (runs in parallel, ~8 seconds total)
2. Injects that context into each AI model's prompt
3. Queries Claude, ChatGPT, Grok, and Gemini concurrently
4. Saves all picks to SQLite
5. Sends a formatted HTML email digest via Resend

**Evening job (6 PM CT):**
1. Fetches end-of-day prices for every picked stock via yfinance
2. Scores each pick correct/incorrect (accounting for LONG and SHORT direction)
3. Updates the $10,000 portfolio simulation using each model's conviction weighting

---

## Live market context injected into every prompt

All 8 modules run concurrently. Each fails gracefully if the data source is unavailable.

| Module | Data | Key needed? |
|--------|------|-------------|
| Indices & sectors | SPY, QQQ, DIA, IWM, VIX + 11 sector ETFs (prev session %) | No — yfinance |
| Fear & Greed Index | CNN Fear & Greed 0–100 score | No — alternative.me |
| Pre-session movers | Top gainers/losers from 60-ticker watchlist | No — yfinance |
| Macro indicators | 10Y/30Y Treasury yields, BTC, ETH, Gold, Crude Oil, USD Index | No — yfinance |
| Economic calendar | High-impact USD events this week (FOMC, CPI, NFP, PCE) | No — Forex Factory |
| Earnings calendar | Who reports today + next 4 trading days (BMO/AMC timing) | No — NASDAQ public API |
| Analyst actions | Upgrades/downgrades/initiations in last 48h across 35 tickers | No — yfinance |
| Market news | Top 15 financial headlines from last 18 hours | Yes — NewsAPI (free) |
| Reddit sentiment | Most-mentioned tickers in WSB, r/stocks, r/investing | No — Reddit public JSON |

---

## How picks work

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

- **direction** — `LONG` (profit if stock rises) or `SHORT` (profit if stock falls). Models pick the mix freely.
- **allocation_pct** — How much of that day's portfolio the model wants in this pick. All 5 must sum to 100. A model that puts 50% on one name is expressing real conviction.
- **confidence** — `High`, `Medium`, or `Low`.

The system prompt explicitly tells models to avoid defaulting to blue-chip household names unless there's a specific catalyst, and to seek mid/small-cap momentum plays, earnings catalysts, technical breakouts, and short squeeze setups.

---

## Portfolio simulation

Each model starts with $10,000. Every trading day:

1. Each pick's allocation % determines its dollar position: `position = portfolio_value × (allocation_pct / 100)`
2. If some tickers lack EOD data, remaining allocations are re-normalized to 100%
3. LONG: `position × (1 + daily_return)`
4. SHORT: `position × (1 - daily_return)`  ← profits when the stock falls
5. New portfolio value = sum of all position results

This means a model that went 60% on one name and it dropped 5% takes a real hit. High conviction cuts both ways.

---

## Accuracy scoring

A pick is **correct** if the stock moved in the predicted direction by end of day:
- LONG pick → stock closed higher than open ✓
- SHORT pick → stock closed lower than open ✓

The leaderboard tracks correct pick count, total picks, accuracy %, and average return % — all filterable by: All Time / 5Y / 1Y / 3M / 1M / 1W / 1D.

---

## Models

| Key | Model | Provider |
|-----|-------|----------|
| `claude` | claude-opus-4-6 | Anthropic |
| `chatgpt` | gpt-4o | OpenAI |
| `grok` | grok-3 | xAI |
| `gemini` | gemini-2.5-flash (falls back through 4 candidates) | Google |

---

## Folder structure

```
ai-stock-analyst/
├── app.py                    # Flask app + API routes
├── scheduler.py              # APScheduler (5 AM + 6 PM jobs)
├── config.py                 # All env-var config
├── requirements.txt
├── railway.toml              # Railway deployment (Nixpacks, no Dockerfile)
│
├── models/
│   ├── prompt.py             # System prompt + user message builder
│   ├── base.py               # JSON parser (handles direction + allocation_pct)
│   ├── runner.py             # Fetches context, queries all 4 models concurrently
│   ├── claude_model.py
│   ├── chatgpt.py
│   ├── grok.py
│   └── gemini.py
│
├── market_context/
│   ├── fetcher.py            # Orchestrator — runs all modules in parallel
│   ├── movers.py             # Pre-session movers (yfinance bulk download)
│   ├── macro.py              # Yields, crypto, commodities + economic calendar
│   ├── earnings.py           # NASDAQ earnings calendar (no key)
│   ├── analyst.py            # Recent analyst upgrades/downgrades (yfinance)
│   ├── news.py               # NewsAPI headlines (free key)
│   └── reddit.py             # WSB + r/stocks + r/investing trending tickers
│
├── database/
│   ├── schema.sql            # 4 tables: predictions, stock_results,
│   │                         #           accuracy_scores, portfolio_values
│   └── db.py                 # All read/write helpers + auto-migration
│
├── email_service/
│   └── emailer.py            # Resend HTTP API digest (not Gmail SMTP)
│
├── stock_data/
│   └── fetcher.py            # yfinance EOD price fetcher
│
├── accuracy/
│   └── tracker.py            # Score predictions + conviction-weighted portfolios
│
└── dashboard/
    ├── templates/index.html
    └── static/
        ├── style.css
        └── app.js
```

---

## API reference

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Dashboard HTML |
| GET | `/health` | Health check |
| GET | `/api/predictions?date=YYYY-MM-DD` | Picks for a date (defaults to today) |
| GET | `/api/predictions/dates` | All dates with predictions |
| GET | `/api/leaderboard?period=1m` | P&L + accuracy leaderboard for a period |
| GET | `/api/accuracy` | All-time accuracy summary |
| GET | `/api/accuracy/<model>` | Daily accuracy history for one model |
| GET | `/api/portfolio` | Latest portfolio value per model |
| GET | `/api/portfolio/<model>` | Full portfolio history for one model |
| GET | `/api/models` | Model metadata (names, colors) |
| POST | `/api/run/morning` | Manually trigger morning job |
| POST | `/api/run/evening` | Manually trigger evening job |
| GET | `/api/export/csv?start=...&end=...` | Download picks as CSV |

Period values for `/api/leaderboard`: `all`, `5y`, `1y`, `3m`, `1m`, `1w`, `1d`

---

## Setup

### 1. Clone & install

```bash
git clone https://github.com/pranavakshat/ai-stock-analyst.git
cd ai-stock-analyst
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure secrets

Create a `.env` file in the project root:

```env
# AI Models
ANTHROPIC_API_KEY=...          # console.anthropic.com
OPENAI_API_KEY=...             # platform.openai.com/api-keys
XAI_API_KEY=...                # console.x.ai
GOOGLE_API_KEY=...             # aistudio.google.com/app/apikey

# Email (Resend — not Gmail SMTP)
RESEND_API_KEY=...             # resend.com — free, 3,000/month
EMAIL_RECIPIENT=you@gmail.com

# Market context
NEWS_API_KEY=...               # newsapi.org — free, 100 req/day

# Optional overrides
TIMEZONE=America/Chicago       # default: America/Chicago
MORNING_HOUR=5                 # default: 5
EVENING_HOUR=18                # default: 18
STARTING_PORTFOLIO_VALUE=10000 # default: 10000
```

### 3. Run locally

```bash
python app.py
```

Open http://localhost:5000.

To trigger jobs without waiting for the schedule:
```bash
curl -X POST http://localhost:5000/api/run/morning
curl -X POST http://localhost:5000/api/run/evening
```

---

## Deploy to Railway

1. Push to GitHub (`.env` is in `.gitignore` — never commit secrets)
2. Go to railway.app → New Project → Deploy from GitHub repo
3. Add all env variables in Railway → Variables
4. Railway auto-detects `railway.toml` and uses Nixpacks (no Dockerfile needed)
5. Live at your Railway URL

**Persistent storage:** Railway's free tier resets the SQLite DB on redeploy. For persistent data, add a Railway Volume ($5/month) or migrate to PostgreSQL.

---

## Adding a new model

1. Copy `models/chatgpt.py` as a template
2. Implement `get_picks(market_context: str = "") -> tuple[list[dict], str]`
3. Register it in `ADAPTERS` in `models/runner.py`
4. Add metadata to `MODELS` in `config.py`
5. Redeploy

---

## Troubleshooting

**Gemini returning no picks:** Check billing at aistudio.google.com — free tier quota is 0 on some project types. Add credits or create a new API key directly in AI Studio.

**Email not arriving:** Check Railway logs for Resend errors. Verify `RESEND_API_KEY` is set. Check spam folder on first send.

**yfinance returning empty data:** Markets are closed on weekends and US holidays. The evening job logs a warning and skips — expected behaviour.

**Market context missing sections:** Each module logs its status. Check Railway logs around the morning job time for any `WARNING` lines from `market_context.*`.
