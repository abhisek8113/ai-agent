"""SQLAlchemy ORM models: Job, Application, EmailThread, Reply, ActionLog.

Every meaningful state transition is captured so the dashboard can show a
full audit trail and the safety rails (rate limits, approvals) can be
enforced from persisted data rather than in-memory state.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """Timezone-aware UTC timestamp used as a column default."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class ApplicationStatus(str, enum.Enum):
    """Lifecycle of a single application, all human-gated before submit."""

    DISCOVERED = "discovered"
    TAILORED = "tailored"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SUBMITTED = "submitted"
    REJECTED = "rejected"
    SKIPPED = "skipped"


class EmailCategory(str, enum.Enum):
    """Categories produced by the email classifier agent."""

    RECRUITER_OUTREACH = "recruiter_outreach"
    INTERVIEW_INVITE = "interview_invite"
    ASSIGNMENT = "assignment"
    REJECTION = "rejection"
    OFFER = "offer"
    FOLLOW_UP_NEEDED = "follow_up_needed"
    JOB_ALERT = "job_alert"
    SPAM = "spam"
    OTHER = "other"


class Job(Base):
    """A scraped job posting. ``external_id`` + ``source`` is unique."""

    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_job_source_external"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    company: Mapped[str | None] = mapped_column(String(512))
    location: Mapped[str | None] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    applications: Mapped[list["Application"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class Application(Base):
    """A tailored application for a job, gated on human approval before submit."""

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus), default=ApplicationStatus.DISCOVERED, nullable=False
    )
    tailored_resume_md: Mapped[str | None] = mapped_column(Text)
    cover_letter_md: Mapped[str | None] = mapped_column(Text)
    match_score: Mapped[int | None] = mapped_column(Integer)
    gaps: Mapped[list | None] = mapped_column(JSON)
    keywords_used: Mapped[list | None] = mapped_column(JSON)
    approved_by_human: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    job: Mapped["Job"] = relationship(back_populates="applications")


class EmailThread(Base):
    """A classified inbound email thread."""

    __tablename__ = "email_threads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    gmail_thread_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False
    )
    sender: Mapped[str | None] = mapped_column(String(512))
    subject: Mapped[str | None] = mapped_column(Text)
    category: Mapped[EmailCategory] = mapped_column(
        Enum(EmailCategory), default=EmailCategory.OTHER, nullable=False
    )
    urgency: Mapped[str | None] = mapped_column(String(16))
    requires_reply: Mapped[bool] = mapped_column(Boolean, default=False)
    extracted: Mapped[dict | None] = mapped_column(JSON)
    summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    replies: Mapped[list["Reply"]] = relationship(
        back_populates="thread", cascade="all, delete-orphan"
    )


class Reply(Base):
    """A drafted reply. Always lands in Gmail Drafts — never auto-sent."""

    __tablename__ = "replies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[int] = mapped_column(
        ForeignKey("email_threads.id", ondelete="CASCADE"), nullable=False
    )
    intent: Mapped[str | None] = mapped_column(String(64))
    subject: Mapped[str | None] = mapped_column(Text)
    body_md: Mapped[str | None] = mapped_column(Text)
    tone_notes: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[int | None] = mapped_column(Integer)
    gmail_draft_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    thread: Mapped["EmailThread"] = relationship(back_populates="replies")


class ActionLog(Base):
    """Append-only audit log. Every automated action is timestamped here."""

    __tablename__ = "action_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
