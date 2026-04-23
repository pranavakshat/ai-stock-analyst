"""
market_context/reddit.py — Scrape WSB and investing subreddits for trending tickers.

Uses Reddit's public JSON API — no authentication or API key required.
Identifies tickers mentioned in post titles using $TICKER patterns and
a curated known-ticker filter to reduce false positives.
"""

import logging
import re
from collections import Counter

import requests

logger = logging.getLogger(__name__)

SUBREDDITS = [
    "wallstreetbets",
    "stocks",
    "investing",
]

# Common false positives to exclude (not stock tickers)
EXCLUDE = {
    "I", "A", "AM", "AN", "ARE", "AT", "BE", "BY", "DO", "FOR", "GO",
    "HE", "IF", "IN", "IS", "IT", "ME", "MY", "NO", "OF", "ON", "OR",
    "SO", "TO", "UP", "US", "WE", "DD", "OP", "ATH", "IMO", "CEO",
    "CFO", "IPO", "ETF", "WSB", "SPY", "QQQ", "IWM", "DIA", "VIX",
    "YOLO", "FOMO", "HOLD", "SELL", "BUY", "CALL", "PUT", "OTM",
    "ITM", "ATM", "IV", "PE", "EPS", "YTD", "GDP", "CPI", "FED",
    "SEC", "FTC", "DOJ", "AI", "ML", "UK", "EU", "US", "CA", "FOMC",
    "THE", "AND", "NOT", "BUT", "ANY", "ALL", "NEW", "NOW", "IRS",
    "WHO", "WHY", "HOW", "LOL", "WTF", "TBH", "EOD", "EOW",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; StockAnalystBot/1.0)",
}


def _fetch_subreddit(sub: str, limit: int = 50) -> list[str]:
    """Return post titles from the subreddit's hot listing."""
    try:
        url = f"https://www.reddit.com/r/{sub}/hot.json?limit={limit}"
        r   = requests.get(url, headers=HEADERS, timeout=8)
        posts = r.json()["data"]["children"]
        return [p["data"]["title"] for p in posts]
    except Exception as exc:
        logger.warning("Reddit fetch failed (%s): %s", sub, exc)
        return []


def _extract_tickers(titles: list[str]) -> Counter:
    """
    Extract ticker mentions from a list of post titles.
    Looks for $TICKER patterns and standalone 1-5 char uppercase words
    that look like tickers (not in the exclude list).
    """
    counter: Counter = Counter()
    # Pattern 1: explicit $TICKER notation — high confidence
    dollar_pattern = re.compile(r"\$([A-Z]{1,5})\b")
    # Pattern 2: standalone UPPERCASE word of 2-5 chars
    word_pattern   = re.compile(r"\b([A-Z]{2,5})\b")

    for title in titles:
        # $TICKER first — these are almost certainly stock mentions
        for match in dollar_pattern.findall(title):
            if match not in EXCLUDE:
                counter[match] += 2   # weight higher — intentional mention

        # Uppercase words (lower weight)
        upper_title = title.upper()
        for match in word_pattern.findall(upper_title):
            if match not in EXCLUDE and len(match) >= 2:
                counter[match] += 1

    return counter


def get_reddit_sentiment() -> str:
    """
    Returns a plain-text block of the most discussed tickers across
    WSB, r/stocks, and r/investing from the last several hours.
    """
    all_titles: list[str] = []
    for sub in SUBREDDITS:
        all_titles.extend(_fetch_subreddit(sub))

    if not all_titles:
        return ""

    counts = _extract_tickers(all_titles)

    # Filter to only tickers mentioned 3+ times to cut noise
    top = [(t, c) for t, c in counts.most_common(30) if c >= 3][:10]

    if not top:
        return ""

    ticker_list = ",  ".join(f"{t} ({c})" for t, c in top)
    return f"REDDIT TRENDING TICKERS (WSB + stocks + investing):\n  {ticker_list}"
