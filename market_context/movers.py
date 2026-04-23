"""
market_context/movers.py — Identify the biggest stock movers from the previous session.

Uses yfinance bulk download (single fast call) on a curated watchlist of ~60
liquid, high-volume names across all sectors. No API key required.
"""

import logging
import yfinance as yf

logger = logging.getLogger(__name__)

# Curated watchlist: liquid names across sectors, including mid-caps
WATCHLIST = [
    # Mega-cap tech
    "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA", "AVGO",
    # Mid/large tech & semis
    "AMD", "QCOM", "INTC", "CRM", "ORCL", "NFLX", "SNAP", "UBER",
    "PLTR", "MSTR", "ARM", "SMCI",
    # Financials
    "JPM", "BAC", "GS", "MS", "C", "WFC", "COIN",
    # Healthcare / biotech
    "LLY", "PFE", "MRNA", "ABBV", "JNJ", "BIIB",
    # Energy
    "XOM", "CVX", "OXY", "SLB",
    # Consumer
    "WMT", "COST", "MCD", "NKE", "SBUX",
    # Industrial / macro
    "BA", "CAT", "GE", "F", "GM",
    # ETFs (useful for sector signals)
    "SPY", "QQQ", "IWM", "GLD", "USO",
]


def get_movers(top_n: int = 6) -> str:
    """
    Returns a plain-text block listing the biggest gainers and losers
    from the most recent trading session.
    """
    try:
        data = yf.download(
            WATCHLIST,
            period="5d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )

        close = data["Close"].dropna(how="all")
        if len(close) < 2:
            return ""

        prev = close.iloc[-2]
        last = close.iloc[-1]
        pct  = ((last - prev) / prev * 100).dropna().round(2)

        # Remove ETFs from the mover display (keep them for context only)
        etfs = {"SPY", "QQQ", "IWM", "GLD", "USO"}
        pct  = pct[~pct.index.isin(etfs)]

        gainers = pct.nlargest(top_n)
        losers  = pct.nsmallest(top_n)

        g_str = "  " + ",  ".join(f"{t} +{v:.1f}%" for t, v in gainers.items())
        l_str = "  " + ",  ".join(f"{t} {v:.1f}%"  for t, v in losers.items())

        return f"BIGGEST MOVERS (prev session):\n  Top Gainers:\n{g_str}\n  Top Losers:\n{l_str}"

    except Exception as exc:
        logger.warning("movers fetch failed: %s", exc)
        return ""
