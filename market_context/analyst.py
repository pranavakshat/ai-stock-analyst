"""
market_context/analyst.py — Recent analyst upgrades and downgrades (last 48 hours).

Uses yfinance's upgrades_downgrades data. No API key required.
Checks a curated watchlist concurrently to stay fast.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# Tickers to scan — liquid names where analyst actions carry weight
SCAN_LIST = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA", "AVGO",
    "AMD", "QCOM", "NFLX", "CRM", "ORCL", "UBER", "PLTR", "ARM",
    "JPM", "BAC", "GS", "MS", "C",
    "LLY", "PFE", "MRNA", "ABBV",
    "XOM", "CVX", "OXY",
    "BA", "CAT", "GE",
    "WMT", "COST", "AMZN",
]

ACTION_LABELS = {
    "up":   "UPGRADED",
    "down": "DOWNGRADED",
    "init": "INITIATED",
    "main": "MAINTAINED",
    "reit": "REITERATED",
}


def _fetch_upgrades(ticker: str, since: date) -> list[dict]:
    try:
        t    = yf.Ticker(ticker)
        df   = t.upgrades_downgrades
        if df is None or df.empty:
            return []
        # Index is DatetimeIndex — filter to last 48h
        df   = df[df.index.date >= since]
        rows = []
        for dt, row in df.iterrows():
            action = row.get("Action", "").lower()
            if action not in ACTION_LABELS:
                continue
            rows.append({
                "ticker":    ticker,
                "date":      dt.strftime("%b %d"),
                "firm":      row.get("Firm", ""),
                "action":    ACTION_LABELS[action],
                "to_grade":  row.get("ToGrade", ""),
                "from_grade": row.get("FromGrade", ""),
            })
        return rows
    except Exception as exc:
        logger.debug("analyst fetch failed %s: %s", ticker, exc)
        return []


def get_analyst_actions() -> str:
    """
    Returns a plain-text block of recent analyst upgrades/downgrades
    across the scan list from the last 48 hours.
    """
    since = date.today() - timedelta(days=2)
    all_actions: list[dict] = []

    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = {pool.submit(_fetch_upgrades, t, since): t for t in SCAN_LIST}
        for future in as_completed(futures):
            all_actions.extend(future.result())

    # Prioritise upgrades and downgrades over initiations/maintentions
    priority_order = {"UPGRADED": 0, "DOWNGRADED": 1, "INITIATED": 2,
                      "MAINTAINED": 3, "REITERATED": 4}
    all_actions.sort(key=lambda x: priority_order.get(x["action"], 5))

    # Cap at 12 actions to keep context tight
    all_actions = all_actions[:12]

    if not all_actions:
        return ""

    lines = ["RECENT ANALYST ACTIONS (last 48 hours):"]
    for a in all_actions:
        grade_change = ""
        if a["from_grade"] and a["to_grade"]:
            grade_change = f" ({a['from_grade']} → {a['to_grade']})"
        elif a["to_grade"]:
            grade_change = f" ({a['to_grade']})"
        firm = f"[{a['firm']}] " if a["firm"] else ""
        lines.append(f"  {a['date']}  {firm}{a['ticker']} {a['action']}{grade_change}")

    return "\n".join(lines)
