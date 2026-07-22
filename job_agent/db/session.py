"""Engine + session factory, plus small persistence helpers.

The audit log helper (:func:`log_action`) is used across the codebase so
every automated action is recorded with a timestamp.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from job_agent.config import settings
from job_agent.db.models import ActionLog, Base

_engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """Create all tables. Alembic owns migrations in production."""
    Base.metadata.create_all(_engine)


@contextmanager
def get_session() -> Iterator[Session]:
    """Context-managed session that commits on success and rolls back on error."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def log_action(action: str, detail: str | None = None) -> None:
    """Append a timestamped entry to the audit log."""
    with get_session() as session:
        session.add(ActionLog(action=action, detail=detail))
