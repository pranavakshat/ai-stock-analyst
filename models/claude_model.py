"""
models/claude_model.py — Anthropic Claude integration.
"""

import logging
import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from models.prompt import DAY_SYSTEM_PROMPT, build_day_user_prompt
from models.base import parse_picks, fallback_picks

logger = logging.getLogger(__name__)
MODEL_NAME = "claude"


def get_picks(market_context: str = "",
              system_prompt_override: str | None = None,
              user_prompt_builder=None) -> tuple[list[dict], str]:
    """Query Claude and return (picks, raw_response)."""
    if not ANTHROPIC_API_KEY:
        return fallback_picks(MODEL_NAME, "ANTHROPIC_API_KEY not set"), ""

    system  = system_prompt_override or DAY_SYSTEM_PROMPT
    builder = user_prompt_builder or build_day_user_prompt

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=180.0)
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=12000,
            thinking={"type": "enabled", "budget_tokens": 8000},
            system=system,
            messages=[{"role": "user", "content": builder(market_context)}],
        )
        raw = next(
            (block.text for block in message.content if hasattr(block, "text")), ""
        )
        picks, raw = parse_picks(raw, MODEL_NAME)
        return picks, raw

    except Exception as exc:
        logger.warning("Claude extended-thinking failed, retrying without: %s", exc)
        try:
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=120.0)
            message = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": builder(market_context)}],
            )
            raw = next(
                (block.text for block in message.content if hasattr(block, "text")),
                message.content[0].text if message.content else "",
            )
            picks, raw = parse_picks(raw, MODEL_NAME)
            return picks, raw
        except Exception as exc2:
            return fallback_picks(MODEL_NAME, str(exc2)), str(exc2)
