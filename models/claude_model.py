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
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_user_prompt(market_context)}],
        )
        raw = message.content[0].text
        picks, raw = parse_picks(raw, MODEL_NAME)
        return picks, raw

    except Exception as exc:
        return fallback_picks(MODEL_NAME, str(exc)), str(exc)
