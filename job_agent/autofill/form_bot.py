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

# Apply-button variants across the major Indian job portals. We use these to
# *locate* (never click) the apply/submit control so we can stop right before it.
APPLY_BUTTON_SELECTORS = [
    "button:has-text('Easy Apply')",       # LinkedIn
    "button:has-text('Apply')",            # generic / Naukri
    "button#apply-button",                 # Naukri quick apply
    "button:has-text('Submit application')",
    "button:has-text('Submit')",
    "#indeedApplyButton",                  # Indeed
]


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

    @staticmethod
    def find_apply_button(page):
        """Locate (never click) the apply/submit button, trying known variants."""
        for selector in APPLY_BUTTON_SELECTORS:
            el = page.query_selector(selector)
            if el:
                logger.info("Detected apply control via selector: {}", selector)
                return el, selector
        logger.warning("No apply button detected — page layout may have changed.")
        return None, None


def fill_application(job, application, headless: bool = False, dry_run: bool = False):
    """Open the job URL, fill the form from the profile, and STOP before submit.

    In dry-run mode, actions are logged and no browser is launched. In live
    mode the browser stays open, paused at the submit button, until you either
    click submit yourself in the browser or press Enter here to abort.
    """
    from job_agent.pipeline import load_candidate_profile

    if settings.pause_all:
        raise RuntimeError("PAUSE_ALL is set; autofill halted.")
    check_daily_limit()

    profile = load_candidate_profile()
    profile_text = "\n".join(f"{k}: {v}" for k, v in profile.items())
    bot = FormBot(profile)

    if dry_run:
        logger.info("[dry-run] would open {} and fill fields from profile", job.url)
        logger.info("[dry-run] would STOP before submit (never auto-submits)")
        return FillReport()

    from job_agent.scrapers._playwright import stealth_page

    settings_headless = settings.headless
    settings.headless = headless
    try:
        with stealth_page("Mozilla/5.0") as page:
            page.goto(job.url, wait_until="domcontentloaded")
            report = bot.fill(page, profile_text)
            el, selector = bot.find_apply_button(page)
            with get_session_notes(application, report):
                pass
            print("\n" + "=" * 60)
            print("Ready to submit — review the browser.")
            print("Click the apply/submit button IN THE BROWSER to submit,")
            print("or press Enter here to ABORT without submitting.")
            print("=" * 60)
            try:
                input()
            except (KeyboardInterrupt, EOFError):
                pass
            logger.warning("Autofill session ended WITHOUT auto-submitting.")
            return report
    finally:
        settings.headless = settings_headless


from contextlib import contextmanager


@contextmanager
def get_session_notes(application, report: FillReport):
    """Persist the filled-field summary to Application.notes for the audit trail."""
    from job_agent.db.session import get_session

    with get_session() as session:
        app = session.get(type(application), application.id)
        if app is not None:
            filled = ", ".join(report.filled.keys())
            app.notes = (app.notes or "") + f"\nautofilled: {filled}"
    yield
