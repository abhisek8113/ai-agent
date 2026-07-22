"""Thin wrapper around the Anthropic SDK that returns parsed JSON.

Centralises client construction, model selection, and robust JSON extraction
so each agent stays focused on its prompt and inputs.
"""

from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger

from job_agent.config import settings

_client = None


def _get_client():
    """Lazily construct the Anthropic client (keeps imports cheap in tests)."""
    global _client
    if _client is None:
        from anthropic import Anthropic

        _client = Anthropic(api_key=settings.anthropic_api_key)
    return _client


def _extract_json(text: str) -> dict[str, Any]:
    """Parse the first JSON object from a model response.

    Models occasionally wrap JSON in prose or code fences; we strip those
    before parsing and fall back to a brace-matched slice.
    """
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def complete_json(
    system_prompt: str,
    user_content: str,
    model: str,
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Call Claude with a system prompt and return the parsed JSON response."""
    client = _get_client()
    logger.debug("Calling model {} ({} chars input)", model, len(user_content))
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    text = "".join(
        block.text for block in resp.content if getattr(block, "type", None) == "text"
    )
    return _extract_json(text)
