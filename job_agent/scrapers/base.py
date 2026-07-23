"""Base scraper: rate limiting, user-agent rotation, stealth, persistence.

Concrete scrapers implement :meth:`fetch_jobs` and yield ``ScrapedJob``
records. The base class owns the polite-crawling behaviour (random delays,
UA rotation) and de-duplicated persistence into the ``jobs`` table.
"""

from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass

from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from job_agent.config import settings
from job_agent.db.models import Job
from job_agent.db.session import get_session, log_action

# A small pool of realistic desktop user agents to rotate between requests.
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
    "Gecko/20100101 Firefox/125.0",
]


def _strip_query(value: str | None) -> str | None:
    """Drop everything after '?' so tracking params don't defeat dedup.

    LinkedIn/Naukri/Indeed append per-session query strings to job URLs, which
    makes the same posting look unique every scrape. Normalising to the path
    keeps dedup stable.
    """
    if not value:
        return value
    return value.split("?", 1)[0]


class PausedError(RuntimeError):
    """Raised when the PAUSE_ALL kill switch is engaged."""


@dataclass
class ScrapedJob:
    """A single normalised job posting from any source."""

    source: str
    external_id: str
    title: str
    company: str | None = None
    location: str | None = None
    url: str | None = None
    description: str | None = None


class BaseScraper(ABC):
    """Common scraping behaviour shared by all job boards."""

    #: Short identifier persisted in ``Job.source``.
    source: str = "base"

    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run

    def random_user_agent(self) -> str:
        """Pick a random user agent for the next browser context."""
        return random.choice(USER_AGENTS)

    def polite_delay(self) -> None:
        """Sleep a random interval between actions to respect rate limits."""
        low, high = settings.min_action_delay, settings.max_action_delay
        delay = random.uniform(low, high)
        logger.debug("Sleeping {:.1f}s between actions", delay)
        time.sleep(delay)

    def _check_kill_switch(self) -> None:
        """Abort immediately if the global pause flag is set."""
        if settings.pause_all:
            raise PausedError("PAUSE_ALL is set; scraping halted.")

    @abstractmethod
    def fetch_jobs(self, keywords: str, location: str) -> Iterable[ScrapedJob]:
        """Yield jobs for the given search. Implemented per board."""
        raise NotImplementedError

    def run(
        self, keywords: str | None = None, location: str | None = None
    ) -> list[Job]:
        """Fetch and persist jobs, de-duplicating on (source, external_id)."""
        self._check_kill_switch()
        keywords = keywords or settings.job_search_keywords
        location = location or settings.job_search_location
        logger.info("[{}] scraping '{}' in '{}'", self.source, keywords, location)

        saved = kept = dropped = 0
        saved_jobs: list[Job] = []
        # Note: polite_delay() is NOT called per card — a single search page is
        # one navigation. Delays belong between page navigations (handled by
        # the pipeline between scrapers, and inside a scraper if it paginates).
        for i, scraped in enumerate(self.fetch_jobs(keywords, location)):
            if i >= settings.max_cards_per_run:
                logger.info(
                    "[{}] hit MAX_CARDS_PER_RUN={}, stopping",
                    self.source, settings.max_cards_per_run,
                )
                break
            scraped.url = _strip_query(scraped.url)
            scraped.external_id = _strip_query(scraped.external_id) or scraped.url or ""

            if self.dry_run:
                logger.info(
                    "[dry-run] kept: {} @ {} -> {}",
                    scraped.title, scraped.company, scraped.url,
                )
                kept += 1
                continue

            job = self._persist(scraped)
            if job is not None:
                saved_jobs.append(job)
                saved += 1
                kept += 1
            else:
                dropped += 1  # duplicate — reason already logged in _persist

        logger.info(
            "[{}] cards processed -> saved={} duplicates_dropped={} kept={}",
            self.source, saved, dropped, kept,
        )
        log_action(
            "scrape",
            f"source={self.source} keywords={keywords} saved={saved} dropped={dropped}",
        )
        return saved_jobs

    def _persist(self, scraped: ScrapedJob) -> Job | None:
        """Insert a job, ignoring duplicates already stored."""
        with get_session() as session:
            existing = session.scalar(
                select(Job).where(
                    Job.source == scraped.source,
                    Job.external_id == scraped.external_id,
                )
            )
            if existing is not None:
                logger.debug(
                    "[{}] skipped: duplicate external_id={}",
                    self.source, scraped.external_id,
                )
                return None
            job = Job(
                source=scraped.source,
                external_id=scraped.external_id,
                title=scraped.title,
                company=scraped.company,
                location=scraped.location,
                url=scraped.url,
                description=scraped.description,
            )
            session.add(job)
            try:
                session.flush()
            except IntegrityError:
                session.rollback()
                logger.debug(
                    "[{}] skipped: duplicate (race) external_id={}",
                    self.source, scraped.external_id,
                )
                return None
            session.expunge(job)
            return job
