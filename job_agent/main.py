"""Command-line entry point for the Job Application Agent.

Commands:
    python -m job_agent.main init                 # create tables
    python -m job_agent.main scrape               # scrape all boards once
    python -m job_agent.main mail                 # poll Gmail + classify once
    python -m job_agent.main tailor <job_id>      # tailor a single job
    python -m job_agent.main dashboard            # launch the Streamlit UI
    python -m job_agent.main serve                # run APScheduler in foreground
    python -m job_agent.main all                  # scrape + tailor + classify
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from loguru import logger

from job_agent.config import settings
from job_agent.db.session import init_db
from job_agent.pipeline import process_inbox, scrape_all, tailor_new_jobs


def _paused(cmd: str) -> bool:
    if settings.pause_all and cmd not in ("init", "dashboard"):
        logger.warning("PAUSE_ALL is set — '{}' is a no-op. Unset it in .env.", cmd)
        return True
    return False


def cmd_tailor(job_id: int | None) -> None:
    """Tailor a specific job (by id) or fall back to the pending queue."""
    from job_agent.agents.tailor import tailor_for_job
    from job_agent.db.models import Application, ApplicationStatus, Job, JobStatus
    from job_agent.db.session import get_session
    from job_agent.pipeline import load_master_resume

    if job_id is None:
        logger.info("Created {} tailored applications.", tailor_new_jobs())
        return

    resume = load_master_resume()
    with get_session() as session:
        job = session.get(Job, job_id)
        if job is None:
            logger.error("No job with id {}", job_id)
            return
        data = tailor_for_job(job, resume)
        session.add(Application(
            job_id=job.id, status=ApplicationStatus.PENDING_APPROVAL,
            tailored_resume_md=data["tailored_resume_md"], cover_letter_md=data["cover_letter_md"],
            match_score=data["match_score"], gaps=data["gaps"], keywords_used=data["keywords_used"],
        ))
        job.status = JobStatus.TAILORED
        job.match_score = data["match_score"]
    logger.info("Tailored job {} — match {}%", job_id, data["match_score"])


def cmd_dashboard() -> None:
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", "job_agent/dashboard/app.py"],
        check=False,
    )


def cmd_serve() -> None:
    from job_agent.scheduler import main as serve_main

    serve_main()


def main() -> None:
    parser = argparse.ArgumentParser(description="Job Application Agent")
    parser.add_argument(
        "command",
        choices=["init", "scrape", "mail", "inbox", "tailor", "dashboard", "serve", "all"],
    )
    parser.add_argument("job_id", nargs="?", type=int, default=None,
                        help="job id (only for the 'tailor' command)")
    args = parser.parse_args()

    if _paused(args.command):
        return

    if args.command != "dashboard":
        init_db()

    if args.command == "init":
        logger.info("Database initialised.")
    elif args.command == "scrape":
        logger.info("Saved {} new jobs.", scrape_all())
    elif args.command in ("mail", "inbox"):
        logger.info("Handled {} emails.", process_inbox())
    elif args.command == "tailor":
        cmd_tailor(args.job_id)
    elif args.command == "dashboard":
        cmd_dashboard()
    elif args.command == "serve":
        cmd_serve()
    elif args.command == "all":
        scrape_all()
        tailor_new_jobs()
        process_inbox()


if __name__ == "__main__":
    main()
