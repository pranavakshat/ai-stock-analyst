"""
market_context/macro.py — Macro indicators: yields, crypto, commodities, economic calendar.

All free, all via yfinance or the public Forex Factory calendar API. No keys required.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import requests
import yfinance as yf

logger = logging.getLogger(__name__)

# ── Tickers ───────────────────────────────────────────────────────────────────

MACRO_TICKERS = {
    # Treasury yields
    "10Y Yield":     "^TNX",
    "30Y Yield":     "^TYX",
    # Crypto (risk-on/off signal)
    "Bitcoin":       "BTC-USD",
    "Ethereum":      "ETH-USD",
    # Commodities
    "Gold":          "GC=F",
    "Crude Oil":     "CL=F",
    # Dollar strength
    "USD Index":     "DX-Y.NYB",
}

YIELD_TICKERS = {"^TNX", "^TYX"}          # display as percentage points
PRICE_PREFIXES = {
    "BTC-USD":    "$",
    "ETH-USD":    "$",
    "GC=F":       "$",
    "CL=F":       "$",
    "DX-Y.NYB":   "",
}


def _fetch_one(name: str, ticker: str) -> dict | None:
    try:
        hist = yf.Ticker(ticker).history(period="5d")
        if len(hist) < 2:
            return None
        prev  = hist["Close"].iloc[-2]
        last  = hist["Close"].iloc[-1]
        chg   = last - prev
        chg_p = (chg / prev * 100) if prev else 0
        return {
            "name":    name,
            "ticker":  ticker,
            "last":    round(float(last), 2),
            "chg":     round(float(chg), 4),
            "chg_pct": round(float(chg_p), 2),
        }
    except Exception as exc:
        logger.warning("macro fetch failed %s: %s", ticker, exc)
        return None


def get_macro_indicators() -> str:
    """Returns a formatted block of macro market indicators."""
    results = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(_fetch_one, name, ticker): (name, ticker)
            for name, ticker in MACRO_TICKERS.items()
        }
        for future in as_completed(futures):
            data = future.result()
            if data:
                results[data["name"]] = data

    if not results:
        return ""

    lines = ["MACRO INDICATORS:"]
    for name, ticker in MACRO_TICKERS.items():
        d = results.get(name)
        if not d:
            continue
        sign   = "+" if d["chg_pct"] >= 0 else ""
        prefix = PRICE_PREFIXES.get(d["ticker"], "")
        if d["ticker"] in YIELD_TICKERS:
            # Yields: show as "4.42% (+0.03)"
            lines.append(f"  {name:<22} {d['last']:.2f}%  ({sign}{d['chg']:.2f})")
        elif d["last"] > 1000:
            lines.append(f"  {name:<22} {prefix}{d['last']:,.0f}  ({sign}{d['chg_pct']:.1f}%)")
        else:
            lines.append(f"  {name:<22} {prefix}{d['last']:.2f}  ({sign}{d['chg_pct']:.1f}%)")

    return "\n".join(lines)


# ── Economic calendar ─────────────────────────────────────────────────────────

CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"


def get_economic_calendar() -> str:
    """
    Fetch this week's high-impact USD economic events from Forex Factory.
    No API key required.
    """
    try:
        r     = requests.get(CALENDAR_URL, timeout=8)
        events = r.json()
    except Exception as exc:
        logger.warning("Economic calendar fetch failed: %s", exc)
        return ""

    # Filter: USD only, High impact only
    high_impact = [
        e for e in events
        if e.get("country", "").upper() == "USD"
        and e.get("impact", "").lower() == "high"
    ]

    if not high_impact:
        return ""

    lines = ["ECONOMIC EVENTS THIS WEEK (High Impact USD):"]
    for e in high_impact[:8]:
        try:
            dt    = datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
            label = dt.astimezone().strftime("%a %b %d, %-I:%M %p")
        except Exception:
            label = e.get("date", "")[:10]
        title = e.get("title", "")
        fore  = e.get("forecast", "")
        prev  = e.get("previous", "")
        suffix = ""
        if fore:
            suffix += f"  Forecast: {fore}"
        if prev:
            suffix += f"  Prev: {prev}"
        lines.append(f"  {label:<24} {title}{suffix}")

    return "\n".join(lines)
