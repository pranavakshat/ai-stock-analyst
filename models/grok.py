"""
models/grok.py — xAI Grok integration.

Grok's API is OpenAI-compatible, so we just point the openai SDK at api.x.ai.
Get your key at: https://console.x.ai
"""

import logging
from openai import OpenAI

from config import XAI_API_KEY, GROK_MODEL
from models.prompt import DAY_SYSTEM_PROMPT, build_day_user_prompt
from models.base import parse_picks, fallback_picks

logger = logging.getLogger(__name__)
MODEL_NAME = "grok"


def get_picks(market_context: str = "",
              system_prompt_override: str | None = None,
              user_prompt_builder=None) -> tuple[list[dict], str]:
    if not XAI_API_KEY:
        return fallback_picks(MODEL_NAME, "XAI_API_KEY not set"), ""

    system  = system_prompt_override or DAY_SYSTEM_PROMPT
    builder = user_prompt_builder or build_day_user_prompt

    try:
        client = OpenAI(
            api_key=XAI_API_KEY,
            base_url="https://api.x.ai/v1",
            timeout=120.0,
        )
        response = client.chat.completions.create(
            model=GROK_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": builder(market_context)},
            ],
            max_tokens=2048,
            temperature=0.7,
        )
        raw = response.choices[0].message.content
        picks, raw = parse_picks(raw, MODEL_NAME)
        return picks, raw

    except Exception as exc:
        return fallback_picks(MODEL_NAME, str(exc)), str(exc)
