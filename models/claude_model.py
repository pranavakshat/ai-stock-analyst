"""
models/claude_model.py — Anthropic Claude integration.
"""

import logging
import anthropic

from config import ANTHROPIC_API_KEY
from models.prompt import SYSTEM_PROMPT, build_user_prompt
from models.base import parse_picks, fallback_picks

logger = logging.getLogger(__name__)
MODEL_NAME = "claude"


def get_picks(market_context: str = "") -> tuple[list[dict], str]:
    """Query Claude and return (picks, raw_response)."""
    if not ANTHROPIC_API_KEY:
        return fallback_picks(MODEL_NAME, "ANTHROPIC_API_KEY not set"), ""

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=180.0)
        message = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=12000,
            thinking={
                "type": "enabled",
                "budget_tokens": 8000,   # up to 8k tokens of internal reasoning
            },
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_user_prompt(market_context)}],
        )
        # Extended thinking prepends a ThinkingBlock — find the TextBlock
        raw = next(
            (block.text for block in message.content if hasattr(block, "text")),
            "",
        )
        picks, raw = parse_picks(raw, MODEL_NAME)
        return picks, raw

    except Exception as exc:
        logger.warning("Claude extended-thinking call failed, retrying without thinking: %s", exc)
        # Fallback: retry without extended thinking in case of billing/quota issue
        try:
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=120.0)
            message = client.messages.create(
                model="claude-opus-4-6",
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": build_user_prompt(market_context)}],
            )
            raw = next(
                (block.text for block in message.content if hasattr(block, "text")),
                message.content[0].text if message.content else "",
            )
            picks, raw = parse_picks(raw, MODEL_NAME)
            return picks, raw
        except Exception as exc2:
            return fallback_picks(MODEL_NAME, str(exc2)), str(exc2)
