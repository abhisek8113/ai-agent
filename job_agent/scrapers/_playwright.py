"""Shared Playwright helpers: launch a stealthy browser context.

Isolated here so the concrete scrapers stay readable and so tests can
monkeypatch a single entry point.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from loguru import logger

from job_agent.config import settings


@contextmanager
def stealth_page(user_agent: str) -> Iterator[object]:
    """Yield a Playwright page with stealth applied and a rotated UA.

    Requires ``playwright`` and ``playwright-stealth`` to be installed and
    ``playwright install chromium`` to have been run.
    """
    from playwright.sync_api import sync_playwright

    try:
        from playwright_stealth import stealth_sync
    except ImportError:  # pragma: no cover - optional dependency
        stealth_sync = None
        logger.warning("playwright-stealth not installed; running without stealth")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=settings.headless)
        context = browser.new_context(user_agent=user_agent)
        page = context.new_page()
        if stealth_sync is not None:
            stealth_sync(page)
        try:
            yield page
        finally:
            context.close()
            browser.close()
