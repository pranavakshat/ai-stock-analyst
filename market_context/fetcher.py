"""
market_context/fetcher.py — Assemble the full live market context string.

All 7 modules run concurrently. Each fails gracefully — a bad network call
just omits that section. Total latency ≈ slowest single module (~5-8s).

Modules                     Key needed?   Source
──────────────────────────────────────────────────────────────────
1. Indices & sectors         No            yfinance
2. Fear & Greed              No            alternative.me
3. Pre-session movers        No            yfinance (bulk download)
4. Macro (yields/crypto/     No            yfinance + Forex Factory
   commodities/econ cal)
5. Earnings calendar         No            NASDAQ public API
6. Analyst actions           No            yfinance
7. Market news headlines     Yes (free)    NewsAPI (newsapi.org)
8. Reddit sentiment          No            Reddit public JSON API
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import requests
import yfinance as yf

from market_context.movers   import get_movers
from market_context.earnings import get_earnings_context
from market_context.news     import get_news_context
from market_context.macro    import get_macro_indicators, get_economic_calendar
from market_context.analyst  import get_analyst_actions
from market_context.reddit   import get_reddit_sentiment

logger = logging.getLogger(__name__)

# ── Indices & sectors ─────────────────────────────────────────────────────────

INDICES = {
    "S&P 500":    "SPY",
    "Nasdaq 100": "QQQ",
    "Dow Jones":  "DIA",
    "Small Caps": "IWM",
    "VIX":        "^VIX",
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


def _pct_change(ticker: str) -> float | None:
    try:
        hist = yf.Ticker(ticker).history(period="5d")
        if len(hist) < 2:
            return None
        prev = hist["Close"].iloc[-2]
        last = hist["Close"].iloc[-1]
        return round((last - prev) / prev * 100, 2)
    except Exception as exc:
        logger.warning("yfinance error for %s: %s", ticker, exc)
        return None


def _fear_greed() -> str:
    try:
        r    = requests.get("https://api.alternative.me/fng/?limit=1", timeout=6)
        data = r.json()["data"][0]
        return f"{data['value']}/100 — {data['value_classification']}"
    except Exception:
        return "unavailable"


def _build_indices_sectors() -> str:
    lines = ["MAJOR INDICES (prev session):"]
    for name, ticker in INDICES.items():
        chg = _pct_change(ticker)
        if chg is not None:
            sign = "+" if chg >= 0 else ""
            lines.append(f"  {name:<18} {sign}{chg:.2f}%")
    lines.append("")
    lines.append("SECTOR PERFORMANCE (best → worst):")
    results = []
    for name, ticker in SECTORS.items():
        chg = _pct_change(ticker)
        if chg is not None:
            results.append((name, chg))
    results.sort(key=lambda x: x[1], reverse=True)
    for name, chg in results:
        bar  = "▲" if chg >= 0 else "▼"
        sign = "+" if chg >= 0 else ""
        lines.append(f"  {bar} {name:<20} {sign}{chg:.2f}%")
    lines.append("")
    lines.append(f"FEAR & GREED INDEX: {_fear_greed()}")
    return "\n".join(lines)


# ── Main builder ──────────────────────────────────────────────────────────────

# Ordered display sequence + labels
MODULE_ORDER = [
    ("indices",   None),
    ("movers",    None),
    ("macro",     None),
    ("econ_cal",  None),
    ("earnings",  None),
    ("analyst",   None),
    ("news",      None),
    ("reddit",    None),
]


def build_market_context() -> str:
    """
    Runs all 8 data modules concurrently and assembles the full context string.
    Typical runtime: 5-10 seconds (bounded by the slowest module).
    """
    today = date.today().strftime("%A, %B %d, %Y")

    tasks = {
        "indices":  _build_indices_sectors,
        "movers":   get_movers,
        "macro":    get_macro_indicators,
        "econ_cal": get_economic_calendar,
        "earnings": get_earnings_context,
        "analyst":  get_analyst_actions,
        "news":     get_news_context,
        "reddit":   get_reddit_sentiment,
    }

    results: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(fn): key for key, fn in tasks.items()}
        for future in as_completed(futures, timeout=60):
            key = futures[future]
            try:
                results[key] = future.result(timeout=15) or ""
            except TimeoutError:
                logger.warning("Context module '%s' timed out — skipping", key)
                results[key] = ""
            except Exception as exc:
                logger.warning("Context module '%s' failed: %s", key, exc)
                results[key] = ""

    # Assemble in logical reading order
    sections = [f"=== LIVE MARKET CONTEXT: {today} ===", ""]

    for key in ("indices", "movers", "macro", "econ_cal",
                "earnings", "analyst", "news", "reddit"):
        block = results.get(key, "").strip()
        if block:
            sections.append(block)
            sections.append("")

    sections.append("=== END MARKET CONTEXT ===")

    context     = "\n".join(sections)
    active_mods = sum(1 for k in tasks if results.get(k, "").strip())
    logger.info("Market context built: %d chars, %d/%d modules active",
                len(context), active_mods, len(tasks))
    return context
