"""
market_context/finnhub_context.py — Optional Finnhub free-tier integration.

Get a free API key at: https://finnhub.io/
  • 60 requests/minute on the free plan — no credit card required.
  • Set FINNHUB_API_KEY in your Railway env vars (or .env file) to enable.
  • If the key is not set, this module produces an empty string and is skipped.

Data provided (all endpoints are free-tier):
  1. Insider transactions   — open-market buys/sells filed in the past 14 days
  2. News sentiment         — aggregate bull/bear score from recent news articles
  3. Analyst consensus      — buy/hold/sell counts + trend change for top names
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

import requests

from config import FINNHUB_API_KEY

logger = logging.getLogger(__name__)

FINNHUB_BASE = "https://finnhub.io/api/v1"

# Tickers to query — keep this list short to stay under the rate limit
INSIDER_WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA",
    "AMD", "JPM", "BAC", "XOM", "LLY", "PLTR", "COIN",
]

SENTIMENT_WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA",
    "AMD", "JPM", "PLTR",
]


def _fh_get(endpoint: str, params: dict) -> dict | None:
    """Single authenticated request to Finnhub."""
    try:
        params["token"] = FINNHUB_API_KEY
        r = requests.get(f"{FINNHUB_BASE}/{endpoint}", params=params, timeout=8)
        if r.status_code == 200:
            return r.json()
        logger.debug("Finnhub %s → HTTP %s", endpoint, r.status_code)
        return None
    except Exception as exc:
        logger.debug("Finnhub request failed %s: %s", endpoint, exc)
        return None


# ── 1. Insider transactions ───────────────────────────────────────────────────

def _get_insider_block() -> str:
    """
    Returns open-market insider transactions from the past 14 days.
    Ignores option exercises and awards — only real cash buys/sells matter.
    """
    today     = date.today().isoformat()
    two_weeks = (date.today() - timedelta(days=14)).isoformat()

    transactions: list[dict] = []

    def _fetch_insider(ticker: str):
        data = _fh_get("stock/insider-transactions",
                        {"symbol": ticker, "from": two_weeks, "to": today})
        if not data:
            return
        for tx in (data.get("data") or []):
            # P = open-market purchase, S = open-market sale
            if tx.get("transactionCode") not in ("P", "S"):
                continue
            shares = tx.get("share", 0)
            price  = tx.get("price", 0)
            if not shares or not price:
                continue
            value = abs(shares * price)
            if value < 50_000:            # skip tiny transactions
                continue
            transactions.append({
                "ticker":  ticker,
                "name":    tx.get("name", "Insider"),
                "date":    tx.get("transactionDate", "")[:10],
                "code":    tx.get("transactionCode", "?"),
                "shares":  int(shares),
                "price":   round(float(price), 2),
                "value":   round(value),
            })

    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(_fetch_insider, t) for t in INSIDER_WATCHLIST]
        for f in as_completed(futs, timeout=30):
            try:
                f.result(timeout=10)
            except Exception:
                pass

    if not transactions:
        return ""

    # Sort by value descending
    transactions.sort(key=lambda x: x["value"], reverse=True)

    lines = ["INSIDER TRANSACTIONS (past 14 days — open-market only, >$50K):"]
    for tx in transactions[:12]:
        action = "BOUGHT" if tx["code"] == "P" else "SOLD"
        value_str = f"${tx['value']:,}"
        lines.append(
            f"  {tx['date']}  {tx['ticker']:<7} {action}  "
            f"{abs(tx['shares']):,} shares @ ${tx['price']}  = {value_str}"
            f"  ({tx['name'][:28]})"
        )

    return "\n".join(lines)


# ── 2. News sentiment ─────────────────────────────────────────────────────────

def _get_sentiment_block() -> str:
    """
    Aggregate news-article sentiment scores for the watchlist.
    Highlights the most bullish and most bearish stocks by news tone.
    """
    scores: list[tuple[str, float]] = []

    def _fetch_sentiment(ticker: str):
        data = _fh_get("news-sentiment", {"symbol": ticker})
        if not data:
            return
        score = data.get("companyNewsScore")
        if score is not None:
            scores.append((ticker, round(float(score), 2)))

    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(_fetch_sentiment, t) for t in SENTIMENT_WATCHLIST]
        for f in as_completed(futs, timeout=25):
            try:
                f.result(timeout=8)
            except Exception:
                pass

    if not scores:
        return ""

    scores.sort(key=lambda x: x[1], reverse=True)
    bullish = [(t, s) for t, s in scores if s > 0.6]
    bearish = [(t, s) for t, s in scores if s < 0.4]

    lines = ["NEWS SENTIMENT (Finnhub score 0–1, >0.6 = bullish, <0.4 = bearish):"]
    if bullish:
        lines.append("  Bullish news tone: " +
                     ", ".join(f"{t} ({s:.2f})" for t, s in bullish[:6]))
    if bearish:
        lines.append("  Bearish news tone: " +
                     ", ".join(f"{t} ({s:.2f})" for t, s in bearish[:6]))

    return "\n".join(lines) if len(lines) > 1 else ""


# ── 3. Analyst consensus ──────────────────────────────────────────────────────

def _get_consensus_block() -> str:
    """Latest analyst recommendation consensus for key names."""
    rows: list[dict] = []

    def _fetch_rec(ticker: str):
        data = _fh_get("stock/recommendation", {"symbol": ticker})
        if not data or not isinstance(data, list) or not data:
            return
        latest = data[0]    # most recent period
        buy    = latest.get("buy", 0) + latest.get("strongBuy", 0)
        hold   = latest.get("hold", 0)
        sell   = latest.get("sell", 0) + latest.get("strongSell", 0)
        total  = buy + hold + sell
        if total < 5:       # too few analysts — skip
            return
        rows.append({
            "ticker": ticker,
            "buy":    buy,
            "hold":   hold,
            "sell":   sell,
            "total":  total,
            "pct_buy": round(buy / total * 100),
        })

    consensus_list = SENTIMENT_WATCHLIST[:]
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(_fetch_rec, t) for t in consensus_list]
        for f in as_completed(futs, timeout=25):
            try:
                f.result(timeout=8)
            except Exception:
                pass

    if not rows:
        return ""

    rows.sort(key=lambda x: x["pct_buy"], reverse=True)

    lines = ["ANALYST CONSENSUS (buy / hold / sell counts):"]
    for r in rows[:8]:
        bar = "█" * (r["pct_buy"] // 10)
        lines.append(
            f"  {r['ticker']:<7} {r['buy']}B/{r['hold']}H/{r['sell']}S  "
            f"({r['pct_buy']}% buy)  {bar}"
        )

    return "\n".join(lines)


# ── Main entry point ──────────────────────────────────────────────────────────

def get_finnhub_context() -> str:
    """
    Runs all three Finnhub modules concurrently and combines results.
    Returns empty string if FINNHUB_API_KEY is not configured.
    """
    if not FINNHUB_API_KEY:
        return ""

    from concurrent.futures import ThreadPoolExecutor, as_completed as _ac

    tasks = {
        "insider":   _get_insider_block,
        "sentiment": _get_sentiment_block,
        "consensus": _get_consensus_block,
    }

    results: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futs = {pool.submit(fn): key for key, fn in tasks.items()}
        for f in _ac(futs, timeout=40):
            key = futs[f]
            try:
                results[key] = f.result(timeout=15) or ""
            except Exception as exc:
                logger.warning("Finnhub %s failed: %s", key, exc)
                results[key] = ""

    parts = [results.get(k, "") for k in ("insider", "sentiment", "consensus")]
    parts = [p for p in parts if p]
    return "\n\n".join(parts)
