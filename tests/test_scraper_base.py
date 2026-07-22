"""Tests for BaseScraper: persistence, de-dup, dry-run, and the kill switch."""

from __future__ import annotations

import pytest

from job_agent.config import settings
from job_agent.db.models import Job
from job_agent.db.session import get_session
from job_agent.scrapers.base import BaseScraper, PausedError, ScrapedJob


class FakeScraper(BaseScraper):
    source = "fake"

    def __init__(self, jobs, **kw):
        super().__init__(**kw)
        self._jobs = jobs

    def fetch_jobs(self, keywords, location):
        yield from self._jobs


@pytest.fixture(autouse=True)
def _no_delay(monkeypatch):
    """Make polite_delay a no-op so tests run fast."""
    monkeypatch.setattr(BaseScraper, "polite_delay", lambda self: None)


def _jobs():
    return [
        ScrapedJob(source="fake", external_id="1", title="DS 1"),
        ScrapedJob(source="fake", external_id="2", title="DS 2"),
    ]


def test_run_persists_and_dedups(db):
    saved = FakeScraper(_jobs()).run()
    assert len(saved) == 2
    # Re-running should save nothing new (dedup on source+external_id).
    again = FakeScraper(_jobs()).run()
    assert again == []
    with get_session() as session:
        assert session.query(Job).count() == 2


def test_dry_run_writes_nothing(db):
    saved = FakeScraper(_jobs(), dry_run=True).run()
    assert saved == []
    with get_session() as session:
        assert session.query(Job).count() == 0


def test_kill_switch_blocks_run(db, monkeypatch):
    monkeypatch.setattr(settings, "pause_all", True)
    with pytest.raises(PausedError):
        FakeScraper(_jobs()).run()
