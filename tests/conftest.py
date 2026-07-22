"""Shared pytest fixtures: an isolated in-memory-ish SQLite database."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import job_agent.db.session as session_module
from job_agent.db.models import Base


@pytest.fixture()
def db(tmp_path, monkeypatch):
    """Point the session module at a throwaway SQLite file for each test."""
    url = f"sqlite:///{tmp_path/'test.db'}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(session_module, "_engine", engine)
    monkeypatch.setattr(session_module, "SessionLocal", TestSession)
    yield engine
