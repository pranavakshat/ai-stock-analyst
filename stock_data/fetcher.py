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
            t    = yf.Ticker(ticker)
            data = t.history(start=target_date, end=next_day, auto_adjust=True)

            if data.empty:
                logger.warning("No data returned for %s on %s", ticker, target_date)
                continue

            row         = data.iloc[0]
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


def fetch_premarket_prices(tickers: list[str],
                           target_date: str | None = None) -> dict[str, dict]:
    """
    Fetch pre-market or latest available prices for a list of tickers.

    Used by the morning job (8 AM CT) to score overnight picks BEFORE the
    market opens, when yf.download() wouldn't have today's candle yet.

    Tries, in order:
      1. pre_market_price   (early pre-market, ~4–9:30 AM ET)
      2. regular_market_price (last regular-session close / intraday if open)
      3. history("2d").Close.iloc[-1] — last known close as final fallback

    Saves to stock_results so the rest of the scoring pipeline can read it
    out of the DB via get_stock_results_by_date().
    """
    if target_date is None:
        target_date = date.today().isoformat()

    results: dict[str, dict] = {}

    for ticker in tickers:
        try:
            t    = yf.Ticker(ticker)
            fi   = t.fast_info          # lightweight; avoids the heavy .info dict

            price = (
                getattr(fi, "pre_market_price",     None) or
                getattr(fi, "regular_market_price", None) or
                getattr(fi, "last_price",           None)
            )

            # Last-resort: pull the most recent close from history
            if not price:
                hist = t.history(period="2d")
                if not hist.empty:
                    price = float(hist["Close"].iloc[-1])

            if not price:
                logger.warning("No price found for %s — skipping", ticker)
                continue

            price = float(price)

            # Save as open_price (= overnight exit).  close_price same value
            # since we have no intraday candle yet; overnight P&L is computed
            # as (exit - entry) / entry where entry = yesterday's close.
            save_stock_result(target_date, ticker, price, price, 0)

            results[ticker.upper()] = {
                "ticker":           ticker.upper(),
                "open_price":       price,
                "close_price":      price,
                "price_change":     0.0,
                "price_change_pct": 0.0,
                "volume":           0,
            }
            logger.info("  Pre-market %s: $%.2f", ticker, price)

        except Exception as exc:
            logger.warning("Pre-market fetch failed for %s: %s", ticker, exc)

    logger.info("Pre-market prices fetched: %d/%d tickers", len(results), len(tickers))
    return results
