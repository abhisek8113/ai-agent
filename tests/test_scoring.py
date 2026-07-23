"""Tests for the local suitability scorer."""

from __future__ import annotations

from job_agent.scoring import suitability_score

PROFILE = {
    "role_target": "Data Scientist",
    "skills": ["Python", "SQL", "Machine Learning", "Power BI"],
}


def test_strong_match_scores_high():
    score = suitability_score(
        "Data Scientist",
        "We need Python, SQL, Machine Learning and Power BI skills.",
        PROFILE,
    )
    assert score >= 80


def test_weak_match_scores_low():
    score = suitability_score(
        "Warehouse Associate",
        "Lifting boxes, forklift certification required.",
        PROFILE,
    )
    assert score < 30


def test_title_role_alignment_matters():
    in_title = suitability_score("Senior Data Scientist", "generic text", PROFILE)
    not_in = suitability_score("Marketing Manager", "generic text", PROFILE)
    assert in_title > not_in


def test_empty_profile_returns_zero():
    assert suitability_score("Data Scientist", "Python SQL", {}) == 0
