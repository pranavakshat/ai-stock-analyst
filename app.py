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
    Import predictions from a CSV file upload or raw CSV body.
    Accepts multipart/form-data (field name: 'file') or raw text/csv body.
    Returns count of rows inserted.
    """
    from database.db import import_predictions_from_csv
    from flask import Response

    try:
        if request.files and "file" in request.files:
            csv_content = request.files["file"].read().decode("utf-8")
        else:
            csv_content = request.get_data(as_text=True)

        if not csv_content.strip():
            return jsonify({"error": "No CSV content received"}), 400

        count = import_predictions_from_csv(csv_content)
        return jsonify({"status": "ok", "rows_imported": count})
    except Exception as exc:
        logger.error("CSV import failed: %s", exc, exc_info=True)
        return jsonify({"error": str(exc)}), 500


# ── CSV Export ────────────────────────────────────────────────────────────────

@app.route("/api/export/csv")
def api_export_csv():
    import csv
    import io
    from database.db import get_predictions_range, get_accuracy_summary

    start = request.args.get("start", "2024-01-01")
    end   = request.args.get("end",   date.today().isoformat())

    predictions = get_predictions_range(start, end)

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["date", "model_name", "rank", "ticker",
                    "confidence", "reasoning", "created_at"],
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


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=DEBUG)
