"""
accuracy/tracker.py — Score predictions against actual stock performance.
Also handles the $10,000 portfolio simulation.

Two session types:
  "day"       — scored using intraday price_change_pct (open → close, same day)
  "overnight" — scored using close of pick_date → open of next trading day
"""

import logging
from datetime import date, timedelta

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
    n_total   = len(predictions)
    n_scored  = 0
    n_skipped = 0
    n_errored = 0

    for pred in predictions:
        model  = pred["model_name"]
        ticker = pred["ticker"]

        try:
            if ticker not in stock_results:
                logger.warning("No stock data for %s — skipping", ticker)
                n_skipped += 1
                continue

            result     = stock_results[ticker]
            change_pct = result["price_change_pct"]
            direction  = (pred.get("direction") or "LONG").upper()
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
            n_scored += 1

            if model not in summary:
                summary[model] = {"correct": 0, "total": 0, "picks": []}
            summary[model]["total"]   += 1
            summary[model]["correct"] += int(is_correct)
            summary[model]["picks"].append({
                "ticker": ticker, "change_pct": change_pct, "correct": is_correct,
            })
        except Exception as exc:
            # Critical: do NOT let a single bad save kill the whole iteration.
            # Pre-fix, an exception here meant ChatGPT+Claude got scored but
            # Gemini+Grok (later in the loop) never did — half the dashboard
            # would be silently empty. Now each pred is isolated.
            n_errored += 1
            logger.exception(
                "score_predictions: failed scoring %s/%s pred_id=%s ticker=%s — %s",
                model, session, pred.get("id"), ticker, exc,
            )

    for model, data in summary.items():
        pct = (data["correct"] / data["total"] * 100) if data["total"] else 0
        logger.info("[%s] %s accuracy on %s: %d/%d (%.1f%%)",
                    model, session, target_date, data["correct"], data["total"], pct)
    logger.info("score_predictions(%s,%s): total=%d scored=%d skipped=%d errored=%d",
                target_date, session, n_total, n_scored, n_skipped, n_errored)

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
    n_total   = len(predictions)
    n_scored  = 0
    n_skipped = 0
    n_errored = 0

    for pred in predictions:
        model  = pred["model_name"]
        ticker = pred["ticker"]

        try:
            prev = prev_results.get(ticker)
            nxt  = next_results.get(ticker)

            if not prev or not nxt:
                logger.warning("Missing price data for %s overnight score — skipping", ticker)
                n_skipped += 1
                continue

            entry_price = prev.get("close_price", 0)
            exit_price  = nxt.get("open_price", 0)

            if not entry_price or not exit_price:
                n_skipped += 1
                continue

            change_pct = (exit_price - entry_price) / entry_price * 100
            direction  = (pred.get("direction") or "LONG").upper()
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
            n_scored += 1

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
        except Exception as exc:
            # Same isolation as score_predictions — see comment there. A single
            # bad save (FK violation, weird tick price, NULL direction, etc.)
            # must NOT silently terminate the whole loop. Each pred handled
            # independently; failures logged and counted but the loop continues.
            n_errored += 1
            logger.exception(
                "score_overnight_picks: failed scoring %s/%s pred_id=%s ticker=%s — %s",
                model, "overnight", pred.get("id"), ticker, exc,
            )

    for model, data in summary.items():
        pct = (data["correct"] / data["total"] * 100) if data["total"] else 0
        logger.info("[%s] Overnight accuracy %s→%s: %d/%d (%.1f%%)",
                    model, pick_date, next_open_date,
                    data["correct"], data["total"], pct)
    logger.info("score_overnight_picks(%s→%s): total=%d scored=%d skipped=%d errored=%d",
                pick_date, next_open_date, n_total, n_scored, n_skipped, n_errored)

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
            save_portfolio_value(model_name, target_date, current_value, 0.0, 0.0, session=session)
            continue

        available   = [p for p in model_picks if p["ticker"] in stock_results]
        if not available:
            save_portfolio_value(model_name, target_date, current_value, 0.0, 0.0, session=session)
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
                             round(daily_return, 2), round(daily_return_pct, 4),
                             session=session)

        logger.info("[%s] %s portfolio %s: $%.2f → $%.2f (%+.2f%%)",
                    model_name, session, target_date,
                    current_value, new_value, daily_return_pct)


# ── Next trading date helper ──────────────────────────────────────────────────

def _next_trading_date(d: str) -> str:
    """Return the next weekday after date string d (skips weekends, not holidays)."""
    dt = date.fromisoformat(d) + timedelta(days=1)
    while dt.weekday() >= 5:   # 5=Sat, 6=Sun
        dt += timedelta(days=1)
    return dt.isoformat()


# ── Overnight portfolio simulation ────────────────────────────────────────────

def update_overnight_portfolios(pick_date: str, next_open_date: str):
    """
    Simulate portfolio for overnight picks made on pick_date.
    Entry = close price of pick_date.
    Exit  = open price of next_open_date.
    Starting balance chains from the latest portfolio value per model
    (typically the day-session value of pick_date, so overnight stacks on top).
    Saved with session='overnight' so it's a distinct data point on the chart.
    """
    predictions = get_predictions_by_date(pick_date, session="overnight")
    if not predictions:
        logger.info("No overnight predictions for %s — skipping overnight portfolio.", pick_date)
        return

    prev_results = get_stock_results_by_date(pick_date)       # close prices
    next_results = get_stock_results_by_date(next_open_date)   # open prices

    if not prev_results:
        logger.warning("No price data for %s — cannot compute overnight portfolio.", pick_date)
        return
    if not next_results:
        logger.warning("No price data for %s — cannot compute overnight portfolio exit.", next_open_date)
        return

    # Start each model from its most recent portfolio value (chains correctly)
    latest = {row["model_name"]: row["portfolio_value"]
              for row in get_latest_portfolio_values()}

    for model_name in MODELS:
        current_value = latest.get(model_name, STARTING_PORTFOLIO_VALUE)
        model_picks   = [p for p in predictions if p["model_name"] == model_name]

        if not model_picks:
            save_portfolio_value(model_name, pick_date, current_value, 0.0, 0.0,
                                 session="overnight")
            continue

        # Build list of picks we have full close→open data for
        available = []
        for p in model_picks:
            ticker  = p["ticker"]
            prev    = prev_results.get(ticker)
            nxt     = next_results.get(ticker)
            if not prev or not nxt:
                logger.warning("Missing price data for %s overnight — skipping pick", ticker)
                continue
            entry   = prev.get("close_price", 0)
            exit_p  = nxt.get("open_price", 0)
            if not entry or not exit_p:
                continue
            overnight_chg = (exit_p - entry) / entry * 100
            available.append({**p, "_overnight_chg": overnight_chg})

        if not available:
            save_portfolio_value(model_name, pick_date, current_value, 0.0, 0.0,
                                 session="overnight")
            continue

        total_alloc = sum(p.get("allocation_pct", 20.0) for p in available)
        new_value   = 0.0

        for pick in available:
            alloc     = pick.get("allocation_pct", 20.0) / total_alloc
            position  = current_value * alloc
            chg_pct   = pick["_overnight_chg"] / 100.0
            direction = pick.get("direction", "LONG").upper()
            gross     = position * (1 - chg_pct if direction == "SHORT" else 1 + chg_pct)
            new_value += gross * (1 - TRADE_FEE_PCT)

        daily_return     = new_value - current_value
        daily_return_pct = (daily_return / current_value * 100) if current_value else 0.0

        save_portfolio_value(model_name, pick_date, round(new_value, 2),
                             round(daily_return, 2), round(daily_return_pct, 4),
                             session="overnight")

        logger.info("[%s] overnight portfolio %s→%s: $%.2f → $%.2f (%+.2f%%)",
                    model_name, pick_date, next_open_date,
                    current_value, new_value, daily_return_pct)


# ── Backfill unscored past dates ──────────────────────────────────────────────

def backfill_unscored_dates() -> int:
    """
    Find all past dates that have predictions but no accuracy scores and score them.
    Handles both 'day' and 'overnight' sessions per date.
    Called automatically by the evening job and after any CSV import.
    Returns number of date/session combos processed.
    """
    from database.db import get_all_prediction_dates, get_conn
    from stock_data.fetcher import fetch_eod_prices

    today = date.today().isoformat()

    # Which (date, session) pairs already have scores
    with get_conn() as conn:
        scored = {(r[0], r[1]) for r in conn.execute(
            "SELECT DISTINCT date, session FROM accuracy_scores"
        ).fetchall()}
        # Which (date, session) pairs exist in active predictions (past dates only)
        pred_pairs = [(r[0], r[1]) for r in conn.execute(
            "SELECT DISTINCT date, session FROM predictions WHERE date < ? AND deleted_at IS NULL",
            (today,)
        ).fetchall()]

    to_process = sorted((d, s) for d, s in pred_pairs if (d, s) not in scored)

    if not to_process:
        logger.info("Backfill: all past dates already scored.")
        return 0

    logger.info("Backfill: %d unscored date/session combos — %s",
                len(to_process), to_process)

    for d, s in to_process:
        try:
            fetch_eod_prices(d)
            if s == "overnight":
                # Overnight: entry = close of pick_date, exit = open of next trading day.
                # Skip if the exit date is today or future — open prices not yet available.
                next_d = _next_trading_date(d)
                if next_d >= today:
                    logger.info(
                        "Skipping overnight backfill for %s → %s: exit date not yet available.",
                        d, next_d,
                    )
                    continue
                fetch_eod_prices(next_d)            # ensure next-day open prices exist
                score_overnight_picks(d, next_d)    # correct close→open accuracy math
                update_overnight_portfolios(d, next_d)  # correct close→open portfolio math
            else:
                score_predictions(d, session=s)     # same-day open→close
                update_portfolios(d, session=s)
            logger.info("Backfilled %s/%s", d, s)
        except Exception as exc:
            logger.error("Backfill failed for %s/%s: %s", d, s, exc)

    return len(to_process)


# ── Convenience wrapper ───────────────────────────────────────────────────────

def run_evening_tasks(target_date: str | None = None, session: str = "day"):
    """Score day picks + update portfolios. Called by scheduler and manual trigger."""
    from stock_data.fetcher import fetch_eod_prices

    if target_date is None:
        target_date = date.today().isoformat()

    logger.info("=== Evening tasks (%s) for %s ===", session, target_date)
    # Catch up any past dates that were never scored (e.g. missed evening jobs)
    backfill_unscored_dates()
    fetch_eod_prices(target_date)
    score_predictions(target_date, session=session)
    update_portfolios(target_date, session=session)
    logger.info("=== Evening tasks complete ===")
