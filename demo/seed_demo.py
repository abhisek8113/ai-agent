"""End-to-end demo: seed realistic jobs + emails, run the full pipeline with
representative agent outputs (no API key needed), and dump the resulting
dashboard state to JSON so it can be rendered.

Run:  python -m demo.seed_demo
"""

from __future__ import annotations

import json
from pathlib import Path

import job_agent.agents.classifier as classifier_mod
import job_agent.agents.replier as replier_mod
import job_agent.agents.tailor as tailor_mod
from job_agent.db.models import (
    Application,
    ApplicationStatus,
    EmailThread,
    Job,
    Reply,
)
from job_agent.db.session import get_session, init_db, log_action
from job_agent.scrapers.base import BaseScraper, ScrapedJob

# --- Representative job postings (what the scrapers would return) ------------
DEMO_JOBS = [
    ScrapedJob(
        source="linkedin", external_id="ln-88213", title="Data Scientist",
        company="Zensar Technologies", location="Coimbatore (Hybrid)",
        url="https://www.linkedin.com/jobs/view/88213",
        description=("Build ML models on customer data. Required: Python, SQL, "
                     "scikit-learn, statistics, data storytelling with Power BI. "
                     "Nice to have: Spark, MLOps."),
    ),
    ScrapedJob(
        source="naukri", external_id="nk-40551", title="Junior Data Scientist",
        company="Tiger Analytics", location="Remote (India)",
        url="https://www.naukri.com/job/40551",
        description=("Analytics consulting. Python, SQL, EDA, feature engineering, "
                     "communication skills. Freshers with strong fundamentals welcome."),
    ),
    ScrapedJob(
        source="indeed", external_id="in-77120", title="ML Engineer",
        company="Globex Corp", location="Bengaluru",
        url="https://in.indeed.com/viewjob?jk=77120",
        description=("Productionize ML pipelines. Required: Python, Spark, Airflow, "
                     "Kubernetes, deep learning. 3+ years experience."),
    ),
]

# --- Representative Claude outputs (stubbed so the demo needs no API key) ----
TAILOR_OUTPUTS = {
    "Data Scientist": {
        "tailored_resume_md": "# Abhisek Murugesan\n**Data Scientist** — Python · SQL · ML · Power BI\n\n## Summary\nData Science trainer turning curriculum expertise into applied modelling...\n\n## Skills\nPython, SQL (advanced), scikit-learn, statistics, **Power BI**, data storytelling",
        "cover_letter_md": "Your Coimbatore team's focus on turning customer data into decisions is exactly the work I've been teaching others to do. As a Data Science trainer I've built and debugged dozens of end-to-end Python/scikit-learn pipelines and translated model output into Power BI dashboards stakeholders actually use...",
        "match_score": 86, "gaps": ["Spark", "MLOps"],
        "keywords_used": ["Python", "SQL", "scikit-learn", "Power BI", "statistics"],
    },
    "Junior Data Scientist": {
        "tailored_resume_md": "# Abhisek Murugesan\n**Junior Data Scientist** — strong fundamentals, remote-ready\n\n## Skills\nPython, SQL, EDA, feature engineering, clear communication",
        "cover_letter_md": "Tiger Analytics hires for fundamentals over years on paper — which is where I'm strongest. Teaching Python and SQL daily has forced me to know EDA and feature engineering cold, not just apply them...",
        "match_score": 91, "gaps": [],
        "keywords_used": ["Python", "SQL", "EDA", "feature engineering"],
    },
    "ML Engineer": {
        "tailored_resume_md": "# Abhisek Murugesan\n**Aspiring ML Engineer**\n\n## Skills\nPython, ML foundations, Git",
        "cover_letter_md": "I'm early in the MLOps journey but bring a rigorous grasp of the modelling fundamentals your pipelines serve...",
        "match_score": 48, "gaps": ["Spark", "Airflow", "Kubernetes", "3+ yrs experience"],
        "keywords_used": ["Python", "machine learning"],
    },
}

DEMO_EMAILS = [
    {
        "thread_id": "gm-thread-1", "sender": "Priya Raman <priya@tigeranalytics.com>",
        "subject": "Interested in your Data Scientist profile",
        "classify": {"category": "recruiter_outreach", "urgency": "high", "requires_reply": True,
                     "extracted": {"company": "Tiger Analytics", "role": "Junior Data Scientist",
                                   "recruiter_name": "Priya Raman", "next_step": "intro call", "deadline": None},
                     "summary": "Recruiter reaching out about the Junior DS role; wants an intro call."},
        "reply": {"subject": "Re: Interested in your Data Scientist profile",
                  "body_md": "Hi Priya,\n\nThanks for reaching out — the Junior Data Scientist role is a strong fit for where I'm headed. I'd be glad to set up an intro call.\n\nWeekday mornings IST work best for me this week; happy to work around your calendar. Shall I send a couple of slots?\n\nBest,\n[Candidate Name]",
                  "tone_notes": "Warm, concrete, moves toward a call without over-committing.", "confidence": 88},
    },
    {
        "thread_id": "gm-thread-2", "sender": "LinkedIn Job Alerts <jobalerts@linkedin.com>",
        "subject": "5 new Data Scientist jobs in Coimbatore",
        "classify": {"category": "job_alert", "urgency": "low", "requires_reply": False,
                     "extracted": {"company": None, "role": "Data Scientist", "recruiter_name": None,
                                   "next_step": None, "deadline": None},
                     "summary": "Automated LinkedIn job alert; no reply needed."},
        "reply": None,
    },
    {
        "thread_id": "gm-thread-3", "sender": "TA Team <careers@zensar.com>",
        "subject": "Zensar — Data Scientist: next steps",
        "classify": {"category": "interview_invite", "urgency": "high", "requires_reply": True,
                     "extracted": {"company": "Zensar Technologies", "role": "Data Scientist",
                                   "recruiter_name": None, "next_step": "technical screen", "deadline": "2026-07-28"},
                     "summary": "Invitation to a technical screen; asks for availability by Jul 28."},
        "reply": {"subject": "Re: Zensar — Data Scientist: next steps",
                  "body_md": "Hi team,\n\nDelighted to move forward with the technical screen. I'm available weekday mornings IST through next week — I can share three specific slots if that's easiest.\n\nLooking forward to it.\n\nBest,\n[Candidate Name]",
                  "tone_notes": "Enthusiastic, offers concrete availability, no salary talk.", "confidence": 84},
    },
]


class DemoScraper(BaseScraper):
    source = "demo"

    def polite_delay(self):  # no sleeping in the demo
        pass

    def fetch_jobs(self, keywords, location):
        yield from DEMO_JOBS


def run() -> dict:
    init_db()

    # 1. Scrape (persist demo jobs, respecting dedup)
    DemoScraper().run(keywords="Data Scientist", location="Coimbatore")

    # 2. Tailor each job (stub Claude with representative output)
    tailor_mod.complete_json = lambda system, user, model, **k: next(
        v for title, v in TAILOR_OUTPUTS.items() if title in user
    )
    with get_session() as session:
        jobs = session.query(Job).all()
        for job in jobs:
            data = next(v for t, v in TAILOR_OUTPUTS.items() if t == job.title)
            session.add(Application(
                job_id=job.id, status=ApplicationStatus.PENDING_APPROVAL,
                tailored_resume_md=data["tailored_resume_md"],
                cover_letter_md=data["cover_letter_md"],
                match_score=data["match_score"], gaps=data["gaps"],
                keywords_used=data["keywords_used"],
            ))
    log_action("demo_tailor", f"tailored {len(jobs)} applications")

    # 3. Classify emails + draft replies (stub Claude)
    for e in DEMO_EMAILS:
        classifier_mod.complete_json = lambda *a, _e=e, **k: _e["classify"]
        c = classifier_mod.classify_email(e["sender"], e["subject"], "(body)")
        with get_session() as session:
            thread = EmailThread(
                gmail_thread_id=e["thread_id"], sender=e["sender"], subject=e["subject"],
                category=c.category, urgency=c.urgency, requires_reply=c.requires_reply,
                extracted=c.extracted, summary=c.summary,
            )
            session.add(thread)
            session.flush()
            tid = thread.id
        if e["reply"]:
            replier_mod.complete_json = lambda *a, _e=e, **k: _e["reply"]
            d = replier_mod.draft_reply("(thread)", "(profile)", "thank_and_engage")
            with get_session() as session:
                session.add(Reply(
                    thread_id=tid, intent="thank_and_engage", subject=d.subject,
                    body_md=d.body_md, tone_notes=d.tone_notes, confidence=d.confidence,
                    gmail_draft_id=f"draft_{tid}",  # simulates a saved Gmail draft
                ))
            log_action("gmail_draft", f"thread={tid} (simulated draft)")

    return export_state()


def export_state() -> dict:
    """Read everything back for rendering."""
    with get_session() as session:
        apps = []
        for app in session.query(Application).all():
            apps.append({
                "title": app.job.title, "company": app.job.company,
                "location": app.job.location, "source": app.job.source, "url": app.job.url,
                "match_score": app.match_score, "gaps": app.gaps or [],
                "keywords": app.keywords_used or [], "cover_letter": app.cover_letter_md,
                "resume": app.tailored_resume_md, "status": app.status.value,
            })
        emails = []
        replies = {r.thread_id: r for r in session.query(Reply).all()}
        for t in session.query(EmailThread).all():
            r = replies.get(t.id)
            emails.append({
                "sender": t.sender, "subject": t.subject, "category": t.category.value,
                "urgency": t.urgency, "requires_reply": t.requires_reply, "summary": t.summary,
                "extracted": t.extracted or {},
                "reply": None if not r else {
                    "subject": r.subject, "body": r.body_md, "confidence": r.confidence,
                    "tone_notes": r.tone_notes, "draft_id": r.gmail_draft_id,
                },
            })
        from job_agent.db.models import ActionLog
        actions = [
            {"action": a.action, "detail": a.detail, "at": a.created_at.isoformat()}
            for a in session.query(ActionLog).order_by(ActionLog.id).all()
        ]
    apps.sort(key=lambda a: a["match_score"], reverse=True)
    return {"applications": apps, "emails": emails, "actions": actions}


if __name__ == "__main__":
    state = run()
    Path("demo/state.json").write_text(json.dumps(state, indent=2))
    print(json.dumps(state, indent=2))
