"""
models/track_record.py — Build performance context blocks injected into each model's prompt.

Two context blocks per model call:
  1. self_track_record  — the calling model's own recent picks + overall accuracy
  2. cross_model_picks  — other models' most recent picks + accuracy (for cross-model learning)

These are appended to the market context string so models can learn from history.
"""

import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)


def build_self_track_record(model_name: str, n_days: int = 14) -> str:
    """
    Return a text block summarising the model's own recent accuracy and latest picks.
    Returns empty string if no data exists yet (safe for first run).
    """
    try:
        from database.db import get_accuracy_summary, get_predictions_range

        summary = get_accuracy_summary()
        self_stats = next((s for s in summary if s["model_name"] == model_name), None)

        lines = ["", "=" * 52, "YOUR RECENT PERFORMANCE (use this to improve)", "=" * 52]

        if self_stats:
            acc = self_stats.get("accuracy_pct", 0)
            correct = self_stats.get("correct_picks", 0)
            total = self_stats.get("total_picks", 0)
            lines.append(f"Overall accuracy: {acc}% ({correct}/{total} picks correct all-time)")
        else:
            lines.append("No scored picks yet — this is your first run.")

        # Recent picks over the last n_days
        end_date   = date.today().isoformat()
        start_date = (date.today() - timedelta(days=n_days)).isoformat()
        recent     = get_predictions_range(start_date, end_date)
        own_picks  = [p for p in recent if p["model_name"] == model_name]

        if own_picks:
            # Group by date
            by_date: dict[str, list] = {}
            for p in own_picks:
                by_date.setdefault(p["date"], []).append(p)

            lines.append(f"\nYour picks over the last {n_days} days:")
            for d in sorted(by_date.keys(), reverse=True)[:5]:
                lines.append(f"  {d}:")
                for p in sorted(by_date[d], key=lambda x: x["rank"]):
                    direction = (p.get("direction") or "LONG").upper()
                    conf = p.get("confidence", "?")
                    lines.append(
                        f"    #{p['rank']} {p['ticker']} [{direction}] [{conf} conf]"
                        f"  — {(p.get('reasoning') or '')[:80]}"
                    )

        lines.append("=" * 52)
        return "\n".join(lines)

    except Exception as exc:
        logger.warning("Could not build self track record for %s: %s", model_name, exc)
        return ""


def build_cross_model_context(exclude_model: str) -> str:
    """
    Return a text block showing other models' recent picks and accuracy.
    Gives the model awareness of consensus vs. contrarian positions.
    Returns empty string on error (safe fallback).
    """
    try:
        from database.db import get_accuracy_summary, get_predictions_range
        from config import MODELS

        end_date   = date.today().isoformat()
        start_date = (date.today() - timedelta(days=3)).isoformat()
        recent     = get_predictions_range(start_date, end_date)

        summary    = get_accuracy_summary()
        acc_map    = {s["model_name"]: s for s in summary}

        lines = ["", "=" * 52, "OTHER AI MODELS' RECENT PICKS (for context)", "=" * 52]

        any_data = False
        for model_key, meta in MODELS.items():
            if model_key == exclude_model:
                continue

            picks = [p for p in recent if p["model_name"] == model_key]
            stats = acc_map.get(model_key)
            acc_str = (
                f" (accuracy: {stats['accuracy_pct']}%  {stats['correct_picks']}/{stats['total_picks']})"
                if stats else ""
            )

            if not picks:
                continue

            any_data = True
            # Show only the most recent date's picks
            latest_date  = max(p["date"] for p in picks)
            latest_picks = [p for p in picks if p["date"] == latest_date]
            session_tag  = latest_picks[0].get("session", "day") if latest_picks else "day"

            lines.append(f"\n{meta['display']}{acc_str}  [{latest_date} / {session_tag}]:")
            for p in sorted(latest_picks, key=lambda x: x["rank"])[:5]:
                direction = (p.get("direction") or "LONG").upper()
                conf = p.get("confidence", "?")
                lines.append(
                    f"  #{p['rank']} {p['ticker']} [{direction}] [{conf} conf]"
                )

        if not any_data:
            return ""   # No cross-model data yet — don't pollute the prompt

        lines.append("=" * 52)
        lines.append(
            "NOTE: Use the above for awareness only — do NOT blindly follow consensus. "
            "Identify where you genuinely disagree and explain why in your reasoning."
        )
        return "\n".join(lines)

    except Exception as exc:
        logger.warning("Could not build cross-model context: %s", exc)
        return ""


def build_performance_context(model_name: str) -> str:
    """
    Combine self track record + cross-model context into one block.
    Safe to call even if no DB data exists yet.
    """
    self_block  = build_self_track_record(model_name)
    cross_block = build_cross_model_context(model_name)
    return self_block + cross_block
