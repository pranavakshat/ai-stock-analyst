"""
market_context/short_interest.py — Short interest and squeeze candidate signals.

Data source: yfinance .info (delayed ~2 weeks from FINRA reports, but free).

Two signals:
  1. HIGH SHORT FLOAT   — stocks with >10% of float short (squeeze fuel)
  2. SHORT RATIO (DTC)  — days-to-cover; >5 days = significant squeeze risk

Combined with recent price momentum (from technicals), high short interest
+ positive catalyst = classic squeeze setup.  All of this is explicit context
for models to reason about.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import yfinance as yf

logger = logging.getLogger(__name__)

# Focus on names known to carry elevated short interest
SHORT_WATCHLIST = [
    # Meme/speculative
    "GME", "AMC", "BBBY",
    # High-beta tech that gets shorted heavily
    "MSTR", "PLTR", "COIN", "LCID", "RIVN", "SMCI", "ARM",
    # EV / clean energy (historically shorted)
    "NIO", "XPEV", "NKLA", "WKHS",
    # Fintech / consumer
    "HOOD", "SOFI", "UPST", "OPEN", "RBLX", "U",
    # Growth names with high shorts
    "TSLA", "NVDA", "AMD",
    # Biotech (short squeeze common post-trial)
    "MRNA", "BNTX", "SAVA",
]


def _fetch_short_info(ticker: str) -> dict | None:
    try:
        info = yf.Ticker(ticker).info

        short_pct   = info.get("shortPercentOfFloat")
        short_ratio = info.get("shortRatio")       # days-to-cover
        shares_short = info.get("sharesShort")
        float_shares = info.get("floatShares")
        name         = info.get("shortName", ticker)

        if short_pct is None:
            return None

        # yfinance sometimes returns as fraction (0.15) sometimes as percent (15.0)
        if isinstance(short_pct, float) and short_pct <= 1.0:
            short_pct = round(short_pct * 100, 1)
        else:
            short_pct = round(float(short_pct), 1)

        return {
            "ticker":       ticker,
            "name":         name[:30],
            "short_pct":    short_pct,
            "short_ratio":  round(float(short_ratio), 1) if short_ratio else None,
            "shares_short": shares_short,
            "float_shares": float_shares,
        }
    except Exception as exc:
        logger.debug("short_interest failed for %s: %s", ticker, exc)
        return None


def get_short_interest_context() -> str:
    """
    Returns a block listing the most heavily shorted stocks in the watchlist.
    Only includes names with ≥10% short float to keep the signal meaningful.
    """
    results: list[dict] = []

    with ThreadPoolExecutor(max_workers=12) as pool:
        futs = [pool.submit(_fetch_short_info, t) for t in SHORT_WATCHLIST]
        for f in as_completed(futs, timeout=35):
            try:
                r = f.result(timeout=12)
                if r and r["short_pct"] >= 10.0:
                    results.append(r)
            except Exception:
                pass

    if not results:
        return ""

    results.sort(key=lambda x: x["short_pct"], reverse=True)

    lines = ["SHORT INTEREST — High-Float-Short Stocks (≥10% of float short):"]
    lines.append(
        "  (High short % + upcoming catalyst = potential squeeze risk. "
        "Conversely: negative catalyst → accelerated drop.)"
    )

    for r in results[:12]:
        dtc  = f"  DTC={r['short_ratio']}d" if r.get("short_ratio") else ""
        name = r.get("name", "")
        lines.append(f"  {r['ticker']:<8}  {r['short_pct']:.1f}% short{dtc}  ({name})")

    return "\n".join(lines)
