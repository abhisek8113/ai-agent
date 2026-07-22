"""Tests for robust JSON extraction from model responses."""

from __future__ import annotations

import pytest

from job_agent.agents.client import _extract_json


def test_plain_json():
    assert _extract_json('{"a": 1}') == {"a": 1}


def test_fenced_json():
    text = 'Here you go:\n```json\n{"a": 1, "b": [2, 3]}\n```\nThanks!'
    assert _extract_json(text) == {"a": 1, "b": [2, 3]}


def test_json_with_surrounding_prose():
    text = 'Sure. {"category": "job_alert"} is my answer.'
    assert _extract_json(text) == {"category": "job_alert"}


def test_invalid_raises():
    with pytest.raises(Exception):
        _extract_json("no json here")
