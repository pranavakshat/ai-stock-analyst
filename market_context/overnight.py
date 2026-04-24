"""
market_context/overnight.py — Overnight-specific market context.

What professional portfolio managers watch for overnight holds:
  1. US equity futures (ES, NQ, YM, RTY) — directional bias after close
  2. Asian market open/performance — first global signal of risk appetite
  3. After-hours movers — stocks already reacting to AMC news/earnings
  4. Treasury yields (2Y, 10Y, 30Y) — risk-off/on signals, Fed sensitivity
  5. Dollar index — strength signals macro risk tone
  6. AMC earnings tonight — direct overnight catalysts
  7. BMO earnings tomorrow — gap-at-open setups
  8. VIX level — overnight volatility expectation

All data is free via yfinance. No additional API keys required.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import yfinance as yf

logger = logging.getLogger(__name__)

# ── US Equity Futures ─────────────────────────────────────────────────────────

US_FUTURES = {
    "S&P 500 Futures":    "ES=F",
    "Nasdaq 100 Futures": "NQ=F",
    "Dow Futures":        "YM=F",
    "Russell 2000 Fut.":  "RTY=F",
}

# ── Asian & European indices ──────────────────────────────────────────────────

OVERNIGHT_INDICES = {
    "Nikkei 225 (Japan)":  "^N225",
    "Hang Seng (HK)":      "^HSI",
    "ASX 200 (Australia)": "^AXJO",
    "KOSPI (South Korea)": "^KS11",
    "FTSE 100 (UK)":       "^FTSE",
    "DAX (Germany)":       "^GDAXI",
}

# ── Extended macro (overnight lens) ──────────────────────────────────────────

OVERNIGHT_MACRO = {
    "2Y Treasury Yield":  "^IRX",   # Short-end (Fed expectations)
    "10Y Treasury Yield": "^TNX",
    "30Y Treasury Yield": "^TYX",
    "USD Index":          "DX-Y.NYB",
    "Gold (GC=F)":        "GC=F",
    "Crude Oil (CL=F)":   "CL=F",
    "Bitcoin":            "BTC-USD",  # 24/7 risk barometer
    "VIX":                "^VIX",
}

# ── After-hours watchlist ─────────────────────────────────────────────────────
# Liquid names where after-hours moves signal broader risk tone

AH_WATCHLIST = [
    # Mega-cap bellwethers (their AH moves set the tone)
    "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA",
    # High-beta movers
    "AMD", "PLTR", "COIN", "MSTR", "SMCI", "ARM",
    # Financials
    "JPM", "GS", "BAC",
    # Industrials/energy
    "XOM", "CVX",
]


def _fetch_single(name: str, ticker: str) -> dict | None:
    """Fetch latest price + day change for one ticker."""
    try:
        hist = yf.Ticker(ticker).history(period="5d")
        if len(hist) < 2:
            return None
        prev  = float(hist["Close"].iloc[-2])
        last  = float(hist["Close"].iloc[-1])
        chg_p = (last - prev) / prev * 100 if prev else 0
        return {"name": name, "ticker": ticker, "last": last,
                "chg_pct": round(chg_p, 2)}
    except Exception as exc:
        logger.debug("overnight fetch failed %s: %s", ticker, exc)
        return None


def _get_futures_block() -> str:
    """US equity futures — direction of overnight session."""
    results = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(_fetch_single, n, t): n for n, t in US_FUTURES.items()}
        for f in as_completed(futs):
            d = f.result()
            if d:
                results[d["name"]] = d

    if not results:
        return ""

    lines = ["US EQUITY FUTURES (current):"]
    for name in US_FUTURES:
        d = results.get(name)
        if not d:
            continue
        arrow = "▲" if d["chg_pct"] >= 0 else "▼"
        sign  = "+" if d["chg_pct"] >= 0 else ""
        lines.append(f"  {arrow} {name:<26} {sign}{d['chg_pct']:.2f}%")
    return "\n".join(lines)


def _get_asian_european_block() -> str:
    """Asian & European indices — first overnight global signal."""
    results = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = {pool.submit(_fetch_single, n, t): n for n, t in OVERNIGHT_INDICES.items()}
        for f in as_completed(futs):
            d = f.result()
            if d:
                results[d["name"]] = d

    if not results:
        return ""

    lines = ["GLOBAL MARKETS (overnight session):"]
    for name in OVERNIGHT_INDICES:
        d = results.get(name)
        if not d:
            continue
        arrow = "▲" if d["chg_pct"] >= 0 else "▼"
        sign  = "+" if d["chg_pct"] >= 0 else ""
        lines.append(f"  {arrow} {name:<28} {sign}{d['chg_pct']:.2f}%")
    return "\n".join(lines)


def _get_overnight_macro_block() -> str:
    """Yields, dollar, commodities, VIX — overnight risk tone."""
    results = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(_fetch_single, n, t): n for n, t in OVERNIGHT_MACRO.items()}
        for f in as_completed(futs):
            d = f.result()
            if d:
                results[d["name"]] = d

    if not results:
        return ""

    lines = ["OVERNIGHT MACRO SIGNALS:"]
    yield_tickers = {"^IRX", "^TNX", "^TYX"}
    for name, ticker in OVERNIGHT_MACRO.items():
        d = results.get(name)
        if not d:
            continue
        sign  = "+" if d["chg_pct"] >= 0 else ""
        arrow = "▲" if d["chg_pct"] >= 0 else "▼"
        if ticker in yield_tickers:
            lines.append(f"  {arrow} {name:<26} {d['last']:.2f}%  ({sign}{d['chg_pct']:.2f}%)")
        elif d["last"] > 10000:
            lines.append(f"  {arrow} {name:<26} ${d['last']:,.0f}  ({sign}{d['chg_pct']:.1f}%)")
        else:
            lines.append(f"  {arrow} {name:<26} {d['last']:.2f}  ({sign}{d['chg_pct']:.1f}%)")
    return "\n".join(lines)


def _get_afterhours_movers_block() -> str:
    """
    Stocks moving significantly in after-hours.
    Uses postMarketPrice vs regularMarketPrice from yfinance .info.
    Only reports moves >= 1.5% to cut noise.
    """
    movers = []

    def _check(ticker: str):
        try:
            info = yf.Ticker(ticker).info
            reg  = info.get("regularMarketPrice") or info.get("currentPrice")
            post = info.get("postMarketPrice")
            if reg and post and reg > 0:
                chg = (post - reg) / reg * 100
                if abs(chg) >= 1.5:
                    return ticker, round(chg, 2), round(post, 2)
        except Exception:
            pass
        return None

    with ThreadPoolExecutor(max_workers=10) as pool:
        futs = [pool.submit(_check, t) for t in AH_WATCHLIST]
        for f in as_completed(futs):
            r = f.result()
            if r:
                movers.append(r)

    if not movers:
        return "AFTER-HOURS MOVERS: No significant moves (>±1.5%) detected"

    movers.sort(key=lambda x: abs(x[1]), reverse=True)
    lines = ["AFTER-HOURS MOVERS (>±1.5%):"]
    for ticker, chg, price in movers[:10]:
        arrow = "▲" if chg >= 0 else "▼"
        sign  = "+" if chg >= 0 else ""
        lines.append(f"  {arrow} {ticker:<8} ${price:.2f}  ({sign}{chg:.1f}% after-hours)")
    return "\n".join(lines)


def _get_earnings_overnight() -> str:
    """
    Full earnings context for overnight context:
      - Upcoming earnings next 7 trading days (any AMC/BMO, any day — not just tomorrow)
      - Recent earnings reactions from past 7 days
    """
    try:
        from market_context.earnings import get_earnings_context
        return get_earnings_context()
    except Exception as exc:
        logger.warning("overnight earnings fetch failed: %s", exc)
        return ""


# ── Main builder ──────────────────────────────────────────────────────────────

def build_overnight_context() -> str:
    """
    Assembles the full overnight market context string concurrently.
    Typical runtime: 5-10 seconds.
    """
    today = date.today().strftime("%A, %B %d, %Y")

    from market_context.technicals    import get_technicals_context
    from market_context.options       import get_options_context
    from market_context.short_interest import get_short_interest_context
    from market_context.finnhub_context import get_finnhub_context

    tasks = {
        "futures":    _get_futures_block,
        "global":     _get_asian_european_block,
        "macro":      _get_overnight_macro_block,
        "ah":         _get_afterhours_movers_block,
        "earnings":   _get_earnings_overnight,
        "technicals": get_technicals_context,
        "options":    get_options_context,
        "short":      get_short_interest_context,
        "finnhub":    get_finnhub_context,
    }

    results: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=9) as pool:
        futs = {pool.submit(fn): key for key, fn in tasks.items()}
        for f in as_completed(futs, timeout=55):
            key = futs[f]
            try:
                results[key] = f.result(timeout=15) or ""
            except Exception as exc:
                logger.warning("Overnight context module '%s' failed: %s", key, exc)
                results[key] = ""

    sections = [f"=== OVERNIGHT MARKET CONTEXT: {today} ===", ""]
    for key in ("futures", "global", "macro", "ah", "earnings",
                "technicals", "options", "short", "finnhub"):
        block = results.get(key, "").strip()
        if block:
            sections.append(block)
            sections.append("")
    sections.append("=== END OVERNIGHT CONTEXT ===")

    context = "\n".join(sections)
    logger.info("Overnight context built: %d chars", len(context))
    return context
