"""
database/db.py — All SQLite read/write operations.
Provides a thin wrapper around sqlite3 so no ORM is required.
"""

import csv
import io
import os
import sqlite3
import logging
from contextlib import contextmanager
from datetime import date as date_type
from pathlib import Path

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
        # Migrations: add columns to existing databases
        pred_cols  = [r[1] for r in conn.execute("PRAGMA table_info(predictions)").fetchall()]
        score_cols = [r[1] for r in conn.execute("PRAGMA table_info(accuracy_scores)").fetchall()]
        if "direction" not in pred_cols:
            conn.execute("ALTER TABLE predictions ADD COLUMN direction TEXT DEFAULT 'LONG'")
            logger.info("Migration: added direction column to predictions")
        if "allocation_pct" not in pred_cols:
            conn.execute("ALTER TABLE predictions ADD COLUMN allocation_pct REAL DEFAULT 20.0")
            logger.info("Migration: added allocation_pct column to predictions")
        if "session" not in pred_cols:
            conn.execute("ALTER TABLE predictions ADD COLUMN session TEXT DEFAULT 'day'")
            logger.info("Migration: added session column to predictions")
        if "session" not in score_cols:
            conn.execute("ALTER TABLE accuracy_scores ADD COLUMN session TEXT DEFAULT 'day'")
            logger.info("Migration: added session column to accuracy_scores")
    logger.info("Database initialised at %s", _get_db_path())


# ── Predictions ───────────────────────────────────────────────────────────────

def save_predictions(date: str, model_name: str, picks: list[dict],
                     raw_response: str = "", session: str = "day"):
    """
    Insert up to 5 picks for a given model on a given date + session.
    session = "day" (market hours) | "overnight" (close → next open).
    Silently replaces if re-run for the same date+session.
    """
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM predictions WHERE date=? AND model_name=? AND session=?",
            (date, model_name, session),
        )
        for pick in picks:
            conn.execute(
                """INSERT INTO predictions (date, model_name, session, rank, ticker, direction,
                       allocation_pct, reasoning, confidence, raw_response)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    date,
                    model_name,
                    session,
                    pick.get("rank", 0),
                    pick.get("ticker", "").upper(),
                    pick.get("direction", "LONG").upper(),
                    float(pick.get("allocation_pct", 20.0)),
                    pick.get("reasoning", ""),
                    pick.get("confidence", "Medium"),
                    raw_response,
                ),
            )
    logger.info("Saved %d %s predictions for %s on %s", len(picks), session, model_name, date)


def get_predictions_by_date(date: str, session: str | None = None) -> list[dict]:
    """Return all predictions for a given date, optionally filtered by session."""
    with get_conn() as conn:
        if session:
            rows = conn.execute(
                "SELECT * FROM predictions WHERE date=? AND session=? ORDER BY model_name, rank",
                (date, session),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM predictions WHERE date=? ORDER BY model_name, session, rank",
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
                        ticker: str, rank: int, change_pct: float,
                        direction: str = "LONG", session: str = "day"):
    """Insert one scored prediction row. Accounts for LONG/SHORT and day/overnight."""
    direction  = direction.upper()
    is_correct = 1 if (change_pct > 0) == (direction == "LONG") else 0
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO accuracy_scores
               (prediction_id, model_name, date, session, ticker, predicted_rank,
                actual_change_pct, is_correct)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (prediction_id, model_name, date, session, ticker, rank, change_pct, is_correct),
        )


def get_accuracy_summary() -> list[dict]:
    """All-time per-model accuracy summary."""
    return get_accuracy_summary_since("2000-01-01")


def get_accuracy_summary_since(start_date: str) -> list[dict]:
    """
    Per-model accuracy summary from start_date (ISO) to today.
    Ordered by correct_picks DESC so the best caller is #1.
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
               WHERE date >= ?
               GROUP BY model_name
               ORDER BY correct_picks DESC""",
            (start_date,),
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


# ── CSV Import / Restore ──────────────────────────────────────────────────────

def import_predictions_from_csv(csv_content: str) -> int:
    """
    Import predictions from a CSV string.
    Skips rows that already exist (same date + model + rank).
    Returns number of rows actually inserted.
    """
    reader = csv.DictReader(io.StringIO(csv_content))
    count = 0
    with get_conn() as conn:
        for row in reader:
            try:
                rank = int(row["rank"])
            except (KeyError, ValueError, TypeError):
                logger.warning("Skipping CSV row with invalid rank: %s", row)
                continue
            existing = conn.execute(
                "SELECT id FROM predictions WHERE date=? AND model_name=? AND rank=?",
                (row["date"], row["model_name"], rank),
            ).fetchone()
            if existing:
                continue
            try:
                conn.execute(
                    """INSERT INTO predictions
                           (date, model_name, session, rank, ticker, direction,
                            allocation_pct, reasoning, confidence, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        row["date"],
                        row["model_name"],
                        row.get("session", "day"),
                        rank,
                        row["ticker"].upper(),
                        row.get("direction", "LONG").upper(),
                        float(row.get("allocation_pct") or 20.0),
                        row.get("reasoning", ""),
                        row.get("confidence", "Medium"),
                        row.get("created_at") or None,
                    ),
                )
                count += 1
            except Exception as exc:
                logger.warning("Skipping CSV row due to error: %s — %s", row, exc)
    logger.info("Imported %d prediction rows from CSV", count)
    return count


def backup_predictions_to_csv(backup_dir: str | None = None) -> str:
    """
    Export all predictions to a dated CSV in backup_dir.
    Defaults to a 'backups/' folder at the project root (same level as this
    package), which is git-tracked so backups survive Railway redeploys.
    Returns the path of the file written.
    """
    if backup_dir is None:
        # __file__ = .../database/db.py  →  project root = one level up
        backup_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backups")
    Path(backup_dir).mkdir(parents=True, exist_ok=True)
    today = date_type.today().isoformat()
    path = os.path.join(backup_dir, f"predictions_{today}.csv")

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT date, model_name, rank, ticker, direction, allocation_pct, "
            "reasoning, confidence, created_at FROM predictions ORDER BY date, model_name, rank"
        ).fetchall()

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["date", "model_name", "rank", "ticker", "direction",
                        "allocation_pct", "reasoning", "confidence", "created_at"],
        )
        writer.writeheader()
        writer.writerows([dict(r) for r in rows])

    logger.info("Backed up %d predictions to %s", len(rows), path)
    return path


def _default_backup_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backups")


def backup_scores_to_csv(backup_dir: str | None = None) -> str:
    """Export all accuracy_scores to a dated CSV. Called after every scoring run."""
    if backup_dir is None:
        backup_dir = _default_backup_dir()
    Path(backup_dir).mkdir(parents=True, exist_ok=True)
    today = date_type.today().isoformat()
    path  = os.path.join(backup_dir, f"accuracy_{today}.csv")

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT prediction_id, model_name, date, session, ticker, "
            "predicted_rank, actual_change_pct, is_correct, calculated_at "
            "FROM accuracy_scores ORDER BY date, model_name"
        ).fetchall()

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "prediction_id", "model_name", "date", "session", "ticker",
            "predicted_rank", "actual_change_pct", "is_correct", "calculated_at",
        ])
        writer.writeheader()
        writer.writerows([dict(r) for r in rows])

    logger.info("Backed up %d accuracy scores to %s", len(rows), path)
    return path


def backup_portfolio_to_csv(backup_dir: str | None = None) -> str:
    """Export all portfolio_values to a dated CSV. Called after every scoring run."""
    if backup_dir is None:
        backup_dir = _default_backup_dir()
    Path(backup_dir).mkdir(parents=True, exist_ok=True)
    today = date_type.today().isoformat()
    path  = os.path.join(backup_dir, f"portfolio_{today}.csv")

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT model_name, date, portfolio_value, daily_return, "
            "daily_return_pct, calculated_at "
            "FROM portfolio_values ORDER BY date, model_name"
        ).fetchall()

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "model_name", "date", "portfolio_value",
            "daily_return", "daily_return_pct", "calculated_at",
        ])
        writer.writeheader()
        writer.writerows([dict(r) for r in rows])

    logger.info("Backed up %d portfolio rows to %s", len(rows), path)
    return path


def backup_all_to_csv() -> dict[str, str]:
    """Backup predictions + accuracy scores + portfolio values. Call after every job."""
    backup_dir = _default_backup_dir()
    return {
        "predictions": backup_predictions_to_csv(backup_dir),
        "accuracy":    backup_scores_to_csv(backup_dir),
        "portfolio":   backup_portfolio_to_csv(backup_dir),
    }


def restore_from_backups(backup_dir: str | None = None) -> int:
    """
    On startup: restore predictions, accuracy scores, and portfolio values from
    the latest backup CSVs if the tables are empty.
    Returns total rows restored across all three tables.
    """
    if backup_dir is None:
        backup_dir = _default_backup_dir()
    backup_path = Path(backup_dir)
    total = 0

    # ── Predictions ──────────────────────────────────────────────────────────
    with get_conn() as conn:
        pred_count = conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]

    if pred_count > 0:
        logger.info("DB has %d predictions — skipping predictions restore.", pred_count)
    else:
        csv_files = sorted(backup_path.glob("predictions_*.csv")) if backup_path.exists() else []
        if csv_files:
            latest = csv_files[-1]
            try:
                n = import_predictions_from_csv(latest.read_text())
                logger.info("Restored %d predictions from %s", n, latest.name)
                total += n
            except Exception as exc:
                logger.error("Failed to restore predictions from %s: %s", latest.name, exc)

    # ── Accuracy scores ───────────────────────────────────────────────────────
    with get_conn() as conn:
        score_count = conn.execute("SELECT COUNT(*) FROM accuracy_scores").fetchone()[0]

    if score_count > 0:
        logger.info("DB has %d accuracy scores — skipping restore.", score_count)
    else:
        csv_files = sorted(backup_path.glob("accuracy_*.csv")) if backup_path.exists() else []
        if csv_files:
            latest = csv_files[-1]
            try:
                rows = list(csv.DictReader(latest.open()))
                with get_conn() as conn:
                    for row in rows:
                        try:
                            conn.execute(
                                """INSERT OR IGNORE INTO accuracy_scores
                                   (prediction_id, model_name, date, session, ticker,
                                    predicted_rank, actual_change_pct, is_correct, calculated_at)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                (
                                    int(row.get("prediction_id") or 0) or None,
                                    row["model_name"],
                                    row["date"],
                                    row.get("session", "day"),
                                    row["ticker"],
                                    int(row.get("predicted_rank") or 0),
                                    float(row.get("actual_change_pct") or 0),
                                    int(row.get("is_correct") or 0),
                                    row.get("calculated_at") or None,
                                ),
                            )
                            total += 1
                        except Exception:
                            pass
                logger.info("Restored %d accuracy scores from %s", len(rows), latest.name)
            except Exception as exc:
                logger.error("Failed to restore accuracy scores: %s", exc)

    # ── Portfolio values ──────────────────────────────────────────────────────
    with get_conn() as conn:
        port_count = conn.execute("SELECT COUNT(*) FROM portfolio_values").fetchone()[0]

    if port_count > 0:
        logger.info("DB has %d portfolio rows — skipping restore.", port_count)
    else:
        csv_files = sorted(backup_path.glob("portfolio_*.csv")) if backup_path.exists() else []
        if csv_files:
            latest = csv_files[-1]
            try:
                rows = list(csv.DictReader(latest.open()))
                with get_conn() as conn:
                    for row in rows:
                        try:
                            conn.execute(
                                """INSERT OR IGNORE INTO portfolio_values
                                   (model_name, date, portfolio_value,
                                    daily_return, daily_return_pct, calculated_at)
                                   VALUES (?, ?, ?, ?, ?, ?)""",
                                (
                                    row["model_name"],
                                    row["date"],
                                    float(row["portfolio_value"]),
                                    float(row.get("daily_return") or 0),
                                    float(row.get("daily_return_pct") or 0),
                                    row.get("calculated_at") or None,
                                ),
                            )
                            total += 1
                        except Exception:
                            pass
                logger.info("Restored %d portfolio rows from %s", len(rows), latest.name)
            except Exception as exc:
                logger.error("Failed to restore portfolio values: %s", exc)

    if total:
        logger.info("=== Startup restore complete: %d total rows ===", total)
    return total
