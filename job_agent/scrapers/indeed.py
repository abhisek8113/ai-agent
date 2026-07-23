"""Indeed jobs scraper."""

from __future__ import annotations

import urllib.parse
from collections.abc import Iterable

from loguru import logger

from job_agent.scrapers._playwright import stealth_page
from job_agent.scrapers.base import BaseScraper, ScrapedJob

SEARCH_URL = "https://in.indeed.com/jobs?q={kw}&l={loc}"


class IndeedScraper(BaseScraper):
    """Scrape Data Scientist postings from Indeed (India)."""

    source = "indeed"

    def fetch_jobs(self, keywords: str, location: str) -> Iterable[ScrapedJob]:
        url = SEARCH_URL.format(
            kw=urllib.parse.quote(keywords),
            loc=urllib.parse.quote(location),
        )
        with stealth_page(self.random_user_agent()) as page:
            logger.info("[indeed] GET {}", url)
            page.goto(url, wait_until="domcontentloaded")
            cards = page.query_selector_all("div.job_seen_beacon")
            logger.info("[indeed] found {} cards", len(cards))
            for i, card in enumerate(cards):
                job = self._parse_card(card)
                logger.debug(
                    "[indeed] card {}: title={!r} company={!r} url={!r}",
                    i, job.title, job.company, job.url,
                )
                if not (job.title and job.title != "Unknown" and job.url):
                    logger.warning("[indeed] card {} skipped: missing fields", i)
                    continue
                yield job

    def _parse_card(self, card) -> ScrapedJob:
        def text(selector: str) -> str | None:
            el = card.query_selector(selector)
            return el.inner_text().strip() if el else None

        link = card.query_selector("a[data-jk]")
        job_key = link.get_attribute("data-jk") if link else None
        href = (
            f"https://in.indeed.com/viewjob?jk={job_key}" if job_key else None
        )
        return ScrapedJob(
            source=self.source,
            external_id=job_key or (text("h2.jobTitle") or ""),
            title=text("h2.jobTitle") or "Unknown",
            company=text("span[data-testid='company-name']"),
            location=text("div[data-testid='text-location']"),
            url=href,
        )
