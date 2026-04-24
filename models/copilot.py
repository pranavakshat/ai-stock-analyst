"""
models/copilot.py — Microsoft Copilot via Azure OpenAI (optional, disabled by default).

To enable:
  1. Create an Azure account at https://portal.azure.com
  2. Create an "Azure OpenAI" resource and deploy a gpt-4o model.
  3. Add to Railway env vars:
       AZURE_OPENAI_KEY=<your-key>
       AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/
       AZURE_OPENAI_DEPLOY=<deployment-name>
  4. Uncomment the "copilot" entry in models/runner.py ADAPTERS.

The openai SDK supports Azure natively — no extra packages needed.
"""

import logging
from openai import AzureOpenAI

from config import AZURE_OPENAI_KEY, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOY
from models.prompt import DAY_SYSTEM_PROMPT, build_day_user_prompt
from models.base import parse_picks, fallback_picks

logger = logging.getLogger(__name__)
MODEL_NAME = "copilot"


def get_picks(market_context: str = "",
              system_prompt_override: str | None = None,
              user_prompt_builder=None) -> tuple[list[dict], str]:
    """Query Azure OpenAI and return (picks, raw_response)."""
    if not AZURE_OPENAI_KEY or not AZURE_OPENAI_ENDPOINT:
        return fallback_picks(MODEL_NAME, "Azure OpenAI credentials not configured"), ""

    system  = system_prompt_override or DAY_SYSTEM_PROMPT
    builder = user_prompt_builder or build_day_user_prompt

    try:
        client = AzureOpenAI(
            api_key=AZURE_OPENAI_KEY,
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_version="2024-02-01",
            timeout=120.0,
        )
        response = client.chat.completions.create(
            model=AZURE_OPENAI_DEPLOY,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": builder(market_context)},
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
