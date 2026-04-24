"""
accuracy/tracker.py — Score predictions against actual stock performance.
Also handles the $10,000 portfolio simulation.

Two session types:
  "day"       — scored using intraday price_change_pct (open → close, same day)
  "overnight" — scored using close of pick_date → open of next trading day
"""

import logging
from datetime import date

from config import MODELS, STARTING_PORTFOLIO_VALUE, TRADE_FEE_PCT
from database.db import (
    get_predictions_by_date,
    get_stock_results_by_date,
    get_latest_portfolio_values,
    save_accuracy_score,
    save_portfolio_value,
)

logger = logging.getLogger(__name__)


# ── Day session scoring ───────────────────────────────────────────────────────

def score_predictions(target_date: str | None = None,
                      session: str = "day") -> dict[str, dict]:
    """
    Score predictions for a given date and session.
    Day: uses price_change_pct (open → close of same day).
    """
    if target_date is None:
        target_date = date.today().isoformat()

    predictions   = get_predictions_by_date(target_date, session=session)
    stock_results = get_stock_results_by_date(target_date)

    if not predictions:
        logger.warning("No %s predictions to score for %s", session, target_date)
        return {}
    if not stock_results:
        logger.warning("No stock results for %s — fetch EOD data first.", target_date)
        return {}

    summary: dict[str, dict] = {}

    for pred in predictions:
        model  = pred["model_name"]
        ticker = pred["ticker"]

        if ticker not in stock_results:
            logger.warning("No stock data for %s — skipping", ticker)
            continue

        result     = stock_results[ticker]
        change_pct = result["price_change_pct"]
        direction  = pred.get("direction", "LONG").upper()
        is_correct = (change_pct > 0) if direction == "LONG" else (change_pct < 0)

        save_accuracy_score(
            prediction_id=pred["id"],
            model_name=model,
            date=target_date,
            ticker=ticker,
            rank=pred["rank"],
            change_pct=change_pct,
            direction=direction,
            session=session,
        )

        if model not in summary:
            summary[model] = {"correct": 0, "total": 0, "picks": []}
        summary[model]["total"]   += 1
        summary[model]["correct"] += int(is_correct)
        summary[model]["picks"].append({
            "ticker": ticker, "change_pct": change_pct, "correct": is_correct,
        })

    for model, data in summary.items():
        pct = (data["correct"] / data["total"] * 100) if data["total"] else 0
        logger.info("[%s] %s accuracy on %s: %d/%d (%.1f%%)",
                    model, session, target_date, data["correct"], data["total"], pct)

    return summary


# ── Overnight scoring ─────────────────────────────────────────────────────────

def score_overnight_picks(pick_date: str, next_open_date: str) -> dict[str, dict]:
    """
    Score overnight picks made on `pick_date`:
      entry = close price of pick_date
      exit  = open price of next_open_date

    Called by the morning job each day.
    """
    predictions = get_predictions_by_date(pick_date, session="overnight")
    if not predictions:
        logger.info("No overnight predictions for %s — nothing to score.", pick_date)
        return {}

    prev_results = get_stock_results_by_date(pick_date)
    next_results = get_stock_results_by_date(next_open_date)

    if not prev_results:
        logger.warning("No stock results for %s — can't score overnight picks.", pick_date)
        return {}

    if not next_results:
        # Market likely hasn't opened yet (morning job runs at 8 AM CT).
        # Use pre-market / latest available price as the overnight exit price.
        logger.info("No EOD data for %s — fetching pre-market prices...", next_open_date)
        try:
            from stock_data.fetcher import fetch_premarket_prices
            tickers = list({p["ticker"] for p in predictions})
            next_results = fetch_premarket_prices(tickers, next_open_date)
        except Exception as exc:
            logger.warning("Could not fetch pre-market prices for %s: %s", next_open_date, exc)
            return {}

    summary: dict[str, dict] = {}

    for pred in predictions:
        model  = pred["model_name"]
        ticker = pred["ticker"]

        prev = prev_results.get(ticker)
        nxt  = next_results.get(ticker)

        if not prev or not nxt:
            logger.warning("Missing price data for %s overnight score — skipping", ticker)
            continue

        entry_price = prev.get("close_price", 0)
        exit_price  = nxt.get("open_price", 0)

        if not entry_price or not exit_price:
            continue

        change_pct = (exit_price - entry_price) / entry_price * 100
        direction  = pred.get("direction", "LONG").upper()
        is_correct = (change_pct > 0) if direction == "LONG" else (change_pct < 0)

        save_accuracy_score(
            prediction_id=pred["id"],
            model_name=model,
            date=pick_date,
            ticker=ticker,
            rank=pred["rank"],
            change_pct=round(change_pct, 4),
            direction=direction,
            session="overnight",
        )

        if model not in summary:
            summary[model] = {"correct": 0, "total": 0, "picks": []}
        summary[model]["total"]   += 1
        summary[model]["correct"] += int(is_correct)
        summary[model]["picks"].append({
            "ticker": ticker,
            "entry": round(entry_price, 2),
            "exit":  round(exit_price, 2),
            "change_pct": round(change_pct, 2),
            "correct": is_correct,
        })

    for model, data in summary.items():
        pct = (data["correct"] / data["total"] * 100) if data["total"] else 0
        logger.info("[%s] Overnight accuracy %s→%s: %d/%d (%.1f%%)",
                    model, pick_date, next_open_date,
                    data["correct"], data["total"], pct)

    return summary


# ── Portfolio simulation ──────────────────────────────────────────────────────

def update_portfolios(target_date: str | None = None, session: str = "day"):
    """Simulate the $10,000 portfolio using conviction-weighted positions."""
    if target_date is None:
        target_date = date.today().isoformat()

    predictions   = get_predictions_by_date(target_date, session=session)
    stock_results = get_stock_results_by_date(target_date)

    latest = {row["model_name"]: row["portfolio_value"]
              for row in get_latest_portfolio_values()}

    for model_name in MODELS:
        current_value = latest.get(model_name, STARTING_PORTFOLIO_VALUE)
        model_picks   = [p for p in predictions if p["model_name"] == model_name]

        if not model_picks or not stock_results:
            save_portfolio_value(model_name, target_date, current_value, 0.0, 0.0)
            continue

        available   = [p for p in model_picks if p["ticker"] in stock_results]
        if not available:
            save_portfolio_value(model_name, target_date, current_value, 0.0, 0.0)
            continue

        total_alloc = sum(p.get("allocation_pct", 20.0) for p in available)
        new_value   = 0.0

        for pick in available:
            alloc     = pick.get("allocation_pct", 20.0) / total_alloc
            position  = current_value * alloc
            result    = stock_results[pick["ticker"]]
            chg_pct   = result["price_change_pct"] / 100.0
            direction = pick.get("direction", "LONG").upper()
            gross = position * (1 - chg_pct if direction == "SHORT" else 1 + chg_pct)
            # Deduct regulatory sell-side fees (SEC + FINRA TAF, ~0.03%)
            new_value += gross * (1 - TRADE_FEE_PCT)

        daily_return     = new_value - current_value
        daily_return_pct = (daily_return / current_value * 100) if current_value else 0.0

        save_portfolio_value(model_name, target_date, round(new_value, 2),
                             round(daily_return, 2), round(daily_return_pct, 4))

        logger.info("[%s] %s portfolio %s: $%.2f → $%.2f (%+.2f%%)",
                    model_name, session, target_date,
                    current_value, new_value, daily_return_pct)


# ── Convenience wrapper ───────────────────────────────────────────────────────

def run_evening_tasks(target_date: str | None = None, session: str = "day"):
    """Score day picks + update portfolios. Called by scheduler and manual trigger."""
    from stock_data.fetcher import fetch_eod_prices

    if target_date is None:
        target_date = date.today().isoformat()

    logger.info("=== Evening tasks (%s) for %s ===", session, target_date)
    fetch_eod_prices(target_date)
    score_predictions(target_date, session=session)
    update_portfolios(target_date, session=session)
    logger.info("=== Evening tasks complete ===")
