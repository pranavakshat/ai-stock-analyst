# AI Stock Analyst — Multi-Model Daily Tracker

Every morning at 5 AM, five AI models are each asked for their top 5 US stock picks of the day. Results land in your inbox and are tracked on a live dashboard that shows accuracy over time and simulates a $10,000 portfolio per model.

---

## Folder Structure

```
ai-stock-analyst/
├── app.py                  # Flask app + scheduler bootstrap
├── scheduler.py            # APScheduler (5 AM + 6 PM jobs)
├── config.py               # All env-var config
├── backup.py               # CSV/JSON data export
├── requirements.txt
├── .env.example            # Copy to .env and fill in
├── Dockerfile
├── railway.toml            # Railway deployment config
├── render.yaml             # Render deployment config
├── .gitignore
│
├── models/
│   ├── prompt.py           # Shared system prompt + user message
│   ├── base.py             # JSON parser shared by all model adapters
│   ├── runner.py           # Calls all 5 models concurrently
│   ├── claude_model.py     # Anthropic
│   ├── chatgpt.py          # OpenAI
│   ├── copilot.py          # Azure OpenAI (Microsoft Copilot)
│   ├── grok.py             # xAI
│   └── gemini.py           # Google
│
├── database/
│   ├── schema.sql          # Table definitions
│   └── db.py               # All read/write helpers
│
├── email_service/
│   └── emailer.py          # Gmail SMTP digest sender
│
├── stock_data/
│   └── fetcher.py          # yfinance EOD price fetcher
│
├── accuracy/
│   └── tracker.py          # Score predictions + update portfolios
│
├── dashboard/
│   ├── templates/index.html
│   └── static/
│       ├── style.css
│       └── app.js
│
├── data/                   # SQLite DB lives here (git-ignored)
├── exports/                # One-off export files
└── backups/                # Daily backup snapshots
```

---

## Quick Start (Local)

### 1. Clone & install

```bash
git clone https://github.com/YOUR_USERNAME/ai-stock-analyst.git
cd ai-stock-analyst
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure secrets

```bash
cp .env.example .env
# Open .env in your editor and fill in all values
```

Key values you need:

| Variable | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | https://console.anthropic.com/settings/keys |
| `OPENAI_API_KEY` | https://platform.openai.com/api-keys |
| `GOOGLE_API_KEY` | https://aistudio.google.com/app/apikey |
| `XAI_API_KEY` | https://console.x.ai |
| `AZURE_OPENAI_KEY` + `AZURE_OPENAI_ENDPOINT` | https://portal.azure.com → Azure OpenAI resource |
| `GMAIL_ADDRESS` + `GMAIL_APP_PASS` | Your Gmail + App Password (see below) |

**Gmail App Password:** Enable 2-Factor Auth on your Google account, then go to https://myaccount.google.com/apppasswords, create an app password for "Mail", and paste the 16-character code into `GMAIL_APP_PASS`.

### 3. Run locally

```bash
python app.py
```

Open http://localhost:5000 to see the dashboard.

### 4. Trigger a manual run (without waiting for 5 AM)

Click **▶ Run Morning Job** on the dashboard, or via curl:

```bash
curl -X POST http://localhost:5000/api/run/morning
curl -X POST http://localhost:5000/api/run/evening
```

---

## API Reference

| Method | Path | Description |
|---|---|---|
| GET | `/` | Dashboard HTML |
| GET | `/health` | Health check |
| GET | `/api/predictions?date=YYYY-MM-DD` | Today's (or any date's) picks |
| GET | `/api/predictions/dates` | All dates with predictions |
| GET | `/api/accuracy` | Per-model accuracy leaderboard |
| GET | `/api/accuracy/<model>` | Daily accuracy history for one model |
| GET | `/api/portfolio` | Latest portfolio value per model |
| GET | `/api/portfolio/<model>` | Full portfolio history for one model |
| GET | `/api/models` | Model names and colors |
| POST | `/api/run/morning` | Manually trigger morning job |
| POST | `/api/run/evening` | Manually trigger evening job |
| GET | `/api/export/csv?start=...&end=...` | Download predictions as CSV |

---

## Deploying to Railway (Recommended)

Railway has a free tier that's plenty for this project.

1. Push your code to GitHub (make sure `.env` is in `.gitignore` — it already is).
2. Go to https://railway.app → New Project → Deploy from GitHub repo.
3. Select your repo.
4. In the Railway dashboard: **Variables** → add every key from `.env.example`.
5. Railway will auto-detect the `railway.toml` and start gunicorn.
6. Your app will be live at `https://ai-stock-analyst-production.up.railway.app` (or similar).

**Persistent storage note:** Railway's free tier doesn't have persistent disk storage by default. Your SQLite DB will reset on redeploy. To fix this, either:
- Upgrade to Railway's $5/month plan which includes a persistent volume, OR
- Switch `DATABASE_PATH` to point to a Railway PostgreSQL add-on (requires minor code change to use `psycopg2` instead of `sqlite3`).

---

## Deploying to Render

1. Push to GitHub.
2. Go to https://render.com → New → Web Service → connect your repo.
3. Render will detect `render.yaml` automatically.
4. Add all environment variables in the Render dashboard under **Environment**.
5. Click **Deploy**.

Same persistent storage caveat applies. Render's free tier puts services to sleep after 15 min of inactivity — the scheduler won't fire reliably. Upgrade to the $7/month Individual plan for always-on.

---

## Deploying with Docker

```bash
docker build -t ai-stock-analyst .
docker run -d \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  -p 5000:5000 \
  ai-stock-analyst
```

The `-v` mount keeps your SQLite database on your local machine across restarts.

---

## Data Backup & Export

Manual one-time export (JSON + CSV per table):

```bash
python backup.py
# Creates: backups/2025-01-15/predictions.json, etc.

python backup.py --output ./my-export
```

Export via API (predictions only):

```bash
curl "http://localhost:5000/api/export/csv?start=2025-01-01&end=2025-12-31" -o picks.csv
```

---

## How Accuracy Is Calculated

A pick is "correct" if the stock's close price is **higher** than its open price on the predicted trading day (i.e. the stock went up intraday). This is the strictest and most objective measure.

For the portfolio simulation, each model's $10,000 is split equally across its 5 picks each day, and actual intraday returns are applied. The portfolio value compounds daily.

---

## Adding or Swapping a Model

1. Copy any file in `models/` (e.g. `chatgpt.py`) as a template.
2. Implement `get_picks() -> tuple[list[dict], str]`.
3. Add the new key to `ADAPTERS` in `models/runner.py`.
4. Add it to `MODELS` in `config.py`.
5. Restart the app.

---

## Troubleshooting

**Email not sending:** Check that you're using a Gmail App Password (not your login password). Regular passwords won't work when 2FA is enabled.

**Copilot returning errors:** Azure OpenAI requires an active Azure subscription and a deployed model. The key, endpoint URL, and deployment name must all be set correctly.

**`yfinance` returning empty data:** Markets are closed on weekends and holidays. The evening job will log a warning and skip scoring — this is expected behaviour.

**Grok API errors:** Make sure your xAI account has API access enabled at https://console.x.ai. The model name may change — update `"grok-3"` in `models/grok.py` if needed.
