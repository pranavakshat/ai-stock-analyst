"""
models/copilot.py — Microsoft Copilot via Azure OpenAI.

Setup required:
1. Create an Azure account at https://portal.azure.com
2. Create an "Azure OpenAI" resource and deploy a gpt-4o model.
3. Copy the endpoint URL, API key, and deployment name into .env.

The openai SDK supports Azure via the AzureOpenAI client — no extra packages needed.
"""

import logging
from openai import AzureOpenAI

from config import AZURE_OPENAI_KEY, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOY
from models.prompt import SYSTEM_PROMPT, build_user_prompt
from models.base import parse_picks, fallback_picks

logger = logging.getLogger(__name__)
MODEL_NAME = "copilot"


def get_picks() -> tuple[list[dict], str]:
    if not AZURE_OPENAI_KEY or not AZURE_OPENAI_ENDPOINT:
        return fallback_picks(MODEL_NAME, "Azure OpenAI credentials not set"), ""

    try:
        client = AzureOpenAI(
            api_key=AZURE_OPENAI_KEY,
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_version="2024-02-01",
        )
        response = client.chat.completions.create(
            model=AZURE_OPENAI_DEPLOY,        # your deployment name in Azure
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": build_user_prompt()},
            ],
            max_tokens=1024,
            temperature=0.7,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        picks, raw = parse_picks(raw, MODEL_NAME)
        return picks, raw

    except Exception as exc:
        return fallback_picks(MODEL_NAME, str(exc)), str(exc)
