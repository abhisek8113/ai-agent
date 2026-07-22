"""Tests for the ORM models and de-duplication constraints."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from job_agent.db.models import (
    Application,
    ApplicationStatus,
    EmailCategory,
    EmailThread,
    Job,
)
from job_agent.db.session import get_session


def test_job_and_application_roundtrip(db):
    with get_session() as session:
        job = Job(source="linkedin", external_id="123", title="Data Scientist")
        session.add(job)
        session.flush()
        session.add(
            Application(job_id=job.id, status=ApplicationStatus.PENDING_APPROVAL)
        )

    with get_session() as session:
        stored = session.query(Application).one()
        assert stored.status == ApplicationStatus.PENDING_APPROVAL
        assert stored.job.title == "Data Scientist"


def test_duplicate_job_rejected(db):
    with get_session() as session:
        session.add(Job(source="naukri", external_id="dup", title="A"))

    with pytest.raises(IntegrityError):
        with get_session() as session:
            session.add(Job(source="naukri", external_id="dup", title="B"))


def test_email_thread_defaults(db):
    with get_session() as session:
        session.add(
            EmailThread(
                gmail_thread_id="t1",
                category=EmailCategory.JOB_ALERT,
            )
        )
    with get_session() as session:
        t = session.query(EmailThread).one()
        assert t.requires_reply is False
        assert t.category == EmailCategory.JOB_ALERT
