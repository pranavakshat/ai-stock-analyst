"""
app.py — Flask application: REST API + dashboard HTML + scheduler bootstrap.

Routes:
  GET  /                         → dashboard HTML
  GET  /api/predictions          → all picks for a date (defaults to today)
  GET  /api/predictions/dates    → all dates that have predictions
  GET  /api/accuracy             → per-model accuracy summary
  GET  /api/accuracy/<model>     → daily accuracy history for one model
  GET  /api/portfolio            → latest portfolio value per model
  GET  /api/portfolio/<model>    → full portfolio history for one model
  GET  /api/models               → model metadata (names, colours)
  POST /api/run/morning          → manually trigger morning job (query + email)
  POST /api/run/evening          → manually trigger evening job (score + portfolio) [?date=YYYY-MM-DD]
  GET  /api/export/csv           → download full predictions + results as CSV
  POST /api/import/predictions   → import predictions from CSV (multipart 'file' or raw body)
  GET  /health                   → health check
"""

import logging
import os
from datetime import date

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from config import APP_SECRET_KEY, DEBUG, PORT, MODELS, STARTING_PORTFOLIO_VALUE
from database.db import (
    init_db,
    get_predictions_by_date,
    get_all_prediction_dates,
    get_accuracy_summary,
    get_accuracy_summary_since,
    get_accuracy_over_time,
    get_portfolio_history,
    get_latest_portfolio_values,
)

# ── App setup ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(
    __name__,
    template_folder="dashboard/templates",
    static_folder="dashboard/static",
)
app.secret_key = APP_SECRET_KEY
CORS(app)

# Initialise DB and start scheduler when the app first boots
init_db()

# Restore predictions from backups if DB was wiped (e.g. after a Railway redeploy)
from database.db import restore_from_backups
restored = restore_from_backups()
if restored:
    logger.info("Restored %d predictions from backup CSVs on startup.", restored)
    # Kick off scoring in background so the web server doesn't block on startup
    import threading
    def _startup_backfill():
        try:
            from accuracy.tracker import backfill_unscored_dates
            n = backfill_unscored_dates()
            logger.info("Startup backfill complete: %d date/session combos scored.", n)
        except Exception as exc:
            logger.error("Startup backfill failed: %s", exc, exc_info=True)
    threading.Thread(target=_startup_backfill, daemon=True).start()

from scheduler import create_scheduler
_scheduler = create_scheduler()
_scheduler.start()
logger.info("Scheduler started.")


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    return send_from_directory("dashboard/templates", "index.html")


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("dashboard/static", filename)


# ── Health ────────────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"status": "ok", "date": date.today().isoformat()})


# ── Predictions ───────────────────────────────────────────────────────────────

@app.route("/api/predictions")
def api_predictions():
    target  = request.args.get("date", date.today().isoformat())
    session = request.args.get("session")   # "day", "overnight", or None (all)
    picks   = get_predictions_by_date(target, session=session)
    return jsonify({"date": target, "session": session, "predictions": picks})


@app.route("/api/predictions/dates")
def api_prediction_dates():
    dates = get_all_prediction_dates()
    return jsonify({"dates": dates})


# ── Leaderboards ──────────────────────────────────────────────────────────────

def _period_to_start_date(period: str) -> str:
    """Convert a period string to an ISO start date."""
    from datetime import timedelta
    today = date.today()
    days = {"1d": 0, "1w": 7, "1m": 30, "3m": 90, "1y": 365, "5y": 1825}
    if period in days:
        return (today - timedelta(days=days[period])).isoformat()
    return "2000-01-01"   # "all"


@app.route("/api/leaderboard")
def api_leaderboard():
    """
    Returns P&L and accuracy leaderboards for a given period.
    Query param: period = all | 5y | 1y | 3m | 1m | 1w | 1d
    """
    period     = request.args.get("period", "all").lower()
    start_date = _period_to_start_date(period)

    # ── Accuracy leaderboard ──────────────────────────────────────────────────
    accuracy = get_accuracy_summary_since(start_date)

    # ── P&L leaderboard ───────────────────────────────────────────────────────
    pnl = []
    for model_name in MODELS:
        history = get_portfolio_history(model_name)   # sorted by date ASC

        current_val = history[-1]["portfolio_value"] if history else STARTING_PORTFOLIO_VALUE

        # Last portfolio value at or before start_date (= "opening" of the period)
        opening_val = STARTING_PORTFOLIO_VALUE
        for h in history:
            if h["date"] <= start_date:
                opening_val = h["portfolio_value"]

        gain     = current_val - opening_val
        gain_pct = (gain / opening_val * 100) if opening_val else 0.0

        pnl.append({
            "model_name":      model_name,
            "current_value":   round(current_val, 2),
            "opening_value":   round(opening_val, 2),
            "period_gain":     round(gain, 2),
            "period_gain_pct": round(gain_pct, 2),
        })

    pnl.sort(key=lambda x: x["period_gain_pct"], reverse=True)

    return jsonify({"period": period, "start_date": start_date,
                    "pnl": pnl, "accuracy": accuracy})


# ── Accuracy ──────────────────────────────────────────────────────────────────

@app.route("/api/accuracy")
def api_accuracy():
    summary = get_accuracy_summary()
    return jsonify({"accuracy": summary})


@app.route("/api/accuracy/<model_name>")
def api_accuracy_model(model_name: str):
    if model_name not in MODELS:
        return jsonify({"error": "Unknown model"}), 404
    history = get_accuracy_over_time(model_name)
    return jsonify({"model": model_name, "history": history})


@app.route("/api/accuracy/scores")
def api_accuracy_scores():
    """Return per-pick accuracy for a specific date + session. Used to color history chips."""
    from database.db import get_conn
    target_date = request.args.get("date", date.today().isoformat())
    session     = request.args.get("session", "day")
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT prediction_id, model_name, ticker, is_correct, actual_change_pct
               FROM accuracy_scores WHERE date=? AND session=?""",
            (target_date, session),
        ).fetchall()
    # Key by prediction_id for easy lookup on the frontend
    scores = {r["prediction_id"]: dict(r) for r in rows}
    return jsonify({"scores": scores, "date": target_date, "session": session})


# ── Portfolio ─────────────────────────────────────────────────────────────────

@app.route("/api/portfolio")
def api_portfolio():
    latest = get_latest_portfolio_values()
    return jsonify({"portfolio": latest})


@app.route("/api/portfolio/<model_name>")
def api_portfolio_model(model_name: str):
    if model_name not in MODELS:
        return jsonify({"error": "Unknown model"}), 404
    history = get_portfolio_history(model_name)
    return jsonify({"model": model_name, "history": history})


# ── Model metadata ────────────────────────────────────────────────────────────

@app.route("/api/models")
def api_models():
    return jsonify({"models": MODELS})


# ── Manual triggers ───────────────────────────────────────────────────────────

@app.route("/api/run/morning", methods=["POST"])
def api_run_morning():
    """Manually trigger the morning job (useful for testing)."""
    import threading
    from scheduler import morning_job
    threading.Thread(target=morning_job, daemon=True).start()
    return jsonify({"status": "morning job started in background"})


@app.route("/api/run/evening", methods=["POST"])
def api_run_evening():
    """
    Manually trigger the full evening job (score day picks + run overnight models).
    Optional query params: ?date=YYYY-MM-DD  (defaults to today)
    """
    import threading
    from scheduler import evening_job as _full_evening_job

    target_date = request.args.get("date", date.today().isoformat())

    def _run():
        # Override today's date for the full evening pipeline
        import accuracy.tracker as _t
        from stock_data.fetcher import fetch_eod_prices
        from models.runner import run_all_models
        from email_service.emailer import send_daily_digest
        from datetime import datetime as _dt
        today_fmt = _dt.fromisoformat(target_date).strftime("%A, %B %d, %Y")
        fetch_eod_prices(target_date)
        _t.score_predictions(target_date, session="day")
        _t.update_portfolios(target_date, session="day")
        overnight_picks = run_all_models(target_date, session="overnight")
        send_daily_digest(overnight_picks, today_fmt, session="overnight")

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "evening job started", "date": target_date})


# ── CSV Import ────────────────────────────────────────────────────────────────

@app.route("/api/import/predictions", methods=["POST"])
def api_import_predictions():
    """
    Import predictions from a CSV file upload or raw CSV body, then automatically
    fetch EOD prices + score + update portfolios for every date in the file.

    Accepts multipart/form-data (field name: 'file') or raw text/csv body.
    Query param: ?rescore=false to skip rescoring (default: true).
    """
    from database.db import import_predictions_from_csv
    import csv as _csv
    import io as _io

    rescore = request.args.get("rescore", "true").lower() != "false"

    try:
        if request.files and "file" in request.files:
            csv_content = request.files["file"].read().decode("utf-8")
        else:
            csv_content = request.get_data(as_text=True)

        if not csv_content.strip():
            return jsonify({"error": "No CSV content received"}), 400

        count = import_predictions_from_csv(csv_content)

        # Extract unique (date, session) pairs for rescoring
        dates_sessions: set[tuple[str, str]] = set()
        if rescore and count > 0:
            reader = _csv.DictReader(_io.StringIO(csv_content))
            for row in reader:
                d = row.get("date", "").strip()
                s = row.get("session", "day").strip() or "day"
                if d:
                    dates_sessions.add((d, s))

        if dates_sessions:
            import threading
            def _rescore_all():
                from accuracy.tracker import backfill_unscored_dates
                # Run full backfill — catches all unscored dates, not just those in this CSV
                backfill_unscored_dates()
            threading.Thread(target=_rescore_all, daemon=True).start()

        return jsonify({
            "status":        "ok",
            "rows_imported": count,
            "rescoring":     bool(dates_sessions),
            "dates":         sorted({d for d, _ in dates_sessions}),
        })
    except Exception as exc:
        logger.error("CSV import failed: %s", exc, exc_info=True)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/run/rescore", methods=["POST"])
def api_run_rescore():
    """
    Re-fetch EOD prices + rescore + update portfolios for a date range.
    Query params: ?start=YYYY-MM-DD&end=YYYY-MM-DD&session=day
    """
    import threading
    from datetime import timedelta

    start   = request.args.get("start", date.today().isoformat())
    end     = request.args.get("end", start)
    session = request.args.get("session", "day")

    d_cur, d_end = date.fromisoformat(start), date.fromisoformat(end)
    dates = []
    while d_cur <= d_end:
        dates.append(d_cur.isoformat())
        d_cur += timedelta(days=1)

    def _run():
        from stock_data.fetcher import fetch_eod_prices
        from accuracy.tracker import score_predictions, update_portfolios
        for d in dates:
            try:
                fetch_eod_prices(d)
                score_predictions(d, session=session)
                update_portfolios(d, session=session)
            except Exception as exc:
                logger.error("Rescore failed for %s: %s", d, exc)

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "rescore started", "dates": dates, "session": session})


# ── CSV Export ────────────────────────────────────────────────────────────────

@app.route("/api/export/csv")
def api_export_csv():
    import csv
    import io
    from database.db import get_predictions_range

    start = request.args.get("start", "2024-01-01")
    end   = request.args.get("end",   date.today().isoformat())

    predictions = get_predictions_range(start, end)

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["date", "model_name", "session", "rank", "ticker", "direction",
                    "allocation_pct", "confidence", "reasoning", "auto_trade_eligible",
                    "created_at"],
        extrasaction="ignore",
    )
    writer.writeheader()
    writer.writerows(predictions)

    from flask import Response
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=predictions_{start}_to_{end}.csv"},
    )


# ── Soft Delete / Restore ─────────────────────────────────────────────────────

@app.route("/api/predictions/<int:pred_id>", methods=["DELETE"])
def api_delete_prediction(pred_id: int):
    """Soft-delete a prediction by ID."""
    from database.db import soft_delete_prediction
    ok = soft_delete_prediction(pred_id)
    if not ok:
        return jsonify({"error": "Prediction not found or already deleted"}), 404
    return jsonify({"status": "deleted", "id": pred_id})


@app.route("/api/predictions/<int:pred_id>/restore", methods=["POST"])
def api_restore_prediction(pred_id: int):
    """Restore a soft-deleted prediction."""
    from database.db import restore_prediction
    ok = restore_prediction(pred_id)
    if not ok:
        return jsonify({"error": "Prediction not found or not deleted"}), 404
    return jsonify({"status": "restored", "id": pred_id})


@app.route("/api/predictions/deleted")
def api_deleted_predictions():
    """Return predictions soft-deleted in the last 10 days."""
    from database.db import get_deleted_predictions
    rows = get_deleted_predictions(days=10)
    return jsonify({"deleted": rows})


@app.route("/api/admin/purge-deleted", methods=["POST"])
def api_purge_deleted():
    """Hard-delete predictions soft-deleted more than 10 days ago."""
    from database.db import purge_old_deleted
    count = purge_old_deleted(days=10)
    return jsonify({"status": "ok", "purged": count})


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=DEBUG)
