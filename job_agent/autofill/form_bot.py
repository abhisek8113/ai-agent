"""Playwright form filler that fills fields but NEVER submits.

This is the most safety-critical automation in the system. It fills known
fields from the candidate profile and uses the screening answerer for the
rest, then hands control back to the human. There is intentionally no code
path that clicks a submit/apply button.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from loguru import logger

from job_agent.agents.replier import answer_screening_question
from job_agent.autofill.rate_limit import check_daily_limit
from job_agent.config import settings
from job_agent.db.session import log_action

# Field-label substrings we can answer directly from the profile mapping.
DIRECT_FIELDS = {
    "name": "full_name",
    "email": "email",
    "phone": "phone",
    "location": "location",
    "current ctc": "current_ctc",
    "expected ctc": "expected_ctc",
    "notice period": "notice_period",
    "experience": "years_experience",
}


@dataclass
class FillReport:
    """Summary of what the bot filled and what it left for the human."""

    filled: dict[str, str] = field(default_factory=dict)
    flagged: list[str] = field(default_factory=list)
    submitted: bool = False  # Always False — enforced by design.


class FormBot:
    """Fills a job application form and stops before submit."""

    def __init__(self, profile: dict) -> None:
        self.profile = profile

    def _resolve(self, label: str) -> str | None:
        """Return a direct profile answer for a known field label, if any."""
        low = label.lower()
        for needle, key in DIRECT_FIELDS.items():
            if needle in low:
                value = self.profile.get(key)
                return str(value) if value is not None else None
        return None

    def fill(self, page, profile_text: str) -> FillReport:
        """Fill visible text inputs/textareas on ``page``. Never submits."""
        if settings.pause_all:
            raise RuntimeError("PAUSE_ALL is set; autofill halted.")
        check_daily_limit()

        report = FillReport()
        inputs = page.query_selector_all(
            "input[type='text'], input[type='email'], input[type='tel'], textarea"
        )
        for el in inputs:
            label = self._label_for(page, el)
            if not label:
                continue
            answer = self._resolve(label)
            if answer is None:
                result = answer_screening_question(label, profile_text)
                answer = result.answer
                if result.flag_for_review:
                    report.flagged.append(label)
            el.fill(answer)
            report.filled[label] = answer

        log_action(
            "autofill",
            f"filled={len(report.filled)} flagged={len(report.flagged)} "
            "submitted=False",
        )
        logger.warning(
            "Form filled with {} fields. STOPPING before submit — human approval "
            "required.",
            len(report.filled),
        )
        return report

    @staticmethod
    def _label_for(page, element) -> str | None:
        """Best-effort label for a form element (aria-label, placeholder, name)."""
        for attr in ("aria-label", "placeholder", "name"):
            val = element.get_attribute(attr)
            if val:
                return val
        return None
