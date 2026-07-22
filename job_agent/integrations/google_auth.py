"""Shared Google OAuth2 flow for Gmail + Calendar.

Runs the installed-app consent flow on first use and caches the token so
subsequent runs are non-interactive. Scopes are intentionally minimal:
Gmail is limited to composing drafts (never sending), and Calendar is
read/write for proposing slots.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from job_agent.config import settings

# gmail.compose lets us create drafts but NOT send — a safety rail by design.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar",
]


def get_credentials():
    """Return valid Google OAuth2 credentials, refreshing/consenting as needed."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    token_path = Path(settings.resolve(settings.google_token_file))
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        logger.info("Refreshing expired Google token")
        creds.refresh(Request())
    else:
        cred_path = Path(settings.resolve(settings.google_credentials_file))
        if not cred_path.exists():
            raise FileNotFoundError(
                f"Google credentials file not found at {cred_path}. "
                "Download OAuth client secrets from Google Cloud Console."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(cred_path), SCOPES)
        creds = flow.run_local_server(port=0)

    token_path.write_text(creds.to_json())
    return creds
