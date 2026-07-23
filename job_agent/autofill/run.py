"""Launch the human-gated autofill for a single application.

    python -m job_agent.autofill.run <application_id> [--dry-run]

Opens the job URL in a real browser, fills every field from your profile, and
STOPS at the submit button — you review and click submit yourself. The
dashboard's "1-click Apply" spawns this so the UI stays responsive.
"""

from __future__ import annotations

import argparse

from loguru import logger

from job_agent.autofill.form_bot import fill_application
from job_agent.db.models import Application, Job
from job_agent.db.session import get_session


def main() -> None:
    parser = argparse.ArgumentParser(description="Autofill one application (stops before submit)")
    parser.add_argument("application_id", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with get_session() as session:
        app = session.get(Application, args.application_id)
        if app is None:
            logger.error("No application {}", args.application_id)
            return
        job = session.get(Job, app.job_id)
        session.expunge(app)
        session.expunge(job)

    if not job.url:
        logger.error("Job {} has no URL to apply to", job.id)
        return
    fill_application(job, app, headless=False, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
