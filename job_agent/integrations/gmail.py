"""Gmail integration: read the inbox and write drafts.

Safety rail: this module can create Gmail *drafts* only. It deliberately
exposes no send capability — replies always land in Drafts for human review.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from email.mime.text import MIMEText

from loguru import logger

from job_agent.db.session import log_action
from job_agent.integrations.google_auth import get_credentials


@dataclass
class InboxMessage:
    """A minimally-parsed inbound Gmail message."""

    id: str
    thread_id: str
    sender: str
    subject: str
    body: str


def _service():
    """Build a Gmail API client from cached OAuth credentials."""
    from googleapiclient.discovery import build

    return build("gmail", "v1", credentials=get_credentials())


def _header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _extract_body(payload: dict) -> str:
    """Recursively pull the first text/plain part from a message payload."""
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    for part in payload.get("parts", []) or []:
        text = _extract_body(part)
        if text:
            return text
    return ""


def fetch_unread(max_results: int = 20) -> list[InboxMessage]:
    """Return recent unread messages from the inbox."""
    service = _service()
    resp = (
        service.users()
        .messages()
        .list(userId="me", q="is:unread in:inbox", maxResults=max_results)
        .execute()
    )
    messages: list[InboxMessage] = []
    for ref in resp.get("messages", []):
        full = (
            service.users()
            .messages()
            .get(userId="me", id=ref["id"], format="full")
            .execute()
        )
        headers = full.get("payload", {}).get("headers", [])
        messages.append(
            InboxMessage(
                id=full["id"],
                thread_id=full["threadId"],
                sender=_header(headers, "From"),
                subject=_header(headers, "Subject"),
                body=_extract_body(full.get("payload", {})),
            )
        )
    logger.info("Fetched {} unread messages", len(messages))
    return messages


def create_draft(
    to: str, subject: str, body: str, thread_id: str | None = None
) -> str:
    """Create a Gmail draft reply. Returns the draft id. Never sends."""
    service = _service()
    mime = MIMEText(body)
    mime["To"] = to
    mime["Subject"] = subject
    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
    message: dict = {"raw": raw}
    if thread_id:
        message["threadId"] = thread_id
    draft = (
        service.users()
        .drafts()
        .create(userId="me", body={"message": message})
        .execute()
    )
    draft_id = draft["id"]
    log_action("gmail_draft", f"to={to} subject={subject} draft_id={draft_id}")
    logger.info("Created Gmail draft {}", draft_id)
    return draft_id
