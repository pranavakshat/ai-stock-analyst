"""
models/gemini.py — Google Gemini integration via the new google-genai SDK.

Get a free API key at: https://aistudio.google.com/app/apikey
"""

import logging
from google import genai
from google.genai import types

from config import GOOGLE_API_KEY
from models.prompt import SYSTEM_PROMPT, build_user_prompt
from models.base import parse_picks, fallback_picks

logger = logging.getLogger(__name__)
MODEL_NAME = "gemini"

# Models to try in order (first one with quota wins)
CANDIDATE_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.5-pro",
]


def get_picks(market_context: str = "") -> tuple[list[dict], str]:
    if not GOOGLE_API_KEY:
        return fallback_picks(MODEL_NAME, "GOOGLE_API_KEY not set"), ""

    try:
        client = genai.Client(api_key=GOOGLE_API_KEY)

        raw = None
        last_error = None

        for model in CANDIDATE_MODELS:
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=build_user_prompt(market_context),
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        max_output_tokens=4096,
                        temperature=0.7,
                    ),
                )
                raw = response.text
                logger.info("Gemini using model: %s", model)
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
