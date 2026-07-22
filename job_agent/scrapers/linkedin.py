"""LinkedIn jobs scraper.

Uses the public guest jobs endpoint which returns server-rendered cards and
does not require login. Selectors are centralised so they can be updated in
one place when LinkedIn changes its markup.
"""

from __future__ import annotations

import urllib.parse
from collections.abc import Iterable

from loguru import logger

from job_agent.scrapers._playwright import stealth_page
from job_agent.scrapers.base import BaseScraper, ScrapedJob

SEARCH_URL = "https://www.linkedin.com/jobs/search/?keywords={kw}&location={loc}"


class LinkedInScraper(BaseScraper):
    """Scrape Data Scientist postings from LinkedIn's guest job search."""

    source = "linkedin"

    def fetch_jobs(self, keywords: str, location: str) -> Iterable[ScrapedJob]:
        url = SEARCH_URL.format(
            kw=urllib.parse.quote(keywords),
            loc=urllib.parse.quote(location),
        )
        with stealth_page(self.random_user_agent()) as page:
            logger.info("[linkedin] GET {}", url)
            page.goto(url, wait_until="domcontentloaded")
            cards = page.query_selector_all("div.base-card")
            logger.info("[linkedin] found {} cards", len(cards))
            for card in cards:
                yield self._parse_card(card)

    def _parse_card(self, card) -> ScrapedJob:
        """Extract a job from one search-result card element."""
        def text(selector: str) -> str | None:
            el = card.query_selector(selector)
            return el.inner_text().strip() if el else None

        link = card.query_selector("a.base-card__full-link")
        href = link.get_attribute("href") if link else None
        external_id = card.get_attribute("data-entity-urn") or href or ""
        return ScrapedJob(
            source=self.source,
            external_id=external_id.split(":")[-1] if external_id else href or "",
            title=text("h3.base-search-card__title") or "Unknown",
            company=text("h4.base-search-card__subtitle"),
            location=text("span.job-search-card__location"),
            url=href,
        )
