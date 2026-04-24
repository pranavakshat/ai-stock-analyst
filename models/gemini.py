"""
models/gemini.py — Google Gemini integration via the new google-genai SDK.

Get a free API key at: https://aistudio.google.com/app/apikey
"""

import logging
from google import genai
from google.genai import types

from config import GOOGLE_API_KEY
from models.prompt import DAY_SYSTEM_PROMPT, build_day_user_prompt
from models.base import parse_picks, fallback_picks

logger = logging.getLogger(__name__)
MODEL_NAME = "gemini"

CANDIDATE_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.5-pro",
]
THINKING_MODELS = {"gemini-2.5-flash", "gemini-2.5-pro"}


def get_picks(market_context: str = "",
              system_prompt_override: str | None = None,
              user_prompt_builder=None) -> tuple[list[dict], str]:
    if not GOOGLE_API_KEY:
        return fallback_picks(MODEL_NAME, "GOOGLE_API_KEY not set"), ""

    system  = system_prompt_override or DAY_SYSTEM_PROMPT
    builder = user_prompt_builder or build_day_user_prompt

    try:
        client    = genai.Client(api_key=GOOGLE_API_KEY)
        raw       = None
        last_error = None

        for model in CANDIDATE_MODELS:
            try:
                supports_thinking = model in THINKING_MODELS
                config_kwargs = dict(
                    system_instruction=system,
                    max_output_tokens=8000,
                    temperature=1.0 if supports_thinking else 0.7,
                )
                if supports_thinking:
                    config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=8000)

                response = client.models.generate_content(
                    model=model,
                    contents=builder(market_context),
                    config=types.GenerateContentConfig(**config_kwargs),
                )
                raw = response.text
                logger.info("Gemini using model: %s (thinking=%s)", model, supports_thinking)
                break
            except Exception as e:
                last_error = e
                logger.warning("Gemini model %s failed: %s", model, e)
                continue

        if raw is None:
            raise Exception(str(last_error))

        picks, raw = parse_picks(raw, MODEL_NAME)
        return picks, raw

    except Exception as exc:
        return fallback_picks(MODEL_NAME, str(exc)), str(exc)
