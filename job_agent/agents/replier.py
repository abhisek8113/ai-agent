"""Reply drafter + screening question answerer agents."""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from job_agent.agents.client import complete_json
from job_agent.agents.prompts import REPLY_DRAFTER_PROMPT, SCREENING_ANSWERER_PROMPT
from job_agent.config import settings

VALID_INTENTS = {
    "accept_interview",
    "request_reschedule",
    "thank_and_engage",
    "decline_politely",
    "answer_screening",
}


@dataclass
class ReplyDraft:
    """Structured output of the reply drafter."""

    subject: str
    body_md: str
    tone_notes: str
    confidence: int

    @property
    def needs_human_rewrite(self) -> bool:
        """Confidence below 70 flags the draft for a human rewrite."""
        return self.confidence < 70


@dataclass
class ScreeningAnswer:
    """Structured output of the screening answerer."""

    answer: str
    confidence: int
    flag_for_review: bool


def draft_reply(
    email_thread: str, candidate_profile: str, intent: str
) -> ReplyDraft:
    """Draft a reply email for a given thread and intent."""
    if intent not in VALID_INTENTS:
        raise ValueError(f"Unknown intent {intent!r}; expected one of {VALID_INTENTS}")
    user_content = (
        f"<email_thread>\n{email_thread}\n</email_thread>\n\n"
        f"<candidate_profile>\n{candidate_profile}\n</candidate_profile>\n\n"
        f"<intent>{intent}</intent>"
    )
    data = complete_json(
        REPLY_DRAFTER_PROMPT, user_content, model=settings.tailor_model
    )
    draft = ReplyDraft(
        subject=data.get("subject", ""),
        body_md=data.get("body_md", ""),
        tone_notes=data.get("tone_notes", ""),
        confidence=int(data.get("confidence", 0)),
    )
    logger.info("Drafted reply (intent={}, confidence={})", intent, draft.confidence)
    return draft


def answer_screening_question(
    question: str, candidate_profile: str
) -> ScreeningAnswer:
    """Answer a single application screening question from the profile."""
    user_content = (
        f"<question>\n{question}\n</question>\n\n"
        f"<candidate_profile>\n{candidate_profile}\n</candidate_profile>"
    )
    data = complete_json(
        SCREENING_ANSWERER_PROMPT, user_content, model=settings.classifier_model
    )
    return ScreeningAnswer(
        answer=data.get("answer", ""),
        confidence=int(data.get("confidence", 0)),
        flag_for_review=bool(data.get("flag_for_review", True)),
    )
