"""Google Calendar integration: propose free interview slots.

Reads busy periods via the freebusy API and returns candidate open slots the
user can offer to a recruiter. It does not create events automatically.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone

from loguru import logger

from job_agent.integrations.google_auth import get_credentials


@dataclass
class Slot:
    """A proposed free interview slot."""

    start: datetime
    end: datetime


def _service():
    from googleapiclient.discovery import build

    return build("calendar", "v3", credentials=get_credentials())


def _working_windows(
    days: int, work_start: int, work_end: int
) -> list[tuple[datetime, datetime]]:
    """Generate daily working-hour windows for the next ``days`` days."""
    windows: list[tuple[datetime, datetime]] = []
    today = datetime.now(timezone.utc).date()
    for offset in range(1, days + 1):
        day = today + timedelta(days=offset)
        if day.weekday() >= 5:  # skip weekends
            continue
        start = datetime.combine(day, time(work_start), tzinfo=timezone.utc)
        end = datetime.combine(day, time(work_end), tzinfo=timezone.utc)
        windows.append((start, end))
    return windows


def propose_slots(
    days: int = 5,
    duration_minutes: int = 45,
    work_start: int = 4,  # ~09:30 IST in UTC
    work_end: int = 12,
    max_slots: int = 5,
) -> list[Slot]:
    """Return up to ``max_slots`` free slots over the next working days."""
    service = _service()
    windows = _working_windows(days, work_start, work_end)
    if not windows:
        return []

    body = {
        "timeMin": windows[0][0].isoformat(),
        "timeMax": windows[-1][1].isoformat(),
        "items": [{"id": "primary"}],
    }
    resp = service.freebusy().query(body=body).execute()
    busy = [
        (
            datetime.fromisoformat(b["start"]),
            datetime.fromisoformat(b["end"]),
        )
        for b in resp["calendars"]["primary"]["busy"]
    ]

    slots: list[Slot] = []
    step = timedelta(minutes=duration_minutes)
    for win_start, win_end in windows:
        cursor = win_start
        while cursor + step <= win_end and len(slots) < max_slots:
            slot_end = cursor + step
            overlaps = any(bs < slot_end and cursor < be for bs, be in busy)
            if not overlaps:
                slots.append(Slot(start=cursor, end=slot_end))
            cursor = slot_end
    logger.info("Proposed {} free slots", len(slots))
    return slots
