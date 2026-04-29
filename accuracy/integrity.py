"""
accuracy/integrity.py — preventative checks against silent partial-scoring.

Why this exists
---------------
We have hit the same class of bug five times in a week:
  - chatgpt + claude scored, gemini + grok silently dropped (Apr 27)
  - gemini + grok scored, chatgpt + claude silently dropped (Apr 28→29)
  - SAVA delisted, single ticker silently dropped from one model

Each time, the dashboard said "we have scores" because *some* rows existed
for the (date, session) pair, but a per-model audit would have flagged the
gap immediately. The old `backfill_unscored_dates()` only checks at the
(date, session) granularity — if any model has a row for that pair, it
considers the pair done. That's the structural hole.

This module checks at the natural-key granularity:
  (date, session, model_name, ticker)

Every prediction must have a matching accuracy_scores row OR an explicit
skip reason. If neither, it's a gap and we surface it loudly.

Usage
-----
- check_scoring_integrity(start_date=None) — read-only audit, returns gaps
- post_scoring_invariant(date, session, expected_n) — sanity check called
  by score_predictions/score_overnight_picks after their loop completes
- log_integrity_warnings_at_startup() — called from app.py after restore

Companion endpoints in app.py:
  GET  /api/admin/integrity-check   → returns gap list
  POST /api/admin/auto-heal         → fills gaps via score-from-cache
"""

from __future__ import annotations

import logging
from datetime import date as date_type, timedelta

logger = logging.getLogger(__name__)


# ── Core audit ───────────────────────────────────────────────────────────────

def check_scoring_integrity(start_date: str | None = None,
                            end_date:   str | None = None) -> dict:
    """
    Audit every (date, session, model, ticker) prediction in the active set.
    Compare against accuracy_scores. Return a structured gap report.

    Args:
        start_date: ISO date, default = 7 days ago. Only audits picks
                    with `date >= start_date` so we don't churn through
                    months of legacy data on every boot.
        end_date:   ISO date, default = today. Picks dated > end_date
                    are not yet eligible (e.g. overnight session waiting
                    on next-day open price).

    Returns:
        {
          "clean": bool,
          "audited": {"start": "...", "end": "...", "predictions": N},
          "gaps": [
            {
              "date": "2026-04-28",
              "session": "overnight",
              "model": "chatgpt",
              "predictions": 5,
              "scored": 0,
              "missing_tickers": ["SBUX","BKNG","TMUS","STX","WELL"],
            },
            ...
          ],
          "summary": {
            "total_gaps": N,
            "missing_rows": N,
            "by_model": {"chatgpt": 5, "claude": 5, ...},
          }
        }
    """
    from database.db import get_conn

    today = date_type.today().isoformat()
    if end_date is None:
        end_date = today
    if start_date is None:
        start_date = (date_type.today() - timedelta(days=7)).isoformat()

    with get_conn() as conn:
        # Active predictions (not soft-deleted) in the audit window
        preds = conn.execute(
            """
            SELECT id, date, session, model_name, ticker
              FROM predictions
             WHERE deleted_at IS NULL
               AND date >= ?
               AND date <= ?
            """,
            (start_date, end_date),
        ).fetchall()

        scores = conn.execute(
            """
            SELECT prediction_id, date, session, model_name, ticker
              FROM accuracy_scores
             WHERE date >= ?
               AND date <= ?
            """,
            (start_date, end_date),
        ).fetchall()

    # Index scores by prediction_id (UPSERT guarantees uniqueness on this key)
    scored_pred_ids = {row["prediction_id"] for row in scores}

    # Group predictions by (date, session, model). Track missing tickers.
    bucket: dict[tuple, dict] = {}
    n_pred_total = 0
    for row in preds:
        n_pred_total += 1
        key = (row["date"], row["session"], row["model_name"])
        b = bucket.setdefault(key, {
            "date":            row["date"],
            "session":         row["session"],
            "model":           row["model_name"],
            "predictions":     0,
            "scored":          0,
            "missing_tickers": [],
        })
        b["predictions"] += 1
        if row["id"] in scored_pred_ids:
            b["scored"] += 1
        else:
            b["missing_tickers"].append(row["ticker"])

    # Filter to genuine gaps. A (date, session) is "not yet eligible" for
    # overnight scoring if next_market_day > today; skip those silently.
    gaps = []
    by_model: dict[str, int] = {}
    missing_rows = 0
    for b in bucket.values():
        if b["scored"] >= b["predictions"]:
            continue
        # Overnight-not-yet-eligible filter: skip overnight picks whose
        # next-trading-day exit price isn't available yet.
        if b["session"] == "overnight":
            d_dt = date_type.fromisoformat(b["date"])
            nxt  = d_dt + timedelta(days=1)
            while nxt.weekday() >= 5:                      # skip weekends
                nxt += timedelta(days=1)
            if nxt.isoformat() > today:                    # exit not yet known
                continue
        # Day session for today: market may still be open. Skip if date == today.
        if b["session"] == "day" and b["date"] == today:
            continue

        gaps.append(b)
        missing = b["predictions"] - b["scored"]
        missing_rows += missing
        by_model[b["model"]] = by_model.get(b["model"], 0) + missing

    return {
        "clean":   len(gaps) == 0,
        "audited": {
            "start":       start_date,
            "end":         end_date,
            "predictions": n_pred_total,
        },
        "gaps": sorted(gaps, key=lambda g: (g["date"], g["session"], g["model"])),
        "summary": {
            "total_gaps":   len(gaps),
            "missing_rows": missing_rows,
            "by_model":     by_model,
        },
    }


# ── Startup hook ─────────────────────────────────────────────────────────────

def log_integrity_warnings_at_startup() -> dict:
    """
    Called from app.py after restore_from_backups() on every Railway boot.
    Logs WARNING for each gap so partial-scoring shows up in deploy logs
    BEFORE it surfaces on the dashboard.

    Returns the integrity report so caller can decide whether to auto-heal.
    """
    try:
        report = check_scoring_integrity()
    except Exception as exc:
        logger.exception("Startup integrity check failed: %s", exc)
        return {"clean": False, "error": str(exc), "gaps": [], "summary": {}}

    if report["clean"]:
        logger.info(
            "Startup integrity check: CLEAN — %d predictions audited (%s → %s).",
            report["audited"]["predictions"],
            report["audited"]["start"],
            report["audited"]["end"],
        )
        return report

    logger.warning(
        "Startup integrity check: %d GAPS DETECTED across %d models — "
        "missing %d accuracy_score rows. Run POST /api/admin/auto-heal to fix.",
        report["summary"]["total_gaps"],
        len(report["summary"]["by_model"]),
        report["summary"]["missing_rows"],
    )
    for g in report["gaps"]:
        logger.warning(
            "  GAP: %s/%s/%s — %d/%d scored, missing %s",
            g["date"], g["session"], g["model"],
            g["scored"], g["predictions"],
            g["missing_tickers"],
        )
    return report


# ── Post-scoring invariant ───────────────────────────────────────────────────

def post_scoring_invariant(target_date: str, session: str, n_scored_counter: int) -> None:
    """
    Called at the end of score_predictions / score_overnight_picks.

    The scoring loop maintains an `n_scored` counter (incremented after every
    successful save_accuracy_score call). The DB count of accuracy_scores
    rows for (date, session) MUST equal that counter — otherwise either:
      (a) save_accuracy_score silently no-op'd (UPSERT path bug)
      (b) a parallel writer is touching the same (date, session)
      (c) the counter was incremented but the save raised after-the-fact

    Any mismatch is logged at ERROR severity. Does NOT raise — we don't want
    to break the scheduler. The dashboard + integrity-check endpoint are the
    surfaces.
    """
    from database.db import get_conn
    try:
        with get_conn() as conn:
            actual = conn.execute(
                "SELECT COUNT(*) FROM accuracy_scores WHERE date = ? AND session = ?",
                (target_date, session),
            ).fetchone()[0]
        if actual < n_scored_counter:
            logger.error(
                "INVARIANT VIOLATED: score loop counter says scored=%d but DB has only %d "
                "accuracy_scores rows for (%s, %s). Silent UPSERT failure?",
                n_scored_counter, actual, target_date, session,
            )
        elif actual > n_scored_counter:
            # Not necessarily a bug — could be a re-score adding to existing rows.
            # Log at INFO so it's visible but not alarming.
            logger.info(
                "Post-scoring DB has %d rows for (%s, %s) vs counter %d "
                "(historical rows from prior runs preserved by UPSERT — expected).",
                actual, target_date, session, n_scored_counter,
            )
    except Exception as exc:
        logger.warning("post_scoring_invariant check failed (non-fatal): %s", exc)
