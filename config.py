"""
config.py — Centralised configuration loaded from environment variables.
Copy .env.example to .env and fill in your keys before running.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── General ──────────────────────────────────────────────────────────────────
APP_SECRET_KEY = os.getenv("APP_SECRET_KEY", "change-me-in-production")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
PORT = int(os.getenv("PORT", 5000))

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_PATH = os.getenv("DATABASE_PATH", "data/predictions.db")

# ── AI Model API Keys ─────────────────────────────────────────────────────────
ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY", "")        # Claude
OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY", "")           # ChatGPT
GOOGLE_API_KEY      = os.getenv("GOOGLE_API_KEY", "")           # Gemini
XAI_API_KEY         = os.getenv("XAI_API_KEY", "")              # Grok

# Azure OpenAI (for future Copilot / GPT-4o via Azure)
AZURE_OPENAI_KEY      = os.getenv("AZURE_OPENAI_KEY", "")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_DEPLOY   = os.getenv("AZURE_OPENAI_DEPLOY", "gpt-4o")

# ── Model version overrides (change without redeploying) ──────────────────────
CLAUDE_MODEL  = os.getenv("CLAUDE_MODEL",  "claude-opus-4-6")
CHATGPT_MODEL = os.getenv("CHATGPT_MODEL", "gpt-4o")
GROK_MODEL    = os.getenv("GROK_MODEL",    "grok-3")

# ── Market context ───────────────────────────────────────────────────────────
NEWS_API_KEY     = os.getenv("NEWS_API_KEY",     "")  # newsapi.org — free, 100 req/day
FINNHUB_API_KEY  = os.getenv("FINNHUB_API_KEY",  "")  # finnhub.io  — free, 60 req/min (no card)

# ── Email (Resend) ────────────────────────────────────────────────────────────
RESEND_API_KEY  = os.getenv("RESEND_API_KEY", "")
EMAIL_RECIPIENT = os.getenv("EMAIL_RECIPIENT", "pranav.akshat.2@gmail.com")
EMAIL_FROM      = os.getenv("EMAIL_FROM", "AI Stock Analyst <onboarding@resend.dev>")

# ── Scheduler ─────────────────────────────────────────────────────────────────
MORNING_HOUR   = int(os.getenv("MORNING_HOUR", 5))    # 5 AM  – query models + send email
MORNING_MINUTE = int(os.getenv("MORNING_MINUTE", 0))
EVENING_HOUR   = int(os.getenv("EVENING_HOUR", 18))   # 6 PM  – fetch results + score accuracy
EVENING_MINUTE = int(os.getenv("EVENING_MINUTE", 0))
TIMEZONE       = os.getenv("TIMEZONE", "America/New_York")

# ── Dashboard ─────────────────────────────────────────────────────────────────
# Set DASHBOARD_URL in Railway to your deployed app URL (e.g. https://your-app.up.railway.app)
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "")

# ── Portfolio ─────────────────────────────────────────────────────────────────
STARTING_PORTFOLIO_VALUE = float(os.getenv("STARTING_PORTFOLIO_VALUE", 10000))
# Per-trade regulatory fee (SEC + FINRA TAF, sell-side only, ~0.03%)
# Robinhood charges $0 commission for US equities; this covers regulatory fees.
TRADE_FEE_PCT = float(os.getenv("TRADE_FEE_PCT", 0.0003))

# ── Model Metadata ────────────────────────────────────────────────────────────
MODELS = {
    "claude":   {"display": "Claude (Anthropic)",  "color": "#d97706"},
    "chatgpt":  {"display": "ChatGPT (OpenAI)",    "color": "#10a37f"},
    "grok":     {"display": "Grok (xAI)",          "color": "#1da1f2"},
    "gemini":   {"display": "Gemini (Google)",     "color": "#4285f4"},
}
