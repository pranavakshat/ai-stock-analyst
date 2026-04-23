"""
market_context/news.py — Fetch top financial news headlines via NewsAPI.

Free tier: 100 requests/day — plenty for one morning call.
Get your key at: https://newsapi.org  (takes 30 seconds, no credit card)

Falls back gracefully to empty string if key not set or API unavailable.
"""

import logging
from datetime import date, timedelta

import requests

from config import NEWS_API_KEY

logger  = logging.getLogger(__name__)
API_URL = "https://newsapi.org/v2/everything"


def get_news_context(max_headlines: int = 15) -> str:
    """
    Returns a plain-text block of the top financial/market headlines
    from the last 18 hours.
    """
    if not NEWS_API_KEY:
        logger.info("NEWS_API_KEY not set — skipping news context.")
        return ""

    # Cast a wide net: major financial topics + geopolitics that moves markets
    query = (
        "stock market OR earnings OR Federal Reserve OR inflation OR tariffs "
        "OR interest rates OR IPO OR merger OR acquisition OR FDA OR crypto"
    )

    since = (date.today() - timedelta(days=1)).isoformat() + "T12:00:00"

    params = {
        "q":          query,
        "language":   "en",
        "sortBy":     "publishedAt",
        "pageSize":   max_headlines,
        "from":       since,
        "apiKey":     NEWS_API_KEY,
    }

    try:
        r    = requests.get(API_URL, params=params, timeout=10)
        data = r.json()

        articles = data.get("articles", [])
        if not articles:
            return ""

        lines = ["TOP MARKET NEWS (last 18 hours):"]
        for i, a in enumerate(articles[:max_headlines], 1):
            source = a.get("source", {}).get("name", "")
            title  = a.get("title", "").strip()
            # Strip the source name if NewsAPI appended it (e.g. "… - Reuters")
            if " - " in title:
                title = title.rsplit(" - ", 1)[0].strip()
            lines.append(f"  {i:>2}. [{source}] {title}")

        return "\n".join(lines)

    except Exception as exc:
        logger.warning("NewsAPI fetch failed: %s", exc)
        return ""
