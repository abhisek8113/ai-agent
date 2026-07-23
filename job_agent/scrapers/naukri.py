"""Naukri.com jobs scraper.

Naukri renders job tuples client-side, so we wait for the results container
before reading cards.
"""

from __future__ import annotations

import urllib.parse
from collections.abc import Iterable

from loguru import logger

from job_agent.scrapers._playwright import stealth_page
from job_agent.scrapers.base import BaseScraper, ScrapedJob

SEARCH_URL = "https://www.naukri.com/{kw}-jobs-in-{loc}"


class NaukriScraper(BaseScraper):
    """Scrape Data Scientist postings from Naukri."""

    source = "naukri"

    def fetch_jobs(self, keywords: str, location: str) -> Iterable[ScrapedJob]:
        slug_kw = urllib.parse.quote(keywords.lower().replace(" ", "-"))
        slug_loc = urllib.parse.quote(location.lower().replace(" ", "-"))
        url = SEARCH_URL.format(kw=slug_kw, loc=slug_loc)
        with stealth_page(self.random_user_agent()) as page:
            logger.info("[naukri] GET {}", url)
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_selector("div.srp-jobtuple-wrapper", timeout=15000)
            cards = page.query_selector_all("div.srp-jobtuple-wrapper")
            logger.info("[naukri] found {} cards", len(cards))
            for i, card in enumerate(cards):
                job = self._parse_card(card)
                logger.debug(
                    "[naukri] card {}: title={!r} company={!r} url={!r}",
                    i, job.title, job.company, job.url,
                )
                if not (job.title and job.title != "Unknown" and job.url):
                    logger.warning("[naukri] card {} skipped: missing fields", i)
                    continue
                yield job

    def _parse_card(self, card) -> ScrapedJob:
        def text(selector: str) -> str | None:
            el = card.query_selector(selector)
            return el.inner_text().strip() if el else None

        link = card.query_selector("a.title")
        href = link.get_attribute("href") if link else None
        external_id = card.get_attribute("data-job-id") or href or ""
        return ScrapedJob(
            source=self.source,
            external_id=external_id,
            title=text("a.title") or "Unknown",
            company=text("a.comp-name"),
            location=text("span.locWdth"),
            url=href,
        )
