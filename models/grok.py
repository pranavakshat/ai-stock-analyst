"""
models/grok.py — xAI Grok integration.

Grok's API is OpenAI-compatible, so we just point the openai SDK at api.x.ai.
Get your key at: https://console.x.ai
"""

import logging
from openai import OpenAI

from config import XAI_API_KEY
from models.prompt import SYSTEM_PROMPT, build_user_prompt
from models.base import parse_picks, fallback_picks

logger = logging.getLogger(__name__)
MODEL_NAME = "grok"


def get_picks(market_context: str = "") -> tuple[list[dict], str]:
    if not XAI_API_KEY:
        return fallback_picks(MODEL_NAME, "XAI_API_KEY not set"), ""

    try:
        client = OpenAI(
            api_key=XAI_API_KEY,
            base_url="https://api.x.ai/v1",
        )
        response = client.chat.completions.create(
            model="grok-3",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": build_user_prompt(market_context)},
            ],
            max_tokens=1024,
            temperature=0.7,
        )
        raw = response.choices[0].message.content
        picks, raw = parse_picks(raw, MODEL_NAME)
        return picks, raw

    except Exception as exc:
        return fallback_picks(MODEL_NAME, str(exc)), str(exc)
