"""
market_context/options.py — Options activity signals.

Two signals given to AI models:

1. CBOE Market-Wide Put/Call Ratios  (via yfinance tickers ^PCE / ^PC)
   — The equity-only ratio strips out index hedges; the most reliable
     sentiment gauge used by professional traders.

2. Per-Stock Options Skew           (yfinance option_chain)
   — For a watchlist of high-beta names, compute today's put/call volume
     and open interest ratios.  Extreme skews = strong directional bets
     by the smart-money options market.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import yfinance as yf

logger = logging.getLogger(__name__)

# ── CBOE market-wide P/C ratios (available on Yahoo Finance) ─────────────────
PC_RATIO_TICKERS = {
    "CBOE Equity P/C":  "^PCE",   # Equity-only — excludes index/hedging noise
    "CBOE Total P/C":   "^PC",    # All options including index hedges
}

# Interpretation thresholds (equity P/C most relevant for stock picks)
_PC_RANGES = [
    (0.40, "extreme greed / heavy calls — contrarian bearish signal"),
    (0.55, "greed — call-skewed market"),
    (0.70, "neutral"),
    (0.85, "mild fear — put buying picking up"),
    (1.00, "fear — elevated put demand, contrarian bullish"),
    (float("inf"), "extreme fear — heavy put buying, contrarian very bullish"),
]

# ── Per-stock watchlist (high-beta, heavily optioned names) ──────────────────
OPTIONS_WATCHLIST = [
    "SPY", "QQQ",                          # Index proxies (best P/C data)
    "NVDA", "TSLA", "AAPL", "MSFT",        # Mega-cap leaders
    "AMD", "META", "AMZN", "GOOGL",
    "PLTR", "COIN", "MSTR", "ARM", "SMCI",  # High-beta speculative
]


def _market_pc_block() -> str:
    """Fetch and interpret CBOE put/call ratios."""
    lines: list[str] = []
    for name, ticker in PC_RATIO_TICKERS.items():
        try:
            hist = yf.Ticker(ticker).history(period="5d")
            if hist.empty:
                continue
            val = float(hist["Close"].iloc[-1])

            interp = next(
                (msg for threshold, msg in _PC_RANGES if val < threshold), ""
            )
            lines.append(f"  {name:<22} {val:.2f}  — {interp}")
        except Exception as exc:
            logger.debug("P/C ratio %s failed: %s", ticker, exc)

    return ("OPTIONS SENTIMENT — CBOE Put/Call Ratios:\n" + "\n".join(lines)) if lines else ""


def _stock_options_block() -> str:
    """
    For each ticker in OPTIONS_WATCHLIST, pull the nearest expiry option chain
    and compute today's volume-based and OI-based put/call ratios.
    Highlights names with extreme directional skew.
    """
    results: list[dict] = []

    def _fetch_chain(ticker: str) -> dict | None:
        try:
            t     = yf.Ticker(ticker)
            dates = t.options
            if not dates:
                return None

            # Nearest expiry has the freshest activity data
            chain     = t.option_chain(dates[0])
            call_vol  = float(chain.calls["volume"].fillna(0).sum())
            put_vol   = float(chain.puts["volume"].fillna(0).sum())
            call_oi   = float(chain.calls["openInterest"].fillna(0).sum())
            put_oi    = float(chain.puts["openInterest"].fillna(0).sum())

            if call_vol + put_vol < 100:      # too thin — skip
                return None

            pc_vol = round(put_vol / call_vol, 2) if call_vol > 0 else None
            pc_oi  = round(put_oi  / call_oi,  2) if call_oi  > 0 else None

            return {"ticker": ticker, "pc_vol": pc_vol, "pc_oi": pc_oi,
                    "call_vol": int(call_vol), "put_vol": int(put_vol)}
        except Exception as exc:
            logger.debug("option_chain failed %s: %s", ticker, exc)
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(_fetch_chain, t) for t in OPTIONS_WATCHLIST]
        for f in as_completed(futs, timeout=35):
            try:
                r = f.result(timeout=12)
                if r and r.get("pc_vol") is not None:
                    results.append(r)
            except Exception:
                pass

    if not results:
        return ""

    # Categorise by skew
    call_heavy = sorted(
        [r for r in results if r["pc_vol"] < 0.5],
        key=lambda x: x["pc_vol"]
    )
    put_heavy = sorted(
        [r for r in results if r["pc_vol"] > 1.5],
        key=lambda x: x["pc_vol"], reverse=True
    )

    lines = ["OPTIONS FLOW — Per-Stock Put/Call (nearest expiry vol):"]
    if call_heavy:
        lines.append("  Call-heavy (P/C<0.50 — bullish bets): " +
                     ", ".join(f"{r['ticker']}({r['pc_vol']})" for r in call_heavy[:7]))
    if put_heavy:
        lines.append("  Put-heavy  (P/C>1.50 — bearish bets): " +
                     ", ".join(f"{r['ticker']}({r['pc_vol']})" for r in put_heavy[:7]))

    return "\n".join(lines) if len(lines) > 1 else ""


def get_options_context() -> str:
    """Combine market-wide P/C ratio + per-stock options skew."""
    from concurrent.futures import ThreadPoolExecutor, as_completed as _ac

    results: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = {
            pool.submit(_market_pc_block):  "market",
            pool.submit(_stock_options_block): "stocks",
        }
        for f in _ac(futs, timeout=40):
            key = futs[f]
            try:
                results[key] = f.result(timeout=15) or ""
            except Exception as exc:
                logger.warning("options context %s failed: %s", key, exc)
                results[key] = ""

    parts = [results.get("market", ""), results.get("stocks", "")]
    parts = [p for p in parts if p]
    return "\n\n".join(parts)
