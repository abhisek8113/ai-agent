"""APScheduler daily jobs: scrape boards and process the inbox.

Respects the PAUSE_ALL kill switch before running any job.
"""

from __future__ import annotations

from loguru import logger

from job_agent.config import settings
from job_agent.db.session import init_db, log_action
from job_agent.pipeline import process_inbox, scrape_all


def _guarded(func) -> None:
    """Run a job unless the kill switch is engaged."""
    if settings.pause_all:
        logger.warning("PAUSE_ALL set; skipping scheduled job {}", func.__name__)
        return
    func()


def daily_scrape() -> None:
    _guarded(scrape_all)


def daily_inbox() -> None:
    _guarded(process_inbox)


def build_scheduler():
    """Construct a blocking scheduler with the daily jobs registered."""
    from apscheduler.schedulers.blocking import BlockingScheduler

    scheduler = BlockingScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(daily_scrape, "cron", hour=8, minute=0, id="daily_scrape")
    scheduler.add_job(daily_inbox, "cron", hour="8-20/2", id="inbox_sweep")
    log_action("scheduler_start", "daily_scrape@08:00, inbox_sweep every 2h")
    return scheduler


def main() -> None:
    init_db()
    scheduler = build_scheduler()
    logger.info("Scheduler started. Ctrl-C to exit.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
