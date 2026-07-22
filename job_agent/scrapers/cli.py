"""Small CLI so scrapers can be run individually, e.g. for a dry run.

Example:
    python -m job_agent.scrapers.cli linkedin --dry-run
"""

from __future__ import annotations

import argparse

from job_agent.db.session import init_db
from job_agent.scrapers.indeed import IndeedScraper
from job_agent.scrapers.linkedin import LinkedInScraper
from job_agent.scrapers.naukri import NaukriScraper

SCRAPERS = {
    "linkedin": LinkedInScraper,
    "naukri": NaukriScraper,
    "indeed": IndeedScraper,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a single job scraper.")
    parser.add_argument("source", choices=sorted(SCRAPERS))
    parser.add_argument("--keywords", default=None)
    parser.add_argument("--location", default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and log jobs without writing to the database.",
    )
    args = parser.parse_args()

    init_db()
    scraper = SCRAPERS[args.source](dry_run=args.dry_run)
    jobs = scraper.run(keywords=args.keywords, location=args.location)
    print(f"{args.source}: saved {len(jobs)} new jobs")


if __name__ == "__main__":
    main()
