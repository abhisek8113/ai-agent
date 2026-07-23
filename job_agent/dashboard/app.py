"""Streamlit review dashboard — the human-in-the-loop control surface.

Sidebar: upload your master resume, see your profile, and filter jobs by
portal, company, and how well they suit you. Tabs: Jobs, Ready to apply,
Drafts, Tracker.

Safety rail: nothing is submitted or sent automatically. "1-click Apply"
tailors your resume and fills the portal form in a real browser, then STOPS at
the submit button for you to click.

Run with:  streamlit run job_agent/dashboard/app.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

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
from job_agent.pipeline import load_candidate_profile, load_master_resume
from job_agent.scoring import suitability_score


# --------------------------------------------------------------------------- #
# Small helpers
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


def _save_uploaded_resume(uploaded) -> None:
    path = Path(settings.resolve(settings.master_resume_file))
    path.write_bytes(uploaded.getvalue())
    log_action("resume_upload", f"file={uploaded.name} -> {path.name}")


def _tailor(job_id: int, profile_resume: str) -> int:
    """Tailor one job, create a PENDING application, return its id."""
    from job_agent.agents.tailor import tailor_for_job

    with get_session() as session:
        job = session.get(Job, job_id)
        data = tailor_for_job(job, profile_resume)
        app = Application(
            job_id=job.id, status=ApplicationStatus.PENDING_APPROVAL,
            tailored_resume_md=data["tailored_resume_md"], cover_letter_md=data["cover_letter_md"],
            match_score=data["match_score"], gaps=data["gaps"], keywords_used=data["keywords_used"],
        )
        session.add(app)
        job.status = JobStatus.TAILORED
        job.match_score = data["match_score"]
        session.flush()
        app_id = app.id
    try:
        from job_agent.render import render_resume
        render_resume(data["tailored_resume_md"], job.company or "", job.title or "", job_id)
    except Exception:
        pass
    return app_id


def _launch_autofill(app_id: int) -> None:
    """Spawn the autofill runner (opens a browser, pauses at submit)."""
    subprocess.Popen(
        [sys.executable, "-m", "job_agent.autofill.run", str(app_id)],
        cwd=str(Path(settings.resolve(".")).parent),
    )


# --------------------------------------------------------------------------- #
# Sidebar — resume upload, profile, filters
# --------------------------------------------------------------------------- #
def render_sidebar(profile: dict) -> dict:
    st.sidebar.header("Your resume")
    uploaded = st.sidebar.file_uploader("Upload master resume (.md/.txt)", type=["md", "txt"])
    if uploaded is not None:
        _save_uploaded_resume(uploaded)
        st.sidebar.success(f"Saved {uploaded.name}")
    resume = load_master_resume()
    st.sidebar.caption(f"Master resume: {'loaded ✓' if resume else 'missing — upload one'}")

    with st.sidebar.expander("Your profile (used to fill forms)"):
        st.json(profile or {"note": "candidate_profile.yaml not found"})

    st.sidebar.header("Filters")
    with get_session() as session:
        sources = [r[0] for r in session.execute(select(Job.source).distinct()).all()]
        companies = [r[0] for r in session.execute(select(Job.company).distinct()).all() if r[0]]
    chosen_sources = st.sidebar.multiselect("Job portals", sorted(sources), default=sorted(sources))
    company_query = st.sidebar.text_input("Company contains")
    min_fit = st.sidebar.slider("Minimum suitability %", 0, 100, 40)
    return {
        "sources": chosen_sources,
        "company_query": company_query.lower().strip(),
        "min_fit": min_fit,
    }


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
# Tab 1 — Jobs (with filters + suitability + 1-click apply)
# --------------------------------------------------------------------------- #
def tab_jobs(profile: dict, filters: dict, resume: str) -> None:
    st.subheader("New jobs")
    with get_session() as session:
        jobs = session.scalars(
            select(Job).where(Job.status == JobStatus.NEW).order_by(Job.scraped_at.desc())
        ).all()
    if not jobs:
        st.info("No new jobs. Run `python -m job_agent.main scrape`.")
        return

    # Score + filter locally (instant, no API).
    scored = []
    for job in jobs:
        fit = suitability_score(job.title or "", job.description or "", profile)
        if job.source not in filters["sources"]:
            continue
        if filters["company_query"] and filters["company_query"] not in (job.company or "").lower():
            continue
        if fit < filters["min_fit"]:
            continue
        scored.append((fit, job))
    scored.sort(key=lambda t: t[0], reverse=True)

    cap = settings.max_bulk_tailor
    batch = scored[:cap]  # daily-cap guard: only tailor up to the configured cap
    head = st.columns([3, 1])
    label = f"{len(scored)} of {len(jobs)} jobs match your filters."
    if len(scored) > cap:
        label += f" Bulk tailor is capped at {cap}/run (top-fit first)."
    head[0].caption(label)
    if head[1].button(f"Tailor top {len(batch)}", disabled=not batch):
        if not resume:
            st.warning("Upload a master resume first (sidebar).")
        else:
            progress = st.progress(0.0, text="Tailoring…")
            done = 0
            for i, (_fit, job) in enumerate(batch):
                try:
                    _tailor(job.id, resume)
                    done += 1
                except Exception as exc:  # keep going if one job fails
                    st.warning(f"Skipped {job.title}: {exc}")
                progress.progress((i + 1) / len(batch), text=f"Tailored {done}/{len(batch)}")
            log_action("bulk_tailor", f"tailored={done} cap={cap}")
            st.success(f"Tailored {done} jobs (cap {cap}) — see the 'Ready to apply' tab.")
            st.rerun()
    for fit, job in scored:
        with st.container(border=True):
            top = st.columns([6, 1])
            top[0].markdown(f"**{job.title}** — {job.company or 'Unknown'}")
            top[0].caption(f"{job.source} · {job.location or 'n/a'} · {job.salary_range or 'salary n/a'}")
            top[1].metric("Suits you", f"{fit}%")
            st.write((job.description or "")[:280] + ("…" if job.description and len(job.description) > 280 else ""))

            with st.expander("Info that will be used to apply"):
                st.json({k: profile.get(k) for k in (
                    "full_name", "email", "phone", "location", "notice_period",
                    "current_ctc", "expected_ctc", "years_experience") if k in profile})

            b = st.columns(4)
            if b[0].button("Tailor now", key=f"tailor_{job.id}"):
                if not resume:
                    st.warning("Upload a master resume first (sidebar).")
                else:
                    _tailor(job.id, resume)
                    st.rerun()
            if b[1].button("1-click Apply", key=f"apply_{job.id}", type="primary"):
                if not resume:
                    st.warning("Upload a master resume first (sidebar).")
                else:
                    app_id = _tailor(job.id, resume)
                    _set_app_status(app_id, ApplicationStatus.APPROVED, approver="dashboard")
                    _set_job_status(job.id, JobStatus.APPROVED)
                    _launch_autofill(app_id)
                    st.success("Tailored + opening browser to fill the form. Review and click Submit yourself.")
            if b[2].button("Skip", key=f"skipjob_{job.id}"):
                _set_job_status(job.id, JobStatus.REJECTED)
                st.rerun()
            if job.url:
                b[3].link_button("Open JD", job.url)


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
            b = st.columns(3)
            if b[0].button("Approve & queue", key=f"appr_{app.id}"):
                _set_app_status(app.id, ApplicationStatus.APPROVED, approver="dashboard")
                _set_job_status(job.id, JobStatus.APPROVED)
                st.rerun()
            if b[1].button("1-click Apply", key=f"rapply_{app.id}", type="primary"):
                _set_app_status(app.id, ApplicationStatus.APPROVED, approver="dashboard")
                _launch_autofill(app.id)
                st.success("Opening browser to fill the form. Review and click Submit yourself.")
            if b[2].button("Skip", key=f"appskip_{app.id}"):
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
            if reply.gmail_draft_id:
                st.success(f"In Gmail Drafts: {reply.gmail_draft_id}")


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
        {"id": app.id, "title": job.title, "company": job.company, "portal": job.source,
         "match": app.match_score, "status": app.status.value,
         "approved_by": app.human_approved_by or ""}
        for app, job in rows if app.status.value in chosen
    ]
    st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)
    st.caption(f"{_daily_usage()} submitted today (cap {settings.max_applications_per_day}).")


# --------------------------------------------------------------------------- #
def main() -> None:
    st.set_page_config(page_title="Job Application Agent", layout="wide")
    init_db()
    profile = load_candidate_profile()
    resume = load_master_resume()
    filters = render_sidebar(profile)
    render_header()
    t1, t2, t3, t4 = st.tabs(["Jobs", "Ready to apply", "Drafts", "Tracker"])
    with t1:
        tab_jobs(profile, filters, resume)
    with t2:
        tab_ready()
    with t3:
        tab_drafts()
    with t4:
        tab_tracker()


main()
