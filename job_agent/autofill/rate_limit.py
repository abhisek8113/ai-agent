"""Daily application rate-limit guard, enforced from persisted state.

Counts applications that reached SUBMITTED today and refuses to exceed the
configured cap. Because it reads from the database, restarting the process
does not reset the counter.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select

from job_agent.config import settings
from job_agent.db.models import Application, ApplicationStatus
from job_agent.db.session import get_session


class RateLimitExceeded(RuntimeError):
    """Raised when the daily application cap has been reached."""


def submitted_today() -> int:
    """Count applications submitted since the start of today (UTC)."""
    start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    with get_session() as session:
        return session.scalar(
            select(func.count())
            .select_from(Application)
            .where(
                Application.status == ApplicationStatus.SUBMITTED,
                Application.submitted_at >= start,
            )
        )


def check_daily_limit() -> None:
    """Raise if submitting another application would exceed the daily cap."""
    count = submitted_today()
    if count >= settings.max_applications_per_day:
        raise RateLimitExceeded(
            f"Daily limit reached: {count}/{settings.max_applications_per_day}"
        )
