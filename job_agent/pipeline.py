"""High-level orchestration tying scrapers, agents, and integrations together.

Kept separate from ``main.py`` and ``scheduler.py`` so both entry points and
tests can call the same functions.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from loguru import logger
from sqlalchemy import select

from job_agent.agents.classifier import classify_email
from job_agent.agents.tailor import tailor_resume
from job_agent.config import settings
from job_agent.db.models import (
    Application,
    ApplicationStatus,
    EmailThread,
    Job,
)
from job_agent.db.session import get_session, log_action
from job_agent.scrapers.apis import API_SCRAPERS
from job_agent.scrapers.indeed import IndeedScraper
from job_agent.scrapers.linkedin import LinkedInScraper
from job_agent.scrapers.naukri import NaukriScraper

# HTML scrapers first, then the reliable API-based sources (10+ total).
SCRAPERS = (LinkedInScraper, NaukriScraper, IndeedScraper, *API_SCRAPERS)


def load_candidate_profile() -> dict:
    """Load the candidate profile YAML, or an empty dict if absent."""
    path = Path(settings.resolve(settings.candidate_profile_file))
    if not path.exists():
        logger.warning("Candidate profile not found at {}", path)
        return {}
    return yaml.safe_load(path.read_text()) or {}


def load_master_resume() -> str:
    """Load the master resume Markdown, or an empty string if absent."""
    path = Path(settings.resolve(settings.master_resume_file))
    return path.read_text() if path.exists() else ""


def scrape_all() -> int:
    """Run every scraper and return the total number of new jobs saved."""
    if settings.pause_all:
        logger.warning("PAUSE_ALL set; scrape_all skipped")
        return 0
    total = 0
    for idx, scraper_cls in enumerate(SCRAPERS):
        scraper = scraper_cls()
        if idx > 0:
            # Random delay between board navigations (not between cards).
            scraper.polite_delay()
        try:
            saved = scraper.run()
            total += len(saved)
        except Exception as exc:  # keep other boards running if one fails
            logger.exception("Scraper {} failed: {}", scraper_cls.source, exc)
    log_action("scrape_all", f"total_new={total}")
    return total


def tailor_new_jobs(limit: int = 20) -> int:
    """Create tailored applications for discovered jobs without one yet."""
    resume = load_master_resume()
    if not resume:
        logger.warning("No master resume; skipping tailoring")
        return 0

    created = 0
    with get_session() as session:
        applied_job_ids = select(Application.job_id)
        jobs = session.scalars(
            select(Job).where(Job.id.not_in(applied_job_ids)).limit(limit)
        ).all()

    for job in jobs:
        try:
            result = tailor_resume(resume, job.description or job.title)
        except Exception as exc:
            logger.exception("Tailoring failed for job {}: {}", job.id, exc)
            continue
        # Render the freshly tailored resume to a file, one per job.
        try:
            from job_agent.render import render_resume

            render_resume(result.tailored_resume_md, job.company or "", job.title or "", job.id)
        except Exception as exc:
            logger.warning("Resume render failed for job {}: {}", job.id, exc)

        with get_session() as session:
            session.add(
                Application(
                    job_id=job.id,
                    status=ApplicationStatus.PENDING_APPROVAL,
                    tailored_resume_md=result.tailored_resume_md,
                    cover_letter_md=result.cover_letter_md,
                    match_score=result.match_score,
                    gaps=result.gaps,
                    keywords_used=result.keywords_used,
                )
            )
        created += 1
    log_action("tailor_new_jobs", f"created={created}")
    return created


def process_inbox(max_results: int = 20) -> int:
    """Classify unread emails and persist new threads. Returns count handled."""
    if settings.pause_all:
        logger.warning("PAUSE_ALL set; process_inbox skipped")
        return 0

    from job_agent.integrations.gmail import fetch_unread

    handled = 0
    for msg in fetch_unread(max_results=max_results):
        with get_session() as session:
            existing = session.scalar(
                select(EmailThread).where(
                    EmailThread.gmail_thread_id == msg.thread_id
                )
            )
            if existing is not None:
                continue
        result = classify_email(msg.sender, msg.subject, msg.body)
        with get_session() as session:
            session.add(
                EmailThread(
                    gmail_thread_id=msg.thread_id,
                    sender=msg.sender,
                    subject=msg.subject,
                    category=result.category,
                    urgency=result.urgency,
                    requires_reply=result.requires_reply,
                    extracted=result.extracted,
                    summary=result.summary,
                )
            )
        handled += 1
    log_action("process_inbox", f"handled={handled}")
    return handled
