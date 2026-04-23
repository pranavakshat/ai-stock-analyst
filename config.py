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

# ── Email (Gmail SMTP) ────────────────────────────────────────────────────────
GMAIL_ADDRESS  = os.getenv("GMAIL_ADDRESS", "")      # sender Gmail address
GMAIL_APP_PASS = os.getenv("GMAIL_APP_PASS", "")     # 16-char App Password (not your login password)
EMAIL_RECIPIENT = os.getenv("EMAIL_RECIPIENT", "pranav.akshat.2@gmail.com")

# ── Scheduler ─────────────────────────────────────────────────────────────────
MORNING_HOUR   = int(os.getenv("MORNING_HOUR", 5))    # 5 AM  – query models + send email
MORNING_MINUTE = int(os.getenv("MORNING_MINUTE", 0))
EVENING_HOUR   = int(os.getenv("EVENING_HOUR", 18))   # 6 PM  – fetch results + score accuracy
EVENING_MINUTE = int(os.getenv("EVENING_MINUTE", 0))
TIMEZONE       = os.getenv("TIMEZONE", "America/New_York")

# ── Portfolio ─────────────────────────────────────────────────────────────────
STARTING_PORTFOLIO_VALUE = float(os.getenv("STARTING_PORTFOLIO_VALUE", 10000))

# ── Model Metadata ────────────────────────────────────────────────────────────
MODELS = {
    "claude":   {"display": "Claude (Anthropic)",  "color": "#d97706"},
    "chatgpt":  {"display": "ChatGPT (OpenAI)",    "color": "#10a37f"},
    "grok":     {"display": "Grok (xAI)",          "color": "#1da1f2"},
    "gemini":   {"display": "Gemini (Google)",     "color": "#4285f4"},
}
