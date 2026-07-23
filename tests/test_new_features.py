"""Tests for the prompt/model/agent enhancements added per the Codex sequence."""

from __future__ import annotations

import pytest

import job_agent.agents.classifier as classifier_mod
import job_agent.agents.client as client_mod
import job_agent.agents.tailor as tailor_mod
from job_agent.agents import prompts
from job_agent.db.models import Job, JobStatus
from job_agent.db.session import get_session


def test_prompt_aliases_and_json_line():
    for p in (prompts.TAILOR_SYSTEM, prompts.CLASSIFIER_SYSTEM,
              prompts.REPLIER_SYSTEM, prompts.SCREENING_SYSTEM):
        assert p.strip().endswith("Respond with JSON only, no prose.")


def test_job_status_defaults_new(db):
    with get_session() as session:
        session.add(Job(source="linkedin", external_id="1", title="DS"))
    with get_session() as session:
        assert session.query(Job).one().status == JobStatus.NEW


def test_tailor_output_clamps_score(monkeypatch):
    monkeypatch.setattr(tailor_mod, "complete_json", lambda *a, **k: {
        "tailored_resume_md": "r", "cover_letter_md": "c",
        "match_score": 250, "gaps": [], "keywords_used": [],
    })
    result = tailor_mod.tailor_resume("resume", "jd")
    assert result.match_score == 100  # clamped to 0-100


def test_client_retries_once_on_bad_json(monkeypatch):
    calls = {"n": 0}

    def fake_call(client, system, messages, model, max_tokens):
        calls["n"] += 1
        return "oops not json" if calls["n"] == 1 else '{"ok": true}'

    monkeypatch.setattr(client_mod, "_get_client", lambda: object())
    monkeypatch.setattr(client_mod, "_call", fake_call)
    out = client_mod.complete_json("sys", "user", model="m")
    assert out == {"ok": True}
    assert calls["n"] == 2  # first bad, retried once


def test_client_raises_after_retries(monkeypatch):
    monkeypatch.setattr(client_mod, "_get_client", lambda: object())
    monkeypatch.setattr(client_mod, "_call", lambda *a, **k: "still not json")
    with pytest.raises(Exception):
        client_mod.complete_json("sys", "user", model="m", retries=1)


def test_classifier_output_pydantic(monkeypatch):
    monkeypatch.setattr(classifier_mod, "complete_json", lambda *a, **k: {
        "category": "interview_invite", "urgency": "high", "requires_reply": True,
    })
    r = classifier_mod.classify_email("x", "y", "z")
    assert r.requires_reply is True
    assert r.category.value == "interview_invite"
