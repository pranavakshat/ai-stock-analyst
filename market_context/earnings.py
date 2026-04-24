"""
market_context/earnings.py — Earnings calendar context for AI stock models.

Two sections injected into every model prompt:

1. UPCOMING EARNINGS (next 7 trading days)
   — Full calendar with AMC / BMO tags so models can pre-position.
   — Not limited to "tomorrow" — if a major report is Thursday, the model
     should know on Monday.

2. RECENT EARNINGS REACTIONS (past 7 trading days)
   — Stocks that just reported + their 1-day price move.
   — Helps models identify post-earnings momentum plays (beat & run,
     miss & rebound, etc.).

Data source: NASDAQ public earnings calendar API (no key required).
Price reactions: yfinance (concurrent per-ticker history calls).
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

import requests
import yfinance as yf

logger = logging.getLogger(__name__)

NASDAQ_URL = "https://api.nasdaq.com/api/calendar/earnings"
HEADERS    = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.nasdaq.com/",
}


# ── NASDAQ calendar fetch ──────────────────────────────────────────────────────

def _fetch_day(iso_date: str) -> list[dict]:
    """Fetch earnings rows for one date from NASDAQ. Returns [] on any error."""
    try:
        r    = requests.get(NASDAQ_URL, params={"date": iso_date},
                            headers=HEADERS, timeout=8)
        rows = r.json().get("data", {}).get("rows") or []
        return rows
    except Exception as exc:
        logger.warning("Earnings fetch failed for %s: %s", iso_date, exc)
        return []


def _timing_tag(row: dict) -> str:
    """Return 'BMO', 'AMC', or '   ' based on the time field."""
    t = (row.get("time") or "").lower()
    if "pre" in t:
        return "BMO"
    if "after" in t:
        return "AMC"
    return "   "


def _fmt_row(row: dict, reaction: float | None = None) -> str:
    """Format one earnings row as a single line."""
    ticker = row.get("symbol", "?")
    name   = row.get("name", "")
    name   = (name[:26] + "…") if len(name) > 27 else name
    tag    = _timing_tag(row)

    if reaction is not None:
        arrow = "▲" if reaction >= 0 else "▼"
        sign  = "+" if reaction >= 0 else ""
        return f"{ticker:<8} {tag}  {name:<27}  {arrow}{sign}{reaction:.1f}%"
    return f"{ticker:<8} {tag}  {name}"


# ── Price-reaction helper ──────────────────────────────────────────────────────

def _reaction_pct(ticker: str, earnings_date: date) -> float | None:
    """
    1-day close-to-close price reaction around earnings_date.

    For AMC reports: close(earnings_date - 1) → close(earnings_date + 1)
    For BMO reports: close(earnings_date - 1) → close(earnings_date)

    We use close-to-close because it's clean and available.  The exact
    entry/exit timing tag (AMC vs BMO) isn't stored here, so we just use
    the nearest available trading-day pair around the event date.
    """
    try:
        start = (earnings_date - timedelta(days=6)).isoformat()
        end   = (earnings_date + timedelta(days=4)).isoformat()
        hist  = yf.Ticker(ticker).history(start=start, end=end)
        if hist.empty or len(hist) < 2:
            return None

        # Normalise index to plain date objects
        dates  = [d.date() for d in hist.index]
        closes = list(hist["Close"])

        # Find the index of the first trading day ON OR AFTER the earnings date
        idx = next((i for i, d in enumerate(dates) if d >= earnings_date), None)
        if idx is None or idx == 0:
            return None   # no "before" row

        before = closes[idx - 1]
        after  = closes[idx]

        if not before or before <= 0:
            return None

        return round((after - before) / before * 100, 1)

    except Exception as exc:
        logger.debug("reaction_pct failed for %s on %s: %s", ticker, earnings_date, exc)
        return None


# ── Upcoming earnings (next N trading days) ───────────────────────────────────

def get_upcoming_earnings(trading_days: int = 7) -> str:
    """
    Returns a formatted block listing earnings reports for the next
    `trading_days` trading days (skips weekends).

    Each line is tagged BMO (before open) or AMC (after close) so models
    know whether to position today or wait.
    """
    today = date.today()
    lines: list[str] = []
    days_counted = 0
    offset       = 0

    while days_counted < trading_days:
        day = today + timedelta(days=offset)
        offset += 1
        if day.weekday() >= 5:    # skip Saturday / Sunday
            continue
        days_counted += 1

        rows = _fetch_day(day.isoformat())
        if not rows:
            continue

        label  = "TODAY" if day == today else day.strftime("%a %b %-d")
        sample = rows[:15]          # top 15 names per day keeps context tight
        extra  = len(rows) - len(sample)

        lines.append(f"\n  {label}:")
        for r in sample:
            lines.append(f"    {_fmt_row(r)}")
        if extra > 0:
            lines.append(f"    … and {extra} more")

    if not lines:
        return ""

    return "UPCOMING EARNINGS (next 7 trading days):\n" + "\n".join(lines)


# ── Recent earnings + reactions (past N days) ─────────────────────────────────

def get_recent_earnings_reactions(days_back: int = 7) -> str:
    """
    Returns earnings that occurred in the past `days_back` calendar days
    together with the 1-day price reaction.

    Reactions are fetched concurrently (one yfinance call per ticker).
    Caps at 12 names per trading day to limit API traffic.
    """
    today    = date.today()
    calendar: list[tuple[date, dict]] = []   # (earnings_date, row)

    for offset in range(1, days_back + 1):
        day = today - timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        rows = _fetch_day(day.isoformat())
        for r in rows[:12]:
            if r.get("symbol"):
                calendar.append((day, r))

    if not calendar:
        return ""

    # Fetch reactions concurrently
    reactions: dict[tuple[str, date], float | None] = {}

    def _fetch_reaction(ticker: str, edate: date):
        return (ticker, edate), _reaction_pct(ticker, edate)

    with ThreadPoolExecutor(max_workers=12) as pool:
        futs = {
            pool.submit(_fetch_reaction, r["symbol"], d): (r["symbol"], d)
            for d, r in calendar
        }
        for fut in as_completed(futs, timeout=30):
            try:
                key, val = fut.result(timeout=10)
                reactions[key] = val
            except Exception:
                pass

    # Format output
    lines: list[str] = []
    calendar.sort(key=lambda x: x[0], reverse=True)   # newest first
    current_day = None

    for earnings_date, row in calendar[:35]:            # hard cap at 35 rows total
        ticker   = row.get("symbol", "")
        reaction = reactions.get((ticker, earnings_date))

        if earnings_date != current_day:
            current_day = earnings_date
            lines.append(f"\n  {earnings_date.strftime('%a %b %-d')}:")

        lines.append(f"    {_fmt_row(row, reaction)}")

    if not lines:
        return ""

    return "RECENT EARNINGS REACTIONS (past 7 days):\n" + "\n".join(lines)


# ── Combined context block (used by fetcher.py and overnight.py) ──────────────

def get_earnings_context() -> str:
    """
    Returns both upcoming earnings and recent reactions as one block.
    Called by build_market_context() and build_overnight_context().
    """
    upcoming  = get_upcoming_earnings(trading_days=7)
    reactions = get_recent_earnings_reactions(days_back=7)

    parts = [p for p in (upcoming, reactions) if p]
    return "\n\n".join(parts)
