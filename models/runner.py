"""
models/runner.py — Calls all models concurrently and saves results to the DB.
Fetches live market context once and injects it into every model's prompt.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from database.db import save_predictions
from market_context.fetcher import build_market_context
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
    Fetch live market context, then query all models in parallel.
    Returns {model_name: picks_list} and persists everything to the DB.
    """
    if today is None:
        today = date.today().isoformat()

    # Fetch market context once — shared across all model calls
    logger.info("Fetching live market context...")
    try:
        market_context = build_market_context()
    except Exception as exc:
        logger.warning("Could not fetch market context: %s — proceeding without it.", exc)
        market_context = ""

    results: dict[str, list[dict]] = {}

    def _call(name: str, fn):
        logger.info("Querying %s...", name)
        picks, raw = fn(market_context)
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
