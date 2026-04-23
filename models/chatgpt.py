"""
models/chatgpt.py — OpenAI ChatGPT integration.
"""

import logging
from openai import OpenAI

from config import OPENAI_API_KEY
from models.prompt import SYSTEM_PROMPT, build_user_prompt
from models.base import parse_picks, fallback_picks

logger = logging.getLogger(__name__)
MODEL_NAME = "chatgpt"


def get_picks(market_context: str = "") -> tuple[list[dict], str]:
    if not OPENAI_API_KEY:
        return fallback_picks(MODEL_NAME, "OPENAI_API_KEY not set"), ""

    try:
        client = OpenAI(api_key=OPENAI_API_KEY, timeout=120.0)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": build_user_prompt(market_context)},
            ],
            max_tokens=2048,
            temperature=0.7,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        picks, raw = parse_picks(raw, MODEL_NAME)
        return picks, raw

    except Exception as exc:
        return fallback_picks(MODEL_NAME, str(exc)), str(exc)
