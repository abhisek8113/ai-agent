"""Resume + cover letter tailoring agent."""

from __future__ import annotations

from dataclasses import dataclass, field

from loguru import logger

from job_agent.agents.client import complete_json
from job_agent.agents.prompts import RESUME_TAILOR_PROMPT
from job_agent.config import settings


@dataclass
class TailorResult:
    """Structured output of the tailoring agent."""

    tailored_resume_md: str
    cover_letter_md: str
    match_score: int
    gaps: list[str] = field(default_factory=list)
    keywords_used: list[str] = field(default_factory=list)


def tailor_resume(master_resume_md: str, job_description: str) -> TailorResult:
    """Tailor the master resume + generate a cover letter for one JD."""
    user_content = (
        f"<master_resume>\n{master_resume_md}\n</master_resume>\n\n"
        f"<job_description>\n{job_description}\n</job_description>"
    )
    data = complete_json(
        RESUME_TAILOR_PROMPT, user_content, model=settings.tailor_model
    )
    logger.info("Tailored resume, match_score={}", data.get("match_score"))
    return TailorResult(
        tailored_resume_md=data.get("tailored_resume_md", ""),
        cover_letter_md=data.get("cover_letter_md", ""),
        match_score=int(data.get("match_score", 0)),
        gaps=list(data.get("gaps", [])),
        keywords_used=list(data.get("keywords_used", [])),
    )
