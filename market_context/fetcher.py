"""
market_context/fetcher.py — Fetch real-time market data to inject into model prompts.

Uses yfinance (already a dependency) + the free alternative.me Fear & Greed API.
No additional API keys required.
"""

import logging
from datetime import date

import requests
import yfinance as yf

logger = logging.getLogger(__name__)

# ── Tickers to track ──────────────────────────────────────────────────────────

INDICES = {
    "S&P 500":      "SPY",
    "Nasdaq 100":   "QQQ",
    "Dow Jones":    "DIA",
    "Small Caps":   "IWM",   # Russell 2000 — key for finding mid/small-cap plays
    "VIX":          "^VIX",
}

SECTORS = {
    "Technology":       "XLK",
    "Energy":           "XLE",
    "Financials":       "XLF",
    "Healthcare":       "XLV",
    "Consumer Disc.":   "XLY",
    "Industrials":      "XLI",
    "Materials":        "XLB",
    "Comm. Services":   "XLC",
    "Consumer Staples": "XLP",
    "Utilities":        "XLU",
    "Real Estate":      "XLRE",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pct_change(ticker: str) -> float | None:
    """Return the most recent session's % change for a ticker."""
    try:
        hist = yf.Ticker(ticker).history(period="5d")
        if len(hist) < 2:
            return None
        prev  = hist["Close"].iloc[-2]
        last  = hist["Close"].iloc[-1]
        return round((last - prev) / prev * 100, 2)
    except Exception as exc:
        logger.warning("yfinance error for %s: %s", ticker, exc)
        return None


def _fear_greed() -> str:
    """Fetch CNN Fear & Greed index via the free alternative.me API."""
    try:
        r    = requests.get("https://api.alternative.me/fng/?limit=1", timeout=6)
        data = r.json()["data"][0]
        return f"{data['value']}/100 — {data['value_classification']}"
    except Exception:
        return "unavailable"


# ── Main builder ──────────────────────────────────────────────────────────────

def build_market_context() -> str:
    """
    Returns a plain-text summary of current market conditions.
    Injected into every model's user prompt so picks are grounded in reality.
    """
    today = date.today().strftime("%A, %B %d, %Y")
    lines = [
        f"=== LIVE MARKET CONTEXT: {today} ===",
        "",
    ]

    # ── Indices ───────────────────────────────────────────────────────────────
    lines.append("MAJOR INDICES (most recent session % change):")
    for name, ticker in INDICES.items():
        chg = _pct_change(ticker)
        if chg is not None:
            arrow = "+" if chg >= 0 else ""
            lines.append(f"  {name:<18} {arrow}{chg:.2f}%")
    lines.append("")

    # ── Sectors ranked best → worst ───────────────────────────────────────────
    lines.append("SECTOR PERFORMANCE (best to worst):")
    sector_results = []
    for name, ticker in SECTORS.items():
        chg = _pct_change(ticker)
        if chg is not None:
            sector_results.append((name, chg))

    sector_results.sort(key=lambda x: x[1], reverse=True)
    for name, chg in sector_results:
        bar   = "▲" if chg >= 0 else "▼"
        arrow = "+" if chg >= 0 else ""
        lines.append(f"  {bar} {name:<20} {arrow}{chg:.2f}%")
    lines.append("")

    # ── Sentiment ─────────────────────────────────────────────────────────────
    lines.append(f"FEAR & GREED INDEX: {_fear_greed()}")
    lines.append("")
    lines.append("=== END MARKET CONTEXT ===")

    result = "\n".join(lines)
    logger.info("Market context built (%d chars)", len(result))
    return result
