"""Streamlit review dashboard — the human-in-the-loop control surface.

Four tabs: Jobs, Ready to apply, Drafts, Tracker. Nothing is submitted or
sent from here automatically; the user approves every action explicitly.

Run with:  streamlit run job_agent/dashboard/app.py
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import select

from job_agent.config import settings
from job_agent.db.models import (
    Application,
    ApplicationStatus,
    EmailThread,
    Job,
    JobStatus,
    Reply,
)
from job_agent.db.session import get_session, init_db, log_action


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _daily_usage() -> int:
    from job_agent.autofill.rate_limit import submitted_today

    return submitted_today()


def _set_job_status(job_id: int, status: JobStatus) -> None:
    with get_session() as session:
        job = session.get(Job, job_id)
        if job:
            job.status = status
    log_action("dashboard_job_status", f"job={job_id} status={status.value}")


def _set_app_status(app_id: int, status: ApplicationStatus, approver: str | None = None) -> None:
    with get_session() as session:
        app = session.get(Application, app_id)
        if app:
            app.status = status
            app.approved_by_human = status == ApplicationStatus.APPROVED
            if approver:
                app.human_approved_by = approver
    log_action("dashboard_app_status", f"app={app_id} status={status.value}")


# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #
def render_header() -> None:
    st.title("Job Application Agent")
    c = st.columns(3)
    c[0].metric("Applications today", f"{_daily_usage()}/{settings.max_applications_per_day}")
    c[1].metric("Kill switch", "PAUSED" if settings.pause_all else "active")
    c[2].metric("Tailoring model", settings.tailor_model)
    if settings.pause_all:
        st.error("PAUSE_ALL is set. Automation is halted until you unset it in .env.")
    st.caption("Nothing submits or sends on its own — every action below waits for your approval.")


# --------------------------------------------------------------------------- #
# Tab 1 — Jobs
# --------------------------------------------------------------------------- #
def tab_jobs() -> None:
    st.subheader("New jobs")
    with get_session() as session:
        jobs = session.scalars(
            select(Job).where(Job.status == JobStatus.NEW).order_by(Job.scraped_at.desc())
        ).all()
    if not jobs:
        st.info("No new jobs. Run `python -m job_agent.main scrape`.")
        return
    for job in jobs:
        with st.container(border=True):
            st.markdown(f"**{job.title}** — {job.company or 'Unknown'}")
            st.caption(f"{job.source} · {job.location or 'n/a'} · {job.salary_range or 'salary n/a'}")
            st.write((job.description or "")[:280] + ("…" if job.description and len(job.description) > 280 else ""))
            b = st.columns(3)
            if b[0].button("Tailor now", key=f"tailor_{job.id}"):
                _tailor_one(job.id)
                st.rerun()
            if b[1].button("Skip", key=f"skipjob_{job.id}"):
                _set_job_status(job.id, JobStatus.REJECTED)
                st.rerun()
            if job.url:
                b[2].link_button("Open JD", job.url)


def _tailor_one(job_id: int) -> None:
    """Tailor a single job on demand from the dashboard."""
    from job_agent.agents.tailor import tailor_for_job
    from job_agent.pipeline import load_master_resume

    resume = load_master_resume()
    if not resume:
        st.warning("No master_resume.md found.")
        return
    with get_session() as session:
        job = session.get(Job, job_id)
        data = tailor_for_job(job, resume)
        session.add(Application(
            job_id=job.id, status=ApplicationStatus.PENDING_APPROVAL,
            tailored_resume_md=data["tailored_resume_md"], cover_letter_md=data["cover_letter_md"],
            match_score=data["match_score"], gaps=data["gaps"], keywords_used=data["keywords_used"],
        ))
        job.status = JobStatus.TAILORED
        job.match_score = data["match_score"]


# --------------------------------------------------------------------------- #
# Tab 2 — Ready to apply
# --------------------------------------------------------------------------- #
def tab_ready() -> None:
    st.subheader("Ready to apply")
    with get_session() as session:
        rows = session.execute(
            select(Application, Job).join(Job, Application.job_id == Job.id)
            .where(Application.status == ApplicationStatus.PENDING_APPROVAL)
            .order_by(Application.match_score.desc())
        ).all()
    if not rows:
        st.info("Nothing tailored yet. Tailor jobs from the Jobs tab.")
        return
    for app, job in rows:
        with st.container(border=True):
            st.markdown(f"**{job.title}** — {job.company or 'Unknown'}  ·  match **{app.match_score or 0}%**")
            if app.gaps:
                st.warning("Gaps: " + ", ".join(app.gaps))
            col = st.columns(2)
            col[0].caption("Tailored resume")
            col[0].markdown(app.tailored_resume_md or "_none_")
            col[1].caption("Cover letter")
            col[1].markdown(app.cover_letter_md or "_none_")
            b = st.columns(2)
            if b[0].button("Approve & queue", key=f"appr_{app.id}"):
                _set_app_status(app.id, ApplicationStatus.APPROVED, approver="dashboard")
                _set_job_status(job.id, JobStatus.APPROVED)
                st.success("Approved. Submit manually on the portal, then mark submitted in Tracker.")
                st.rerun()
            if b[1].button("Skip", key=f"appskip_{app.id}"):
                _set_app_status(app.id, ApplicationStatus.SKIPPED)
                st.rerun()


# --------------------------------------------------------------------------- #
# Tab 3 — Drafts
# --------------------------------------------------------------------------- #
def tab_drafts() -> None:
    st.subheader("Drafted email replies")
    with get_session() as session:
        rows = session.execute(
            select(Reply, EmailThread).join(EmailThread, Reply.thread_id == EmailThread.id)
            .order_by(Reply.created_at.desc())
        ).all()
    if not rows:
        st.info("No draft replies yet. Run the inbox pipeline.")
        return
    for reply, thread in rows:
        with st.container(border=True):
            st.markdown(f"**{thread.subject or '(no subject)'}**")
            st.caption(f"From: {thread.sender} · {thread.category.value}")
            if reply.confidence is not None and reply.confidence < 70:
                st.warning(f"Low confidence ({reply.confidence}%) — rewrite before using.")
            st.markdown(reply.body_md or "")
            b = st.columns(2)
            if reply.gmail_draft_id:
                b[0].success(f"In Gmail Drafts: {reply.gmail_draft_id}")
            b[1].caption("Replies never auto-send — open Gmail to review and send.")


# --------------------------------------------------------------------------- #
# Tab 4 — Tracker
# --------------------------------------------------------------------------- #
def tab_tracker() -> None:
    st.subheader("Application tracker")
    with get_session() as session:
        rows = session.execute(
            select(Application, Job).join(Job, Application.job_id == Job.id)
            .order_by(Application.updated_at.desc())
        ).all()
    if not rows:
        st.info("No applications yet.")
        return
    statuses = [s.value for s in ApplicationStatus]
    chosen = st.multiselect("Filter by status", statuses, default=statuses)
    data = [
        {
            "id": app.id, "title": job.title, "company": job.company,
            "match": app.match_score, "status": app.status.value,
            "approved_by": app.human_approved_by or "",
        }
        for app, job in rows if app.status.value in chosen
    ]
    st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)
    st.caption(f"{_daily_usage()} submitted today (cap {settings.max_applications_per_day}).")


# --------------------------------------------------------------------------- #
def main() -> None:
    st.set_page_config(page_title="Job Application Agent", layout="wide")
    init_db()
    render_header()
    t1, t2, t3, t4 = st.tabs(["Jobs", "Ready to apply", "Drafts", "Tracker"])
    with t1:
        tab_jobs()
    with t2:
        tab_ready()
    with t3:
        tab_drafts()
    with t4:
        tab_tracker()


main()
