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


def _call(client, system_prompt: str, messages: list, model: str, max_tokens: int) -> str:
    resp = client.messages.create(
        model=model, max_tokens=max_tokens, system=system_prompt, messages=messages
    )
    return "".join(
        block.text for block in resp.content if getattr(block, "type", None) == "text"
    )


def complete_json(
    system_prompt: str,
    user_content: str,
    model: str,
    max_tokens: int = 4096,
    retries: int = 1,
) -> dict[str, Any]:
    """Call Claude and return parsed JSON, retrying once on a parse failure.

    On the retry we feed the model's own (bad) output back with a firm nudge
    to return valid JSON only — this recovers the common case where the model
    wraps JSON in prose or truncates a code fence.
    """
    client = _get_client()
    logger.debug("Calling model {} ({} chars input)", model, len(user_content))
    messages = [{"role": "user", "content": user_content}]
    text = _call(client, system_prompt, messages, model, max_tokens)
    for attempt in range(retries + 1):
        try:
            return _extract_json(text)
        except (json.JSONDecodeError, ValueError):
            if attempt >= retries:
                logger.error("JSON parse failed after {} retries", retries)
                raise
            logger.warning("Bad JSON from model; retrying with a nudge")
            messages += [
                {"role": "assistant", "content": text},
                {"role": "user", "content": "That was not valid JSON. Return valid JSON only, no prose."},
            ]
            text = _call(client, system_prompt, messages, model, max_tokens)
