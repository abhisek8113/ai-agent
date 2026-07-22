"""Tests for the agent wrappers with the Claude client mocked out."""

from __future__ import annotations

import pytest

import job_agent.agents.classifier as classifier_mod
import job_agent.agents.replier as replier_mod
import job_agent.agents.tailor as tailor_mod
from job_agent.db.models import EmailCategory


def test_tailor_parses_result(monkeypatch):
    monkeypatch.setattr(
        tailor_mod,
        "complete_json",
        lambda *a, **k: {
            "tailored_resume_md": "# R",
            "cover_letter_md": "Hook...",
            "match_score": 82,
            "gaps": ["Spark"],
            "keywords_used": ["Python", "ML"],
        },
    )
    result = tailor_mod.tailor_resume("resume", "jd")
    assert result.match_score == 82
    assert result.gaps == ["Spark"]


def test_classifier_maps_category(monkeypatch):
    monkeypatch.setattr(
        classifier_mod,
        "complete_json",
        lambda *a, **k: {
            "category": "recruiter_outreach",
            "urgency": "high",
            "requires_reply": True,
            "extracted": {"company": "Acme"},
            "summary": "Recruiter reached out",
        },
    )
    result = classifier_mod.classify_email("r@acme.com", "Hi", "Interested?")
    assert result.category == EmailCategory.RECRUITER_OUTREACH
    assert result.requires_reply is True


def test_classifier_unknown_category_falls_back(monkeypatch):
    monkeypatch.setattr(
        classifier_mod,
        "complete_json",
        lambda *a, **k: {"category": "banana", "urgency": "low"},
    )
    result = classifier_mod.classify_email("x", "y", "z")
    assert result.category == EmailCategory.OTHER


def test_reply_low_confidence_flags_rewrite(monkeypatch):
    monkeypatch.setattr(
        replier_mod,
        "complete_json",
        lambda *a, **k: {
            "subject": "Re: Interview",
            "body_md": "Sure.",
            "tone_notes": "warm",
            "confidence": 55,
        },
    )
    draft = replier_mod.draft_reply("thread", "profile", "accept_interview")
    assert draft.needs_human_rewrite is True


def test_reply_rejects_unknown_intent():
    with pytest.raises(ValueError):
        replier_mod.draft_reply("thread", "profile", "bogus_intent")
