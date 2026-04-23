"""
models/base.py — Shared parsing utilities used by every model adapter.
"""

import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


def parse_picks(raw: str, model_name: str) -> tuple[list[dict], str]:
    """
    Extract the JSON picks array from a model's raw text response.
    Returns (picks_list, raw_response_string).

    Tolerates:
    - Extra prose before/after the JSON block
    - Markdown code fences (```json ... ```)
    - Single-quoted JSON (rare but seen from some models)
    """
    # Strip markdown fences if present
    cleaned = re.sub(r"```(?:json)?", "", raw).strip()

    # Find outermost {...} block
    start = cleaned.find("{")
    end   = cleaned.rfind("}") + 1
    if start == -1 or end == 0:
        logger.error("[%s] No JSON object found in response", model_name)
        return [], raw

    json_str = cleaned[start:end]

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        # Last-ditch: replace single quotes with double quotes
        try:
            data = json.loads(json_str.replace("'", '"'))
        except json.JSONDecodeError as exc:
            logger.error("[%s] JSON parse error: %s\nRaw: %s", model_name, exc, raw[:500])
            return [], raw

    picks = data.get("picks", [])

    validated = []
    seen_tickers = set()
    for i, pick in enumerate(picks[:5]):
        ticker = str(pick.get("ticker", "")).upper().strip()
        if not ticker or ticker in seen_tickers:
            continue
        seen_tickers.add(ticker)
        direction = str(pick.get("direction", "LONG")).upper()
        if direction not in ("LONG", "SHORT"):
            direction = "LONG"
        validated.append({
            "rank":       int(pick.get("rank", i + 1)),
            "ticker":     ticker,
            "direction":  direction,
            "reasoning":  str(pick.get("reasoning", "")),
            "confidence": str(pick.get("confidence", "Medium")),
        })

    logger.info("[%s] Parsed %d picks: %s", model_name, len(validated),
                [p["ticker"] for p in validated])
    return validated, raw


def fallback_picks(model_name: str, error: str) -> list[dict]:
    """Return an empty list + log — never crash the nightly run."""
    logger.error("[%s] FAILED to get picks: %s", model_name, error)
    return []
