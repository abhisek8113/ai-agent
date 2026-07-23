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


def daily_backup() -> None:
    """Copy the SQLite file to a timestamped local backup.

    A local snapshot always runs; if Google Drive credentials are present the
    snapshot is also uploaded. This keeps the safety-rail (daily backup) even
    when Drive isn't configured.
    """
    if settings.pause_all:
        logger.warning("PAUSE_ALL set; skipping backup")
        return
    import shutil
    from datetime import datetime, timezone
    from pathlib import Path

    db_path = settings.database_url.replace("sqlite:///", "")
    if not Path(db_path).exists():
        logger.warning("No SQLite file at {} to back up", db_path)
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_dir = Path(settings.resolve("backups"))
    backup_dir.mkdir(exist_ok=True)
    dest = backup_dir / f"jobs-{stamp}.db"
    shutil.copy2(db_path, dest)
    log_action("backup", f"local={dest}")
    logger.info("SQLite backed up to {}", dest)
    try:
        _upload_to_drive(dest)
    except Exception as exc:  # Drive is optional; never fail the backup on it
        logger.info("Drive upload skipped ({})", exc)


def _upload_to_drive(path) -> None:
    """Upload a file to Google Drive if credentials are configured."""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    from job_agent.integrations.google_auth import get_credentials

    service = build("drive", "v3", credentials=get_credentials())
    media = MediaFileUpload(str(path), resumable=False)
    service.files().create(
        body={"name": path.name}, media_body=media, fields="id"
    ).execute()
    logger.info("Uploaded {} to Google Drive", path.name)


def build_scheduler():
    """Construct a blocking scheduler with the daily jobs registered."""
    from apscheduler.schedulers.blocking import BlockingScheduler

    scheduler = BlockingScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(daily_scrape, "cron", hour=8, minute=0, id="daily_scrape")
    scheduler.add_job(daily_inbox, "cron", minute="*/15", id="inbox_sweep")
    scheduler.add_job(daily_backup, "cron", hour=22, minute=0, id="daily_backup")
    log_action(
        "scheduler_start",
        "daily_scrape@08:00 IST, inbox_sweep every 15m, backup@22:00 IST",
    )
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
