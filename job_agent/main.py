"""Command-line entry point for one-off runs of the pipeline.

Examples:
    python -m job_agent.main init          # create tables
    python -m job_agent.main scrape        # scrape all boards once
    python -m job_agent.main tailor        # tailor pending jobs
    python -m job_agent.main inbox         # classify unread emails
    python -m job_agent.main all           # scrape + tailor + inbox
"""

from __future__ import annotations

import argparse

from loguru import logger

from job_agent.config import settings
from job_agent.db.session import init_db
from job_agent.pipeline import process_inbox, scrape_all, tailor_new_jobs


def main() -> None:
    parser = argparse.ArgumentParser(description="Job Application Agent")
    parser.add_argument(
        "command",
        choices=["init", "scrape", "tailor", "inbox", "all"],
    )
    args = parser.parse_args()

    if settings.pause_all and args.command != "init":
        logger.warning("PAUSE_ALL is set — nothing will run. Unset it in .env.")
        return

    init_db()

    if args.command == "init":
        logger.info("Database initialised.")
    elif args.command == "scrape":
        logger.info("Saved {} new jobs.", scrape_all())
    elif args.command == "tailor":
        logger.info("Created {} tailored applications.", tailor_new_jobs())
    elif args.command == "inbox":
        logger.info("Handled {} emails.", process_inbox())
    elif args.command == "all":
        scrape_all()
        tailor_new_jobs()
        process_inbox()


if __name__ == "__main__":
    main()
