"""
models/runner.py — Calls all 5 models concurrently and saves results to the DB.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from database.db import save_predictions
from models import claude_model, chatgpt, grok, gemini

logger = logging.getLogger(__name__)

# Map model key → module.get_picks function
ADAPTERS = {
    "claude":  claude_model.get_picks,
    "chatgpt": chatgpt.get_picks,
    "grok":    grok.get_picks,
    "gemini":  gemini.get_picks,
}


def run_all_models(today: str | None = None) -> dict[str, list[dict]]:
    """
    Query all 5 models in parallel (max 5 threads).
    Returns {model_name: picks_list}.
    Also persists every result to the database.
    """
    if today is None:
        today = date.today().isoformat()

    results: dict[str, list[dict]] = {}

    def _call(name: str, fn):
        logger.info("Querying %s...", name)
        picks, raw = fn()
        save_predictions(today, name, picks, raw)
        return name, picks

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_call, name, fn): name for name, fn in ADAPTERS.items()}
        for future in as_completed(futures):
            model_key = futures[future]
            try:
                name, picks = future.result()
                results[name] = picks
                logger.info("✓ %s returned %d picks", name, len(picks))
            except Exception as exc:
                logger.error("✗ %s raised: %s", model_key, exc)
                results[model_key] = []

    return results
