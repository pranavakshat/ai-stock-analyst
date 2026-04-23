"""
accuracy/tracker.py — Score predictions against actual stock performance.
Also handles the $10 000 portfolio simulation.

Called every evening after stock_data.fetcher runs.
"""

import logging
from datetime import date

from config import MODELS, STARTING_PORTFOLIO_VALUE
from database.db import (
    get_predictions_by_date,
    get_stock_results_by_date,
    get_latest_portfolio_values,
    save_accuracy_score,
    save_portfolio_value,
)

logger = logging.getLogger(__name__)


# ── Accuracy Scoring ──────────────────────────────────────────────────────────

def score_predictions(target_date: str | None = None) -> dict[str, dict]:
    """
    Compare each model's picks against actual EOD prices.
    Saves accuracy_scores rows and returns a summary dict.
    """
    if target_date is None:
        target_date = date.today().isoformat()

    predictions = get_predictions_by_date(target_date)
    stock_results = get_stock_results_by_date(target_date)

    if not predictions:
        logger.warning("No predictions to score for %s", target_date)
        return {}

    if not stock_results:
        logger.warning("No stock results available for %s — fetch EOD data first.", target_date)
        return {}

    summary: dict[str, dict] = {}  # model_name → {correct, total, picks}

    for pred in predictions:
        model  = pred["model_name"]
        ticker = pred["ticker"]

        if ticker not in stock_results:
            logger.warning("No stock data for %s — skipping", ticker)
            continue

        result     = stock_results[ticker]
        change_pct = result["price_change_pct"]
        direction  = pred.get("direction", "LONG").upper()
        # LONG is correct if price went up; SHORT is correct if price went down
        is_correct = (change_pct > 0) if direction == "LONG" else (change_pct < 0)

        save_accuracy_score(
            prediction_id=pred["id"],
            model_name=model,
            date=target_date,
            ticker=ticker,
            rank=pred["rank"],
            change_pct=change_pct,
        )

        if model not in summary:
            summary[model] = {"correct": 0, "total": 0, "picks": []}
        summary[model]["total"] += 1
        summary[model]["correct"] += int(is_correct)
        summary[model]["picks"].append({
            "ticker": ticker,
            "change_pct": change_pct,
            "correct": is_correct,
        })

    for model, data in summary.items():
        pct = (data["correct"] / data["total"] * 100) if data["total"] else 0
        logger.info("[%s] Accuracy on %s: %d/%d (%.1f%%)",
                    model, target_date, data["correct"], data["total"], pct)

    return summary


# ── Portfolio Simulation ──────────────────────────────────────────────────────

def update_portfolios(target_date: str | None = None):
    """
    Simulate $10 000 portfolio per model:
    - Each day, split current portfolio value equally across all 5 picks.
    - Apply that day's actual returns to each position.
    - If no picks / no data, portfolio value stays flat.
    """
    if target_date is None:
        target_date = date.today().isoformat()

    predictions  = get_predictions_by_date(target_date)
    stock_results = get_stock_results_by_date(target_date)

    # Get each model's current portfolio value (or starting value)
    latest = {row["model_name"]: row["portfolio_value"]
              for row in get_latest_portfolio_values()}

    for model_name in MODELS:
        current_value = latest.get(model_name, STARTING_PORTFOLIO_VALUE)

        # Get this model's picks for today
        model_picks = [p for p in predictions if p["model_name"] == model_name]

        if not model_picks or not stock_results:
            # No picks or no data — flat day
            save_portfolio_value(model_name, target_date, current_value, 0.0, 0.0)
            continue

        # Allocation-weighted: use each pick's allocation_pct
        available_picks = [p for p in model_picks if p["ticker"] in stock_results]
        if not available_picks:
            save_portfolio_value(model_name, target_date, current_value, 0.0, 0.0)
            continue

        # Normalize allocations among picks that have EOD data
        total_alloc = sum(p.get("allocation_pct", 20.0) for p in available_picks)
        new_value = 0.0

        for pick in available_picks:
            alloc     = pick.get("allocation_pct", 20.0) / total_alloc  # normalized fraction
            position  = current_value * alloc
            result    = stock_results[pick["ticker"]]
            chg_pct   = result["price_change_pct"] / 100.0
            direction = pick.get("direction", "LONG").upper()
            # LONG profits when price goes up; SHORT profits when price goes down
            if direction == "SHORT":
                new_value += position * (1 - chg_pct)
            else:
                new_value += position * (1 + chg_pct)

        daily_return     = new_value - current_value
        daily_return_pct = (daily_return / current_value * 100) if current_value else 0.0

        save_portfolio_value(model_name, target_date, round(new_value, 2),
                             round(daily_return, 2), round(daily_return_pct, 4))

        logger.info("[%s] Portfolio %s: $%.2f → $%.2f (%+.2f%%)",
                    model_name, target_date, current_value, new_value, daily_return_pct)


def run_evening_tasks(target_date: str | None = None):
    """Convenience wrapper: score accuracy + update portfolios in one call."""
    from stock_data.fetcher import fetch_eod_prices

    if target_date is None:
        target_date = date.today().isoformat()

    logger.info("=== Evening tasks for %s ===", target_date)
    fetch_eod_prices(target_date)
    score_predictions(target_date)
    update_portfolios(target_date)
    logger.info("=== Evening tasks complete ===")
