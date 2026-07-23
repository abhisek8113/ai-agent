"""Email classifier agent (uses the cheaper Haiku model)."""

from __future__ import annotations

from dataclasses import dataclass, field

from loguru import logger
from pydantic import BaseModel, Field

from job_agent.agents.client import complete_json
from job_agent.agents.prompts import EMAIL_CLASSIFIER_PROMPT
from job_agent.config import settings
from job_agent.db.models import EmailCategory


class ClassifierOutput(BaseModel):
    """Pydantic schema for the classifier's JSON response."""

    category: str = "other"
    urgency: str = "low"
    requires_reply: bool = False
    extracted: dict = Field(default_factory=dict)
    summary: str = ""


@dataclass
class ClassificationResult:
    """Structured output of the classifier agent."""

    category: EmailCategory
    urgency: str
    requires_reply: bool
    extracted: dict = field(default_factory=dict)
    summary: str = ""


def classify_email(sender: str, subject: str, body: str) -> ClassificationResult:
    """Classify a single inbound email into an actionable category."""
    user_content = (
        f"from: {sender}\nsubject: {subject}\n\nbody:\n{body}"
    )
    data = complete_json(
        EMAIL_CLASSIFIER_PROMPT, user_content, model=settings.classifier_model
    )
    out = ClassifierOutput.model_validate(data)
    try:
        category = EmailCategory(out.category)
    except ValueError:
        category = EmailCategory.OTHER
    logger.info("Classified email from {} as {}", sender, category.value)
    return ClassificationResult(
        category=category,
        urgency=out.urgency,
        requires_reply=out.requires_reply,
        extracted=out.extracted,
        summary=out.summary,
    )
