"""
models/runner.py — Calls all models concurrently and saves results to the DB.

session = "day"       → intraday picks, day market context, open→close scoring
session = "overnight" → overnight holds, overnight context, close→next open scoring
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


def run_all_models(today: str | None = None,
                   session: str = "day") -> dict[str, list[dict]]:
    """
    Fetch live market context for the given session, query all models in parallel,
    save results to DB, and return {model_name: picks_list}.

    session = "day"       — uses day market context + intraday prompt
    session = "overnight" — uses overnight context + overnight prompt
    """
    if today is None:
        today = date.today().isoformat()

    logger.info("=== Running %s session models for %s ===", session.upper(), today)

    # ── Fetch appropriate market context ──────────────────────────────────────
    if session == "overnight":
        from market_context.overnight import build_overnight_context
        context_builder = build_overnight_context
        from models.prompt import build_overnight_user_prompt as build_user_prompt
        from models.prompt import OVERNIGHT_SYSTEM_PROMPT as system_prompt
    else:
        from market_context.fetcher import build_market_context
        context_builder = build_market_context
        from models.prompt import build_day_user_prompt as build_user_prompt
        from models.prompt import DAY_SYSTEM_PROMPT as system_prompt

    try:
        market_context = context_builder()
    except Exception as exc:
        logger.warning("Could not fetch %s context: %s — proceeding without it.", session, exc)
        market_context = ""

    results: dict[str, list[dict]] = {}

    def _call(name: str, fn):
        logger.info("Querying %s (%s session)...", name, session)
        # Append this model's track record + cross-model picks to the market context
        from models.track_record import build_performance_context
        perf_ctx = build_performance_context(name)
        combined_context = market_context + perf_ctx if perf_ctx else market_context
        picks, raw = fn(combined_context,
                        system_prompt_override=system_prompt,
                        user_prompt_builder=build_user_prompt)
        save_predictions(today, name, picks, raw, session=session)
        return name, picks

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_call, name, fn): name for name, fn in ADAPTERS.items()}
        for future in as_completed(futures):
            model_key = futures[future]
            try:
                name, picks = future.result()
                results[name] = picks
                logger.info("✓ %s returned %d picks (%s)", name, len(picks), session)
            except Exception as exc:
                logger.error("✗ %s raised: %s", model_key, exc)
                results[model_key] = []

    return results
