"""Central configuration loaded from the environment / .env file.

All secrets live in ``.env`` (never hardcoded). Import ``settings`` anywhere
you need configuration; it is a singleton validated by pydantic.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Typed application settings sourced from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Anthropic
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    tailor_model: str = Field(default="claude-sonnet-4-6", alias="TAILOR_MODEL")
    classifier_model: str = Field(
        default="claude-haiku-4-5-20251001", alias="CLASSIFIER_MODEL"
    )

    # Google
    google_credentials_file: str = Field(
        default="credentials.json", alias="GOOGLE_CREDENTIALS_FILE"
    )
    google_token_file: str = Field(default="token.json", alias="GOOGLE_TOKEN_FILE")

    # Storage
    database_url: str = Field(default="sqlite:///job_agent.db", alias="DATABASE_URL")

    # Safety rails
    pause_all: bool = Field(default=False, alias="PAUSE_ALL")
    max_applications_per_day: int = Field(default=20, alias="MAX_APPLICATIONS_PER_DAY")
    min_action_delay: float = Field(default=30.0, alias="MIN_ACTION_DELAY")
    max_action_delay: float = Field(default=120.0, alias="MAX_ACTION_DELAY")

    # Candidate
    candidate_profile_file: str = Field(
        default="candidate_profile.yaml", alias="CANDIDATE_PROFILE_FILE"
    )
    master_resume_file: str = Field(
        default="master_resume.md", alias="MASTER_RESUME_FILE"
    )

    # Scraping
    job_search_keywords: str = Field(
        default="Data Scientist", alias="JOB_SEARCH_KEYWORDS"
    )
    job_search_location: str = Field(
        default="Coimbatore", alias="JOB_SEARCH_LOCATION"
    )
    headless: bool = Field(default=True, alias="HEADLESS")
    # Cap on how many cards a single scraper run will process, so a page with
    # dozens of results doesn't blow past the rate limit or run for minutes.
    max_cards_per_run: int = Field(default=25, alias="MAX_CARDS_PER_RUN")

    def resolve(self, relative: str) -> Path:
        """Resolve a path setting against the project root if not absolute."""
        p = Path(relative)
        return p if p.is_absolute() else PROJECT_ROOT / p


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached, validated settings singleton."""
    return Settings()


settings = get_settings()
