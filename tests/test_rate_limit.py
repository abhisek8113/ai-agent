"""Tests for the daily application rate-limit guard."""

from __future__ import annotations

import pytest

from job_agent.autofill.rate_limit import (
    RateLimitExceeded,
    check_daily_limit,
    submitted_today,
)
from job_agent.config import settings
from job_agent.db.models import Application, ApplicationStatus, Job
from job_agent.db.models import utcnow
from job_agent.db.session import get_session


def _make_submitted(n: int) -> None:
    with get_session() as session:
        for i in range(n):
            job = Job(source="fake", external_id=str(i), title="DS")
            session.add(job)
            session.flush()
            session.add(
                Application(
                    job_id=job.id,
                    status=ApplicationStatus.SUBMITTED,
                    submitted_at=utcnow(),
                )
            )


def test_counts_submitted_today(db):
    _make_submitted(3)
    assert submitted_today() == 3


def test_check_raises_at_cap(db, monkeypatch):
    monkeypatch.setattr(settings, "max_applications_per_day", 2)
    _make_submitted(2)
    with pytest.raises(RateLimitExceeded):
        check_daily_limit()


def test_check_ok_below_cap(db, monkeypatch):
    monkeypatch.setattr(settings, "max_applications_per_day", 20)
    _make_submitted(1)
    check_daily_limit()  # should not raise
