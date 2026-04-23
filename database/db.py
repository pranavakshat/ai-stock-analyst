"""
database/db.py — All SQLite read/write operations.
Provides a thin wrapper around sqlite3 so no ORM is required.
"""

import os
import sqlite3
import logging
from contextlib import contextmanager
from datetime import date as date_type

from config import DATABASE_PATH

logger = logging.getLogger(__name__)

# ── Connection helper ─────────────────────────────────────────────────────────

def _get_db_path() -> str:
    """Resolve the database path and ensure its directory exists."""
    path = DATABASE_PATH
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    return path


@contextmanager
def get_conn():
    """Yield a sqlite3 connection with row_factory set."""
    conn = sqlite3.connect(_get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # safe for concurrent reads
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Schema initialisation ─────────────────────────────────────────────────────

def init_db():
    """Create all tables if they don't exist yet, and run migrations."""
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path) as f:
        sql = f.read()
    with get_conn() as conn:
        conn.executescript(sql)
        # Migration: add direction column to existing databases
        cols = [r[1] for r in conn.execute("PRAGMA table_info(predictions)").fetchall()]
        if "direction" not in cols:
            conn.execute("ALTER TABLE predictions ADD COLUMN direction TEXT DEFAULT 'LONG'")
            logger.info("Migration: added direction column to predictions")
        if "allocation_pct" not in cols:
            conn.execute("ALTER TABLE predictions ADD COLUMN allocation_pct REAL DEFAULT 20.0")
            logger.info("Migration: added allocation_pct column to predictions")
    logger.info("Database initialised at %s", _get_db_path())


# ── Predictions ───────────────────────────────────────────────────────────────

def save_predictions(date: str, model_name: str, picks: list[dict], raw_response: str = ""):
    """
    Insert up to 5 picks for a given model on a given date.
    Each pick dict should have keys: ticker, reasoning, confidence, rank.
    Silently replaces if re-run for the same date.
    """
    with get_conn() as conn:
        # Remove any stale predictions for this model+date before inserting fresh ones
        conn.execute(
            "DELETE FROM predictions WHERE date=? AND model_name=?",
            (date, model_name),
        )
        for pick in picks:
            conn.execute(
                """INSERT INTO predictions (date, model_name, rank, ticker, direction,
                       allocation_pct, reasoning, confidence, raw_response)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    date,
                    model_name,
                    pick.get("rank", 0),
                    pick.get("ticker", "").upper(),
                    pick.get("direction", "LONG").upper(),
                    float(pick.get("allocation_pct", 20.0)),
                    pick.get("reasoning", ""),
                    pick.get("confidence", "Medium"),
                    raw_response,
                ),
            )
    logger.info("Saved %d predictions for %s on %s", len(picks), model_name, date)


def get_predictions_by_date(date: str) -> list[dict]:
    """Return all predictions for a given date, ordered by model + rank."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM predictions WHERE date=? ORDER BY model_name, rank""",
            (date,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_predictions_range(start: str, end: str) -> list[dict]:
    """Return predictions between two ISO dates (inclusive)."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM predictions WHERE date BETWEEN ? AND ?
               ORDER BY date DESC, model_name, rank""",
            (start, end),
        ).fetchall()
    return [dict(r) for r in rows]


def get_all_prediction_dates() -> list[str]:
    """Return distinct dates that have predictions, newest first."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT date FROM predictions ORDER BY date DESC"
        ).fetchall()
    return [r["date"] for r in rows]


# ── Stock Results ─────────────────────────────────────────────────────────────

def save_stock_result(date: str, ticker: str, open_price: float, close_price: float,
                      volume: int = 0):
    """Upsert end-of-day result for one ticker."""
    change = close_price - open_price
    change_pct = (change / open_price * 100) if open_price else 0.0
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO stock_results (date, ticker, open_price, close_price,
               price_change, price_change_pct, volume)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(date, ticker) DO UPDATE SET
                 open_price=excluded.open_price,
                 close_price=excluded.close_price,
                 price_change=excluded.price_change,
                 price_change_pct=excluded.price_change_pct,
                 volume=excluded.volume,
                 fetched_at=datetime('now')""",
            (date, ticker.upper(), open_price, close_price, change, change_pct, volume),
        )


def get_stock_results_by_date(date: str) -> dict[str, dict]:
    """Return {TICKER: result_dict} for a given date."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM stock_results WHERE date=?", (date,)
        ).fetchall()
    return {r["ticker"]: dict(r) for r in rows}


# ── Accuracy Scores ───────────────────────────────────────────────────────────

def save_accuracy_score(prediction_id: int, model_name: str, date: str,
                        ticker: str, rank: int, change_pct: float):
    """Insert one scored prediction row."""
    is_correct = 1 if change_pct > 0 else 0
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO accuracy_scores
               (prediction_id, model_name, date, ticker, predicted_rank,
                actual_change_pct, is_correct)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (prediction_id, model_name, date, ticker, rank, change_pct, is_correct),
        )


def get_accuracy_summary() -> list[dict]:
    """
    Return per-model accuracy summary:
    total_picks, correct_picks, accuracy_pct, avg_return_pct
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT
                 model_name,
                 COUNT(*)                          AS total_picks,
                 SUM(is_correct)                   AS correct_picks,
                 ROUND(AVG(is_correct) * 100, 2)   AS accuracy_pct,
                 ROUND(AVG(actual_change_pct), 2)  AS avg_return_pct
               FROM accuracy_scores
               GROUP BY model_name
               ORDER BY accuracy_pct DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


def get_accuracy_over_time(model_name: str) -> list[dict]:
    """Return daily rolling accuracy for one model (for charting)."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT date,
                 ROUND(AVG(is_correct) * 100, 2) AS daily_accuracy_pct,
                 ROUND(AVG(actual_change_pct), 2) AS avg_return_pct
               FROM accuracy_scores
               WHERE model_name=?
               GROUP BY date
               ORDER BY date""",
            (model_name,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Portfolio ─────────────────────────────────────────────────────────────────

def save_portfolio_value(model_name: str, date: str, value: float,
                         daily_return: float, daily_return_pct: float):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO portfolio_values
               (model_name, date, portfolio_value, daily_return, daily_return_pct)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(model_name, date) DO UPDATE SET
                 portfolio_value=excluded.portfolio_value,
                 daily_return=excluded.daily_return,
                 daily_return_pct=excluded.daily_return_pct,
                 calculated_at=datetime('now')""",
            (model_name, date, value, daily_return, daily_return_pct),
        )


def get_portfolio_history(model_name: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT date, portfolio_value, daily_return, daily_return_pct
               FROM portfolio_values WHERE model_name=? ORDER BY date""",
            (model_name,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_latest_portfolio_values() -> list[dict]:
    """Return the most recent portfolio value for every model."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT pv.*
               FROM portfolio_values pv
               INNER JOIN (
                 SELECT model_name, MAX(date) AS max_date
                 FROM portfolio_values GROUP BY model_name
               ) latest ON pv.model_name=latest.model_name AND pv.date=latest.max_date
               ORDER BY pv.portfolio_value DESC"""
        ).fetchall()
    return [dict(r) for r in rows]
