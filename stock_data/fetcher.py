"""
stock_data/fetcher.py — Fetch end-of-day prices via yfinance (free, no API key).

Called every evening at ~6 PM after markets close (4 PM ET).
"""

import logging
from datetime import date, timedelta

import yfinance as yf

from database.db import (
    get_predictions_by_date,
    save_stock_result,
    get_stock_results_by_date,
)

logger = logging.getLogger(__name__)


def fetch_eod_prices(target_date: str | None = None) -> dict[str, dict]:
    """
    Fetch open + close prices for every ticker that was predicted on target_date.
    Saves results to the DB and returns {TICKER: result_dict}.
    """
    if target_date is None:
        target_date = date.today().isoformat()

    predictions = get_predictions_by_date(target_date)
    if not predictions:
        logger.warning("No predictions found for %s — nothing to fetch.", target_date)
        return {}

    tickers = list({p["ticker"] for p in predictions})
    logger.info("Fetching EOD prices for %d tickers on %s: %s",
                len(tickers), target_date, tickers)

    # yfinance needs a day range; use target_date → next_day
    next_day = (date.fromisoformat(target_date) + timedelta(days=1)).isoformat()

    results: dict[str, dict] = {}
    for ticker in tickers:
        try:
            data = yf.download(
                ticker,
                start=target_date,
                end=next_day,
                progress=False,
                auto_adjust=True,
            )
            if data.empty:
                logger.warning("No data returned for %s on %s", ticker, target_date)
                continue

            row = data.iloc[0]
            open_price  = float(row["Open"])
            close_price = float(row["Close"])
            volume      = int(row.get("Volume", 0))

            save_stock_result(target_date, ticker, open_price, close_price, volume)

            change     = close_price - open_price
            change_pct = (change / open_price * 100) if open_price else 0.0
            results[ticker] = {
                "ticker":           ticker,
                "open_price":       open_price,
                "close_price":      close_price,
                "price_change":     round(change, 4),
                "price_change_pct": round(change_pct, 4),
                "volume":           volume,
            }
            logger.info("  %s: open=%.2f close=%.2f change=%.2f%%",
                        ticker, open_price, close_price, change_pct)

        except Exception as exc:
            logger.error("Error fetching %s: %s", ticker, exc)

    return results


def get_results_for_date(target_date: str) -> dict[str, dict]:
    """Return already-stored results (skip yfinance if already fetched)."""
    existing = get_stock_results_by_date(target_date)
    if existing:
        return existing
    return fetch_eod_prices(target_date)
