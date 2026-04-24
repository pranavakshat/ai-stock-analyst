"""
market_context/technicals.py — Technical indicator signals for the watchlist.

Computed entirely from yfinance price/volume data — no extra dependencies.

Signals produced:
  • RSI(14)          — oversold (<35) and overbought (>70)
  • 50 / 200 MA      — above/below, golden cross, death cross
  • Relative Volume  — today's volume vs 20-day average (>2x = unusual)
  • 52-week extremes — stocks within 3% of yearly high or 10% above yearly low
  • MACD line vs signal — recent bullish or bearish cross
"""

import logging

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# Batch download for speed — one API call instead of 30+
TECH_WATCHLIST = [
    # Mega-cap / bellwether tech
    "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA", "AVGO",
    # Mid/high-beta tech & semis
    "AMD", "QCOM", "CRM", "NFLX", "UBER", "PLTR", "MSTR", "ARM", "SMCI",
    # Financials
    "JPM", "BAC", "GS", "COIN",
    # Healthcare / biotech
    "LLY", "MRNA",
    # Energy
    "XOM", "CVX",
    # Key ETFs (macro signal)
    "SPY", "QQQ", "IWM",
]


# ── Indicator helpers ─────────────────────────────────────────────────────────

def _rsi(series: pd.Series, period: int = 14) -> float | None:
    """Wilders RSI.  Returns None if not enough data."""
    if len(series) < period + 2:
        return None
    delta  = series.diff().dropna()
    up     = delta.clip(lower=0)
    down   = (-delta).clip(lower=0)
    avg_u  = up.ewm(com=period - 1, min_periods=period).mean().iloc[-1]
    avg_d  = down.ewm(com=period - 1, min_periods=period).mean().iloc[-1]
    if avg_d == 0:
        return 100.0
    return round(float(100 - 100 / (1 + avg_u / avg_d)), 1)


def _macd_cross(series: pd.Series) -> str | None:
    """
    Detect the most recent MACD(12,26,9) cross direction.
    Returns 'bullish', 'bearish', or None if no recent cross.
    """
    if len(series) < 35:
        return None
    ema12 = series.ewm(span=12, adjust=False).mean()
    ema26 = series.ewm(span=26, adjust=False).mean()
    macd  = ema12 - ema26
    sig   = macd.ewm(span=9, adjust=False).mean()
    hist  = macd - sig

    # Check the last 5 bars for a cross
    recent = hist.iloc[-5:]
    if len(recent) < 2:
        return None
    if recent.iloc[-1] > 0 and recent.iloc[-3] < 0:
        return "bullish"
    if recent.iloc[-1] < 0 and recent.iloc[-3] > 0:
        return "bearish"
    return None


# ── Main context builder ──────────────────────────────────────────────────────

def get_technicals_context() -> str:
    """
    Downloads 1 year of daily OHLCV for TECH_WATCHLIST in one batch call,
    then computes technical signals for each ticker.
    Total runtime: ~5-8 seconds (single batch download).
    """
    try:
        raw = yf.download(
            TECH_WATCHLIST,
            period="1y",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
    except Exception as exc:
        logger.warning("technicals batch download failed: %s", exc)
        return ""

    # Normalize column structure (single vs multi ticker)
    closes  = raw["Close"]  if "Close"  in raw.columns else raw
    volumes = raw["Volume"] if "Volume" in raw.columns else None

    if closes.empty or len(closes) < 20:
        return ""

    # If only one ticker, columns are Series not DataFrame — normalise
    if isinstance(closes, pd.Series):
        closes = closes.to_frame(name=TECH_WATCHLIST[0])
    if volumes is not None and isinstance(volumes, pd.Series):
        volumes = volumes.to_frame(name=TECH_WATCHLIST[0])

    results: dict[str, dict] = {}

    for ticker in closes.columns:
        series = closes[ticker].dropna()
        if len(series) < 30:
            continue
        try:
            price   = float(series.iloc[-1])
            high52  = float(series.max())
            low52   = float(series.min())

            ma50  = float(series.rolling(50).mean().iloc[-1])  if len(series) >= 50  else None
            ma200 = float(series.rolling(200).mean().iloc[-1]) if len(series) >= 200 else None

            rsi   = _rsi(series)
            macd  = _macd_cross(series)

            # Relative volume
            rel_vol = None
            if volumes is not None and ticker in volumes.columns:
                vol_series = volumes[ticker].dropna()
                if len(vol_series) >= 20:
                    avg_v   = float(vol_series.rolling(20).mean().iloc[-1])
                    last_v  = float(vol_series.iloc[-1])
                    rel_vol = round(last_v / avg_v, 1) if avg_v > 0 else None

            results[ticker] = {
                "price":         price,
                "rsi":           rsi,
                "ma50":          ma50,
                "ma200":         ma200,
                "above_50ma":    (price > ma50)  if ma50  else None,
                "above_200ma":   (price > ma200) if ma200 else None,
                "pct_from_high": round((price - high52) / high52 * 100, 1),
                "pct_from_low":  round((price - low52)  / low52  * 100, 1),
                "rel_vol":       rel_vol,
                "macd_cross":    macd,
            }
        except Exception as exc:
            logger.debug("technicals compute error %s: %s", ticker, exc)

    if not results:
        return ""

    lines = ["TECHNICAL SIGNALS:"]

    # ── RSI extremes ──────────────────────────────────────────────────────────
    oversold   = sorted([(t, d["rsi"]) for t, d in results.items()
                          if d.get("rsi") is not None and d["rsi"] < 35],
                        key=lambda x: x[1])
    overbought = sorted([(t, d["rsi"]) for t, d in results.items()
                          if d.get("rsi") is not None and d["rsi"] > 70],
                        key=lambda x: x[1], reverse=True)

    if oversold:
        lines.append("  RSI Oversold  (<35):  " +
                     ", ".join(f"{t}={r}" for t, r in oversold[:8]))
    if overbought:
        lines.append("  RSI Overbought (>70): " +
                     ", ".join(f"{t}={r}" for t, r in overbought[:8]))

    # ── MACD crosses (last 5 sessions) ───────────────────────────────────────
    bull_macd = [t for t, d in results.items() if d.get("macd_cross") == "bullish"]
    bear_macd = [t for t, d in results.items() if d.get("macd_cross") == "bearish"]
    if bull_macd:
        lines.append(f"  MACD Bullish Cross (last 5d): {', '.join(bull_macd[:8])}")
    if bear_macd:
        lines.append(f"  MACD Bearish Cross (last 5d): {', '.join(bear_macd[:8])}")

    # ── 52-week extremes ─────────────────────────────────────────────────────
    near_high = sorted([(t, d["pct_from_high"]) for t, d in results.items()
                        if d.get("pct_from_high") is not None and d["pct_from_high"] >= -3],
                       key=lambda x: x[1], reverse=True)
    near_low  = sorted([(t, d["pct_from_low"]) for t, d in results.items()
                        if d.get("pct_from_low") is not None and d["pct_from_low"] <= 10],
                       key=lambda x: x[1])

    if near_high:
        lines.append("  Near 52-Wk High (≤3%):  " +
                     ", ".join(f"{t} ({p:+.1f}%)" for t, p in near_high[:8]))
    if near_low:
        lines.append("  Near 52-Wk Low  (≤10% above): " +
                     ", ".join(f"{t} (+{p:.1f}%)" for t, p in near_low[:6]))

    # ── High relative volume ──────────────────────────────────────────────────
    high_rvol = sorted([(t, d["rel_vol"]) for t, d in results.items()
                        if d.get("rel_vol") is not None and d["rel_vol"] >= 2.0],
                       key=lambda x: x[1], reverse=True)
    if high_rvol:
        lines.append("  High Rel. Volume (>2× avg): " +
                     ", ".join(f"{t} {v:.1f}×" for t, v in high_rvol[:8]))

    # ── MA trend alignment ────────────────────────────────────────────────────
    bull_align = [t for t, d in results.items()
                  if d.get("above_50ma") is True and d.get("above_200ma") is True]
    bear_align = [t for t, d in results.items()
                  if d.get("above_50ma") is False and d.get("above_200ma") is False]

    etfs = {"SPY", "QQQ", "IWM"}
    bull_stocks = [t for t in bull_align if t not in etfs]
    bear_stocks = [t for t in bear_align if t not in etfs]

    if bull_stocks:
        lines.append(f"  Above 50 & 200 MA (bullish): {', '.join(bull_stocks[:12])}")
    if bear_stocks:
        lines.append(f"  Below 50 & 200 MA (bearish): {', '.join(bear_stocks[:8])}")

    return "\n".join(lines) if len(lines) > 1 else ""
