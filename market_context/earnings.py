"""
market_context/earnings.py — Fetch today's and this week's earnings calendar.

Uses the public NASDAQ earnings calendar API — no API key required.
Falls back gracefully to empty string on any failure.
"""

import logging
from datetime import date, timedelta

import requests

logger = logging.getLogger(__name__)

NASDAQ_URL = "https://api.nasdaq.com/api/calendar/earnings"
HEADERS    = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nasdaq.com/",
}


def _fetch_day(iso_date: str) -> list[dict]:
    """Fetch earnings rows for one date. Returns [] on any error."""
    try:
        r = requests.get(
            NASDAQ_URL,
            params={"date": iso_date},
            headers=HEADERS,
            timeout=8,
        )
        rows = r.json().get("data", {}).get("rows") or []
        return rows
    except Exception as exc:
        logger.warning("Earnings fetch failed for %s: %s", iso_date, exc)
        return []


def _fmt_row(row: dict) -> str:
    ticker = row.get("symbol", "?")
    name   = row.get("name", "")
    # Shorten name to keep context tight
    name   = name[:28] + "…" if len(name) > 28 else name
    time   = row.get("time", "")
    tag    = "BMO" if "pre" in time.lower() else "AMC" if "after" in time.lower() else "   "
    return f"{ticker:<8} {tag}  {name}"


def get_earnings_context() -> str:
    """
    Returns a plain-text block covering today's and the next 4 trading days.
    BMO = Before Market Open, AMC = After Market Close.
    """
    today = date.today()
    lines = []

    for offset in range(5):
        day     = today + timedelta(days=offset)
        # Skip weekends
        if day.weekday() >= 5:
            continue

        rows = _fetch_day(day.isoformat())
        if not rows:
            continue

        label  = "TODAY" if offset == 0 else day.strftime("%a %b %d")
        # Cap to top 12 names per day to keep context tight
        sample = rows[:12]
        block  = [f"  {_fmt_row(r)}" for r in sample]
        extra  = len(rows) - len(sample)
        if extra > 0:
            block.append(f"  … and {extra} more")

        lines.append(f"{label}:")
        lines.extend(block)
        lines.append("")

    if not lines:
        return ""

    return "EARNINGS CALENDAR:\n" + "\n".join(lines)
