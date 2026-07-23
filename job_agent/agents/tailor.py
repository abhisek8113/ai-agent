"""Resume + cover letter tailoring agent."""

from __future__ import annotations

from dataclasses import dataclass, field

from loguru import logger
from pydantic import BaseModel, Field, field_validator

from job_agent.agents.client import complete_json
from job_agent.agents.prompts import RESUME_TAILOR_PROMPT
from job_agent.config import settings


class TailorOutput(BaseModel):
    """Pydantic schema the model's JSON must satisfy."""

    tailored_resume_md: str = ""
    cover_letter_md: str = ""
    match_score: int = 0
    gaps: list[str] = Field(default_factory=list)
    keywords_used: list[str] = Field(default_factory=list)

    @field_validator("match_score")
    @classmethod
    def _clamp(cls, v: int) -> int:
        return max(0, min(100, int(v)))


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
    out = TailorOutput.model_validate(data)
    logger.info("Tailored resume, match_score={}", out.match_score)
    return TailorResult(
        tailored_resume_md=out.tailored_resume_md,
        cover_letter_md=out.cover_letter_md,
        match_score=out.match_score,
        gaps=out.gaps,
        keywords_used=out.keywords_used,
    )


def tailor_for_job(job, master_resume_md: str) -> dict:
    """Tailor for a Job row and return a dict the caller saves to Application."""
    result = tailor_resume(master_resume_md, job.description or job.title or "")
    return {
        "tailored_resume_md": result.tailored_resume_md,
        "cover_letter_md": result.cover_letter_md,
        "match_score": result.match_score,
        "gaps": result.gaps,
        "keywords_used": result.keywords_used,
    }
