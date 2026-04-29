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


# ── Admin token guard ────────────────────────────────────────────────────────
#
# All mutation endpoints (manual job triggers, CSV imports, soft-delete /
# restore, admin tools) require a token to call. Read-only endpoints
# (predictions, leaderboard, portfolio, accuracy, models, export) are public.
#
# Token comes from the ADMIN_TOKEN env var. Clients send it via either:
#   • X-Admin-Token: <token> request header  (preferred — used by curl + JS fetch)
#   • ?admin_token=<token>                  query param  (fallback for buttons)
#
# If ADMIN_TOKEN is not set on the server, the guard fails closed: every
# protected endpoint returns 503. That's deliberate — we don't want a misconfig
# to leave the dashboard's nuke-buttons publicly accessible.

from functools import wraps


def require_admin(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        configured = (os.environ.get("ADMIN_TOKEN") or "").strip()
        if not configured:
            return jsonify({"error": "Server not configured for admin access (ADMIN_TOKEN unset)."}), 503
        provided = (
            request.headers.get("X-Admin-Token", "")
            or request.args.get("admin_token", "")
        ).strip()
        # Constant-time compare so timing can't leak the token
        import hmac
        if not provided or not hmac.compare_digest(provided, configured):
            return jsonify({"error": "Unauthorized"}), 401
        return view(*args, **kwargs)
    return wrapped

# Initialise DB and start scheduler when the app first boots
init_db()

# Restore predictions from backups if DB was wiped (e.g. after a Railway redeploy)
from database.db import restore_from_backups
restored = restore_from_backups()
logger.info("Startup restore: %d rows loaded from backup CSVs.", restored)

# Always kick off a background backfill so accuracy/portfolio data is current
# after every deploy (even when predictions were already in the DB).
import threading
def _startup_backfill():
    try:
        from accuracy.tracker import backfill_unscored_dates
        from database.db import backup_all_to_csv
        n = backfill_unscored_dates()
        logger.info("Startup backfill complete: %d date/session combos scored.", n)
        if n > 0:
            try:
                paths = backup_all_to_csv()
                logger.info("Post-backfill backup written: %s", list(paths.values()))
            except Exception as bex:
                logger.warning("Post-backfill backup failed (non-fatal): %s", bex)
    except Exception as exc:
        logger.error("Startup backfill failed: %s", exc, exc_info=True)
threading.Thread(target=_startup_backfill, daemon=True).start()

from scheduler import create_scheduler

# ── Single-scheduler guard ───────────────────────────────────────────────────
# Multiple gunicorn workers would each boot their own APScheduler and fire
# every job twice (= two morning emails with different picks). We hold an
# exclusive fcntl lock on a file in /tmp; only the first worker to grab it
# starts the scheduler. Other workers serve HTTP only.
import fcntl
_scheduler_lock_path = os.environ.get("SCHEDULER_LOCK", "/tmp/ai-stock-analyst-scheduler.lock")
try:
    _scheduler_lock_fp = open(_scheduler_lock_path, "w")
    fcntl.flock(_scheduler_lock_fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
    _scheduler_lock_fp.write(str(os.getpid()))
    _scheduler_lock_fp.flush()
    _scheduler = create_scheduler()
    _scheduler.start()
    logger.info("Scheduler started in PID %d (acquired lock %s).", os.getpid(), _scheduler_lock_path)
except (BlockingIOError, OSError) as exc:
    logger.info("Scheduler not started in PID %d — another worker holds the lock (%s).", os.getpid(), exc)
    _scheduler = None


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


# ── Live intraday prices ─────────────────────────────────────────────────────
#
# Read-only, ephemeral, never touches the DB. Powers the live-tracking widgets
# on the Today's Picks tab. The 45 s in-process cache is keyed by the sorted
# ticker tuple so rapid tab-switches don't hammer Yahoo with the same query.

_LIVE_CACHE: dict[tuple, tuple[float, dict]] = {}   # {key: (expires_at, payload)}
_LIVE_CACHE_TTL = 45.0    # seconds


def _is_us_market_open() -> bool:
    """True iff it's currently 9:30 AM – 4:00 PM ET on a weekday.

    Note: doesn't account for US market holidays — yfinance will simply
    return stale prices on those days, which is the correct behavior anyway
    (we just won't show a 'live' badge fluctuating against frozen data).
    """
    try:
        from zoneinfo import ZoneInfo
        from datetime import datetime as _dt, time as _time
        now_et = _dt.now(ZoneInfo("America/New_York"))
        if now_et.weekday() >= 5:                         # Sat/Sun
            return False
        return _time(9, 30) <= now_et.time() < _time(16, 0)
    except Exception:
        return False


def _fetch_live_prices(tickers: tuple[str, ...]) -> dict[str, dict]:
    """One-shot live price lookup. Never raises — returns {} on any failure."""
    if not tickers:
        return {}
    try:
        import yfinance as yf
    except Exception as exc:
        logger.warning("yfinance import failed in /api/live/prices: %s", exc)
        return {}

    out: dict[str, dict] = {}
    market_open = _is_us_market_open()

    for ticker in tickers:
        try:
            t  = yf.Ticker(ticker)
            fi = getattr(t, "fast_info", None)

            current = None
            opn     = None
            if fi is not None:
                current = (getattr(fi, "last_price", None)
                           or getattr(fi, "regular_market_price", None))
                opn     = (getattr(fi, "open", None)
                           or getattr(fi, "regular_market_open", None))

            # Fall back to a 2-day history if fast_info didn't give us
            # a usable price (some delisted/illiquid tickers, etc.).
            if current is None or opn is None:
                hist = t.history(period="2d", auto_adjust=True)
                if hist is not None and not hist.empty:
                    last = hist.iloc[-1]
                    if current is None: current = float(last["Close"])
                    if opn     is None: opn     = float(last["Open"])

            if current is None or opn is None:
                continue

            current = float(current)
            opn     = float(opn)
            change_pct = ((current - opn) / opn * 100.0) if opn else 0.0

            out[ticker.upper()] = {
                "current_price":  round(current, 4),
                "open_price":     round(opn, 4),
                "change_pct":     round(change_pct, 4),
                "is_market_open": market_open,
            }
        except Exception as exc:
            # One bad ticker shouldn't kill the rest of the response.
            logger.debug("live price fetch failed for %s: %s", ticker, exc)
            continue

    return out


@app.route("/api/live/prices")
def api_live_prices():
    """
    GET /api/live/prices?tickers=AAPL,MSFT,...

    Returns {TICKER: {current_price, open_price, change_pct, is_market_open}}.
    45 s in-process cache. Empty {} on any upstream failure (caller's
    responsibility to render a graceful fallback).
    """
    import time as _time

    raw = (request.args.get("tickers") or "").strip()
    if not raw:
        return jsonify({})

    tickers = tuple(sorted({t.strip().upper() for t in raw.split(",") if t.strip()}))
    if not tickers:
        return jsonify({})

    now = _time.time()

    # Drop stale entries opportunistically so the cache can't grow without bound.
    for k in [k for k, (exp, _) in _LIVE_CACHE.items() if exp <= now]:
        _LIVE_CACHE.pop(k, None)

    cached = _LIVE_CACHE.get(tickers)
    if cached and cached[0] > now:
        return jsonify(cached[1])

    try:
        payload = _fetch_live_prices(tickers)
    except Exception as exc:
        logger.warning("/api/live/prices unexpected error: %s", exc)
        payload = {}

    _LIVE_CACHE[tickers] = (now + _LIVE_CACHE_TTL, payload)
    return jsonify(payload)


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
@require_admin
def api_run_morning():
    """Manually trigger the morning job (useful for testing)."""
    import threading
    from scheduler import morning_job
    threading.Thread(target=morning_job, daemon=True).start()
    return jsonify({"status": "morning job started in background"})


@app.route("/api/run/evening", methods=["POST"])
@require_admin
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
@require_admin
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
@require_admin
def api_run_rescore():
    """
    Re-fetch EOD prices + rescore + update portfolios for a date range.
    Query params:
      ?start=YYYY-MM-DD&end=YYYY-MM-DD     — date range (defaults to today)
      ?session=day | overnight             — which session
      ?next_open_date=YYYY-MM-DD           — required for overnight: the
                                             trading day whose OPEN price
                                             closes the overnight position.
                                             If omitted, defaults to the
                                             next weekday after `end`.

    Day session uses score_predictions (open→close on same date).
    Overnight session uses score_overnight_picks (close → next open),
    which is the function the morning_job calls. Using score_predictions
    on an overnight session will produce 0% changes — that was the bug
    that bit us on Apr 27.
    """
    import threading
    from datetime import timedelta

    start         = request.args.get("start", date.today().isoformat())
    end           = request.args.get("end", start)
    session       = request.args.get("session", "day")
    next_open_arg = request.args.get("next_open_date", "").strip()

    d_cur, d_end = date.fromisoformat(start), date.fromisoformat(end)
    dates = []
    while d_cur <= d_end:
        dates.append(d_cur.isoformat())
        d_cur += timedelta(days=1)

    def _next_weekday(iso: str) -> str:
        d = date.fromisoformat(iso) + timedelta(days=1)
        while d.weekday() >= 5:                     # 5=Sat, 6=Sun
            d += timedelta(days=1)
        return d.isoformat()

    def _run():
        from stock_data.fetcher import fetch_eod_prices
        from database.db import get_predictions_by_date, save_stock_result
        from accuracy.tracker import (
            score_predictions, update_portfolios,
            score_overnight_picks, update_overnight_portfolios,
        )
        from datetime import datetime as _dt, timedelta as _td

        def _fetch_history_for_overnight_tickers(tickers, target_date):
            """
            Fetch the actual day-candle for each ticker on `target_date` and
            store real (open, close) values in stock_results.

            Critical: do NOT use fetch_premarket_prices here. That helper saves
            open_price = close_price = current_price (same value), which means
            calling it for next_open_date and then computing change_pct against
            it gives ~0% (or worse, OVERWRITES correct data already in
            stock_results with a flat-line snapshot). We need the real intraday
            open from history(start, end).
            """
            try:
                import yfinance as yf
            except Exception as exc:
                logger.warning("yfinance unavailable for overnight rescore: %s", exc)
                return
            end = (_dt.fromisoformat(target_date) + _td(days=1)).date().isoformat()
            for ticker in tickers:
                try:
                    h = yf.Ticker(ticker).history(start=target_date, end=end, auto_adjust=True)
                    if h is None or h.empty:
                        logger.info("No history for %s on %s — skipping", ticker, target_date)
                        continue
                    row = h.iloc[0]
                    save_stock_result(
                        target_date, ticker,
                        float(row["Open"]), float(row["Close"]),
                        int(row.get("Volume", 0) or 0),
                    )
                    logger.info("Fetched %s %s: open=%.4f close=%.4f",
                                ticker, target_date, float(row["Open"]), float(row["Close"]))
                except Exception as exc:
                    logger.warning("Failed fetching %s %s: %s", ticker, target_date, exc)

        for d in dates:
            try:
                if session == "overnight":
                    # Overnight: hold close-of-d → open-of-next-trading-day.
                    nxt = next_open_arg or _next_weekday(d)
                    # 1. Fetch real open/close candles for both dates, scoped
                    #    to the actual overnight ticker list (NOT to the date's
                    #    own predictions, which is what fetch_eod_prices uses
                    #    by default).
                    overnight_preds = get_predictions_by_date(d, session="overnight")
                    overnight_tickers = sorted({p["ticker"] for p in overnight_preds})
                    if overnight_tickers:
                        _fetch_history_for_overnight_tickers(overnight_tickers, d)
                        _fetch_history_for_overnight_tickers(overnight_tickers, nxt)
                    # 2. Score against entry=close(d), exit=open(nxt).
                    score_overnight_picks(pick_date=d, next_open_date=nxt)
                    update_overnight_portfolios(pick_date=d, next_open_date=nxt)
                else:
                    fetch_eod_prices(d)
                    score_predictions(d, session=session)
                    update_portfolios(d, session=session)
            except Exception as exc:
                logger.error("Rescore failed for %s/%s: %s", d, session, exc)

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({
        "status": "rescore started",
        "dates": dates,
        "session": session,
        "next_open_date": next_open_arg or (_next_weekday(dates[-1]) if dates else None),
    })


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
@require_admin
def api_delete_prediction(pred_id: int):
    """Soft-delete a prediction by ID."""
    from database.db import soft_delete_prediction
    ok = soft_delete_prediction(pred_id)
    if not ok:
        return jsonify({"error": "Prediction not found or already deleted"}), 404
    return jsonify({"status": "deleted", "id": pred_id})


@app.route("/api/predictions/<int:pred_id>/restore", methods=["POST"])
@require_admin
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
@require_admin
def api_purge_deleted():
    """Hard-delete predictions soft-deleted more than 10 days ago."""
    from database.db import purge_old_deleted
    count = purge_old_deleted(days=10)
    return jsonify({"status": "ok", "purged": count})


@app.route("/api/admin/whoami", methods=["GET"])
@require_admin
def api_whoami():
    """
    Lightweight auth-check. If the X-Admin-Token (or ?admin_token=) header
    matches ADMIN_TOKEN on the server, returns 200 with {"auth":"valid"}.
    Anything else → 401 / 503 from the @require_admin decorator.

    Use this to verify the token works WITHOUT triggering any side effects.
    Curl it instead of clicking Run Morning when you only want to test auth.
    """
    return jsonify({"status": "ok", "auth": "valid"})


@app.route("/api/admin/clear-scores", methods=["POST"])
@require_admin
def api_clear_scores():
    """
    Hard-delete accuracy_scores rows for a specific (date, session). Does NOT
    touch predictions or portfolio_values. Useful when accuracy_scores has
    accumulated orphan rows whose prediction_id no longer points at a real
    prediction (e.g. after an unauthorized run wrote scores, then the
    underlying predictions got deleted, leaving orphans that the next
    score-run UPSERT can't touch because UPSERT keys on prediction_id).

    Required query params:
      ?date=YYYY-MM-DD
      ?session=day | overnight
      ?confirm=true
    """
    from database.db import get_conn

    target_date = (request.args.get("date") or "").strip()
    sess        = (request.args.get("session") or "").strip()
    confirm     = (request.args.get("confirm") or "").strip().lower()

    if not target_date or sess not in ("day", "overnight"):
        return jsonify({
            "error": "Required: ?date=YYYY-MM-DD&session=day|overnight",
        }), 400
    if confirm != "true":
        return jsonify({
            "error": "Pass &confirm=true to actually delete. This is a hard delete.",
            "would_delete": {"date": target_date, "session": sess, "table": "accuracy_scores"},
        }), 400

    with get_conn() as conn:
        n = conn.execute(
            "DELETE FROM accuracy_scores WHERE date=? AND session=?",
            (target_date, sess),
        ).rowcount

    logger.warning("Admin clear-scores %s/%s: deleted %d rows", target_date, sess, n)
    return jsonify({
        "status": "ok",
        "date": target_date,
        "session": sess,
        "accuracy_scores_deleted": n,
    })


@app.route("/api/admin/delete-session", methods=["POST"])
@require_admin
def api_delete_session():
    """
    Hard-delete every prediction + accuracy_score + portfolio_value row for a
    specific (date, session) pair. Useful for nuking corrupted runs (e.g. an
    unauthorized 'Run Morning' click that overwrote that day's real picks).

    Required query params:
      ?date=YYYY-MM-DD
      ?session=day | overnight

    Optional:
      ?confirm=true   safety check — request is rejected without it
    """
    from database.db import get_conn

    target_date = (request.args.get("date") or "").strip()
    sess        = (request.args.get("session") or "").strip()
    confirm     = (request.args.get("confirm") or "").strip().lower()

    if not target_date or sess not in ("day", "overnight"):
        return jsonify({
            "error": "Required: ?date=YYYY-MM-DD&session=day|overnight",
        }), 400
    if confirm != "true":
        return jsonify({
            "error": "Pass &confirm=true to actually delete. This is a hard delete.",
            "would_delete": {"date": target_date, "session": sess},
        }), 400

    with get_conn() as conn:
        n_pred = conn.execute(
            "DELETE FROM predictions WHERE date=? AND session=?",
            (target_date, sess),
        ).rowcount
        n_score = conn.execute(
            "DELETE FROM accuracy_scores WHERE date=? AND session=?",
            (target_date, sess),
        ).rowcount
        n_port = conn.execute(
            "DELETE FROM portfolio_values WHERE date=? AND session=?",
            (target_date, sess),
        ).rowcount

    logger.warning(
        "Admin delete-session %s/%s: predictions=%d accuracy=%d portfolio=%d",
        target_date, sess, n_pred, n_score, n_port,
    )
    return jsonify({
        "status": "ok",
        "date": target_date,
        "session": sess,
        "predictions_deleted": n_pred,
        "accuracy_scores_deleted": n_score,
        "portfolio_values_deleted": n_port,
    })


@app.route("/api/admin/backup-now", methods=["POST"])
@require_admin
def api_backup_now():
    """
    Dump the current live DB to CSVs in backups/ and (if BACKUP_GIT_PUSH=1
    and GH_TOKEN is set) commit + push them. Use this before a manual
    redeploy to guarantee in-flight data survives the SQLite wipe.

    Pure write-out + commit; never queries models, never re-scores, never
    sends emails. Safe to call at any time.
    """
    from database.db import backup_all_to_csv
    try:
        paths = backup_all_to_csv()
    except Exception as exc:
        logger.error("backup-now: backup_all_to_csv failed: %s", exc, exc_info=True)
        return jsonify({"status": "error", "stage": "csv", "error": str(exc)}), 500

    pushed = False
    push_error = None
    try:
        from git_backup import git_autocommit_backups
        pushed = git_autocommit_backups(label="manual")
    except Exception as exc:
        push_error = str(exc)
        logger.warning("backup-now: git_autocommit_backups failed: %s", exc)

    return jsonify({
        "status":    "ok",
        "csvs":      list(paths.values()) if isinstance(paths, dict) else paths,
        "git_push":  pushed,
        "push_error": push_error,
    })


def _auto_backup_after_admin_mutation(label: str) -> dict:
    """
    Internal helper: dump CSVs and try to commit them. Used at the tail of
    admin mutation endpoints so a Railway redeploy can't lose the change.
    Mirrors api_backup_now() but does not require a separate HTTP call.
    Never raises — failures are reported in the dict.
    """
    from database.db import backup_all_to_csv
    out = {"csvs": [], "git_push": False, "push_error": None, "csv_error": None}
    try:
        paths = backup_all_to_csv()
        out["csvs"] = list(paths.values()) if isinstance(paths, dict) else paths
    except Exception as exc:
        out["csv_error"] = str(exc)
        logger.error("auto_backup: backup_all_to_csv failed: %s", exc, exc_info=True)
        return out
    try:
        from git_backup import git_autocommit_backups
        out["git_push"] = git_autocommit_backups(label=label)
    except Exception as exc:
        out["push_error"] = str(exc)
        logger.warning("auto_backup: git_autocommit_backups failed: %s", exc)
    return out


@app.route("/api/admin/manual-score", methods=["POST"])
@require_admin
def api_manual_score():
    """
    Manually inject one accuracy_scores row. Used when yfinance is wrong
    (delisted-but-actually-trading tickers like SAVA) or when an iteration
    bug silently dropped a model's picks and we need to backfill.

    JSON body:
      {
        "model":      "chatgpt",          # required
        "date":       "2026-04-29",       # required (YYYY-MM-DD, the prediction date)
        "session":    "day",              # required: "day" or "overnight"
        "ticker":     "SAVA",             # required
        "change_pct": -3.19,              # required (signed pct, e.g. -3.19 for -3.19%)
        "direction":  "LONG"              # optional, default LONG
      }

    Behavior:
      - Looks up the prediction by (model, date, session, ticker). 404 if not found.
      - Writes accuracy_scores via the same UPSERT path as the scheduled scorer.
      - Auto-calls backup_all_to_csv + git_autocommit_backups so the change
        survives the next Railway redeploy. NO manual /backup-now needed.
    """
    from database.db import get_conn, save_accuracy_score

    body = request.get_json(silent=True) or {}
    model      = (body.get("model") or "").strip().lower()
    target     = (body.get("date") or "").strip()
    sess       = (body.get("session") or "").strip().lower()
    ticker     = (body.get("ticker") or "").strip().upper()
    direction  = (body.get("direction") or "LONG").strip().upper()
    change_raw = body.get("change_pct")

    if not model or not target or sess not in ("day", "overnight") or not ticker:
        return jsonify({
            "error": "Required JSON: model, date, session (day|overnight), ticker, change_pct",
        }), 400
    try:
        change_pct = float(change_raw)
    except (TypeError, ValueError):
        return jsonify({"error": f"change_pct must be a number, got {change_raw!r}"}), 400
    if direction not in ("LONG", "SHORT"):
        return jsonify({"error": "direction must be LONG or SHORT"}), 400

    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, rank FROM predictions "
            "WHERE model_name=? AND date=? AND session=? AND ticker=? "
            "LIMIT 1",
            (model, target, sess, ticker),
        ).fetchone()

    if not row:
        return jsonify({
            "error": "No matching prediction",
            "lookup": {"model": model, "date": target, "session": sess, "ticker": ticker},
        }), 404

    pred_id = row["id"]
    rank    = row["rank"]

    save_accuracy_score(
        prediction_id=pred_id,
        model_name=model,
        date=target,
        ticker=ticker,
        rank=rank,
        change_pct=round(change_pct, 4),
        direction=direction,
        session=sess,
    )
    logger.warning(
        "Admin manual-score: %s %s %s %s = %.4f%% (LONG=%s) pred_id=%s",
        model, target, sess, ticker, change_pct, direction == "LONG", pred_id,
    )

    backup = _auto_backup_after_admin_mutation(label="manual-score")

    is_correct = 1 if (change_pct > 0) == (direction == "LONG") else 0
    return jsonify({
        "status":         "ok",
        "prediction_id":  pred_id,
        "model":          model,
        "date":           target,
        "session":        sess,
        "ticker":         ticker,
        "change_pct":     round(change_pct, 4),
        "direction":      direction,
        "is_correct":     bool(is_correct),
        "auto_backup":    backup,
    })


@app.route("/api/admin/score-from-cache", methods=["POST"])
@require_admin
def api_score_from_cache():
    """
    Bulk-recompute accuracy_scores for a (date, session) using ONLY prices
    already cached in stock_results. Bypasses every external fetch path —
    useful when yfinance is intermittently failing for some models but the
    prices were captured for others on the same day.

    Required query params:
      ?date=YYYY-MM-DD
      ?session=day | overnight

    Behavior:
      - day session:       entry=open(date), exit=close(date)
      - overnight session: entry=close(date), exit=open(next_market_day)
        (next_market_day defaults to date+1; weekends auto-skipped)

    Iterates predictions one-by-one with the same try/except isolation as
    score_predictions, so a single missing-price ticker can't kill the loop.
    Auto-backs-up at the end. Idempotent thanks to UPSERT on prediction_id.
    """
    from database.db import (
        get_conn,
        get_predictions_by_date,
        get_stock_results_by_date,
        save_accuracy_score,
    )
    from datetime import datetime, timedelta

    target = (request.args.get("date") or "").strip()
    sess   = (request.args.get("session") or "").strip().lower()
    if not target or sess not in ("day", "overnight"):
        return jsonify({"error": "Required: ?date=YYYY-MM-DD&session=day|overnight"}), 400

    preds = get_predictions_by_date(target, session=sess)
    if not preds:
        return jsonify({"status": "ok", "message": "no predictions", "scored": 0}), 200

    if sess == "day":
        compare_date = target
        entry_field, exit_field = "open_price", "close_price"
        needed_dates = [target]
    else:
        d = datetime.strptime(target, "%Y-%m-%d").date()
        nxt = d + timedelta(days=1)
        while nxt.weekday() >= 5:
            nxt += timedelta(days=1)
        compare_date = nxt.isoformat()
        entry_field, exit_field = "close_price", "open_price"
        needed_dates = [target, compare_date]

    # On Railway, stock_results gets wiped on every redeploy and is NOT in
    # the CSV restore set, so the cache is cold whenever we redeploy. Refetch
    # any missing dates from yfinance so this endpoint self-heals instead of
    # returning 20 'no cached price' skips. We write back into stock_results
    # via save_stock_result so subsequent reads will hit the cache.
    from database.db import save_stock_result
    needed_tickers = sorted({p["ticker"] for p in preds})
    fetch_log = []
    for d_iso in needed_dates:
        cached = get_stock_results_by_date(d_iso) or {}
        missing = [t for t in needed_tickers if t not in cached]
        if not missing:
            fetch_log.append({"date": d_iso, "skipped": "all cached"})
            continue
        try:
            import yfinance as yf
            d_dt   = datetime.strptime(d_iso, "%Y-%m-%d").date()
            d_next = (d_dt + timedelta(days=1)).isoformat()
            got = []
            for tk in missing:
                try:
                    hist = yf.Ticker(tk).history(start=d_iso, end=d_next, auto_adjust=True)
                    if hist.empty:
                        continue
                    row = hist.iloc[0]
                    op  = float(row["Open"])
                    cl  = float(row["Close"])
                    save_stock_result(d_iso, tk, op, cl, int(row.get("Volume", 0)))
                    got.append(tk)
                except Exception as inner:
                    logger.warning("score-from-cache fetch %s on %s: %s", tk, d_iso, inner)
            fetch_log.append({"date": d_iso, "requested": missing, "fetched": got,
                              "still_missing": [t for t in missing if t not in got]})
        except Exception as exc:
            logger.exception("score-from-cache: yfinance import/fetch on %s failed: %s", d_iso, exc)
            fetch_log.append({"date": d_iso, "error": str(exc), "requested": missing})

    if sess == "day":
        entry_lookup = exit_lookup = get_stock_results_by_date(target)
    else:
        entry_lookup = get_stock_results_by_date(target)
        exit_lookup  = get_stock_results_by_date(compare_date)

    n_total = len(preds)
    n_scored = n_skipped = n_errored = 0
    detail = []

    for p in preds:
        try:
            t = p["ticker"]
            e = (entry_lookup or {}).get(t, {}).get(entry_field) or 0
            x = (exit_lookup  or {}).get(t, {}).get(exit_field)  or 0
            if not e or not x:
                n_skipped += 1
                detail.append({"ticker": t, "model": p["model_name"], "status": "skipped",
                               "reason": "no cached price",
                               "entry": e, "exit": x})
                continue
            change_pct = (x - e) / e * 100
            direction  = (p.get("direction") or "LONG").upper()
            save_accuracy_score(
                prediction_id=p["id"],
                model_name=p["model_name"],
                date=target,
                ticker=t,
                rank=p["rank"],
                change_pct=round(change_pct, 4),
                direction=direction,
                session=sess,
            )
            n_scored += 1
            detail.append({"ticker": t, "model": p["model_name"],
                           "status": "scored", "change_pct": round(change_pct, 4)})
        except Exception as exc:
            n_errored += 1
            logger.exception("score-from-cache: failed %s/%s: %s", p.get("model_name"), p.get("ticker"), exc)
            detail.append({"ticker": p.get("ticker"), "model": p.get("model_name"),
                           "status": "errored", "error": str(exc)})

    logger.warning("Admin score-from-cache(%s,%s): total=%d scored=%d skipped=%d errored=%d",
                   target, sess, n_total, n_scored, n_skipped, n_errored)

    backup = _auto_backup_after_admin_mutation(label="score-from-cache")

    return jsonify({
        "status":       "ok",
        "date":         target,
        "session":      sess,
        "compare_date": compare_date,
        "total":        n_total,
        "scored":       n_scored,
        "skipped":      n_skipped,
        "errored":      n_errored,
        "detail":       detail,
        "fetch_log":    fetch_log,
        "auto_backup":  backup,
    })


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=DEBUG)
