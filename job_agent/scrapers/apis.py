"""API-based job sources.

Unlike the HTML scrapers (LinkedIn/Naukri/Indeed), these hit stable JSON
endpoints, so they rarely break. Several need no credentials at all; the
per-company sources (Greenhouse, Lever) and Adzuna are configured via .env.

Together with the three HTML scrapers this gives 10+ sources:
    HTML : linkedin, naukri, indeed
    API  : remotive, remoteok, arbeitnow, jobicy, greenhouse, lever, adzuna
"""

from __future__ import annotations

from collections.abc import Iterable

import requests
from loguru import logger

from job_agent.config import settings
from job_agent.scrapers.base import BaseScraper, ScrapedJob

TIMEOUT = 20
HEADERS = {"User-Agent": "job-agent/1.0 (+personal use)"}


def _get_json(url: str, params: dict | None = None):
    resp = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _matches(keywords: str, *fields: str) -> bool:
    """True if any keyword token appears in the concatenated fields."""
    hay = " ".join(f.lower() for f in fields if f)
    return all(tok in hay for tok in keywords.lower().split())


class RemotiveScraper(BaseScraper):
    """Remotive — public remote-jobs API, no key required."""

    source = "remotive"

    def fetch_jobs(self, keywords: str, location: str) -> Iterable[ScrapedJob]:
        data = _get_json("https://remotive.com/api/remote-jobs", {"search": keywords})
        for j in data.get("jobs", []):
            yield ScrapedJob(
                source=self.source, external_id=str(j.get("id")),
                title=j.get("title", "Unknown"), company=j.get("company_name"),
                location=j.get("candidate_required_location"),
                url=j.get("url"), description=j.get("description"),
            )


class RemoteOKScraper(BaseScraper):
    """RemoteOK — public JSON feed, no key required."""

    source = "remoteok"

    def fetch_jobs(self, keywords: str, location: str) -> Iterable[ScrapedJob]:
        data = _get_json("https://remoteok.com/api")
        for j in data:
            if not isinstance(j, dict) or "position" not in j:
                continue  # first element is a legal notice
            if not _matches(keywords, j.get("position", ""), " ".join(j.get("tags", []))):
                continue
            yield ScrapedJob(
                source=self.source, external_id=str(j.get("id")),
                title=j.get("position", "Unknown"), company=j.get("company"),
                location=j.get("location"), url=j.get("url"),
                description=j.get("description"),
            )


class ArbeitnowScraper(BaseScraper):
    """Arbeitnow — public job-board API, no key required."""

    source = "arbeitnow"

    def fetch_jobs(self, keywords: str, location: str) -> Iterable[ScrapedJob]:
        data = _get_json("https://www.arbeitnow.com/api/job-board-api")
        for j in data.get("data", []):
            if not _matches(keywords, j.get("title", ""), j.get("description", "")):
                continue
            yield ScrapedJob(
                source=self.source, external_id=str(j.get("slug")),
                title=j.get("title", "Unknown"), company=j.get("company_name"),
                location=j.get("location"), url=j.get("url"),
                description=j.get("description"),
            )


class JobicyScraper(BaseScraper):
    """Jobicy — public remote-jobs API, no key required."""

    source = "jobicy"

    def fetch_jobs(self, keywords: str, location: str) -> Iterable[ScrapedJob]:
        data = _get_json(
            "https://jobicy.com/api/v2/remote-jobs",
            {"count": 50, "tag": keywords},
        )
        for j in data.get("jobs", []):
            yield ScrapedJob(
                source=self.source, external_id=str(j.get("id")),
                title=j.get("jobTitle", "Unknown"), company=j.get("companyName"),
                location=j.get("jobGeo"), url=j.get("url"),
                description=j.get("jobExcerpt"),
            )


class GreenhouseScraper(BaseScraper):
    """Greenhouse — per-company career portals via board token (no key)."""

    source = "greenhouse"

    def fetch_jobs(self, keywords: str, location: str) -> Iterable[ScrapedJob]:
        tokens = [t.strip() for t in settings.greenhouse_companies.split(",") if t.strip()]
        for token in tokens:
            try:
                data = _get_json(
                    f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
                    {"content": "true"},
                )
            except requests.RequestException as exc:
                logger.warning("[greenhouse] {} failed: {}", token, exc)
                continue
            for j in data.get("jobs", []):
                title = j.get("title", "")
                if not _matches(keywords, title, j.get("content", "")):
                    continue
                yield ScrapedJob(
                    source=self.source, external_id=f"{token}:{j.get('id')}",
                    title=title or "Unknown", company=token,
                    location=(j.get("location") or {}).get("name"),
                    url=j.get("absolute_url"), description=j.get("content"),
                )


class LeverScraper(BaseScraper):
    """Lever — per-company career portals via company slug (no key)."""

    source = "lever"

    def fetch_jobs(self, keywords: str, location: str) -> Iterable[ScrapedJob]:
        slugs = [s.strip() for s in settings.lever_companies.split(",") if s.strip()]
        for slug in slugs:
            try:
                data = _get_json(f"https://api.lever.co/v0/postings/{slug}", {"mode": "json"})
            except requests.RequestException as exc:
                logger.warning("[lever] {} failed: {}", slug, exc)
                continue
            for j in data:
                title = j.get("text", "")
                if not _matches(keywords, title, j.get("descriptionPlain", "")):
                    continue
                yield ScrapedJob(
                    source=self.source, external_id=str(j.get("id")),
                    title=title or "Unknown", company=slug,
                    location=(j.get("categories") or {}).get("location"),
                    url=j.get("hostedUrl"), description=j.get("descriptionPlain"),
                )


class AdzunaScraper(BaseScraper):
    """Adzuna — aggregator across many boards (free app id/key required)."""

    source = "adzuna"

    def fetch_jobs(self, keywords: str, location: str) -> Iterable[ScrapedJob]:
        if not (settings.adzuna_app_id and settings.adzuna_app_key):
            logger.info("[adzuna] no credentials set; skipping")
            return
        country = settings.adzuna_country
        data = _get_json(
            f"https://api.adzuna.com/v1/api/jobs/{country}/search/1",
            {
                "app_id": settings.adzuna_app_id, "app_key": settings.adzuna_app_key,
                "what": keywords, "where": location, "results_per_page": 25,
            },
        )
        for j in data.get("results", []):
            yield ScrapedJob(
                source=self.source, external_id=str(j.get("id")),
                title=j.get("title", "Unknown"),
                company=(j.get("company") or {}).get("display_name"),
                location=(j.get("location") or {}).get("display_name"),
                url=j.get("redirect_url"), description=j.get("description"),
            )


# Key-free sources always run; per-company/keyed ones run when configured.
API_SCRAPERS = [
    RemotiveScraper, RemoteOKScraper, ArbeitnowScraper, JobicyScraper,
    GreenhouseScraper, LeverScraper, AdzunaScraper,
]
