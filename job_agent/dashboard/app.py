"""Streamlit review dashboard — the human-in-the-loop control surface.

Nothing is submitted or sent from here automatically. The user reviews
tailored applications and drafted replies, then approves them explicitly.

Run with:  streamlit run job_agent/dashboard/app.py
"""

from __future__ import annotations

import streamlit as st
from sqlalchemy import select

from job_agent.config import settings
from job_agent.db.models import (
    Application,
    ApplicationStatus,
    EmailThread,
    Job,
    Reply,
)
from job_agent.db.session import get_session, init_db, log_action


def _daily_usage() -> int:
    from job_agent.autofill.rate_limit import submitted_today

    return submitted_today()


def render_header() -> None:
    st.title("Job Application Agent")
    cols = st.columns(3)
    cols[0].metric(
        "Applications today",
        f"{_daily_usage()}/{settings.max_applications_per_day}",
    )
    cols[1].metric("Kill switch", "PAUSED" if settings.pause_all else "active")
    cols[2].metric("Tailoring model", settings.tailor_model)
    if settings.pause_all:
        st.error("PAUSE_ALL is set. Automation is halted until you unset it in .env.")


def render_applications() -> None:
    st.header("Pending applications")
    with get_session() as session:
        rows = session.execute(
            select(Application, Job)
            .join(Job, Application.job_id == Job.id)
            .where(Application.status == ApplicationStatus.PENDING_APPROVAL)
            .order_by(Application.match_score.desc())
        ).all()

    if not rows:
        st.info("No applications awaiting approval.")
        return

    for app, job in rows:
        with st.expander(
            f"{job.title} @ {job.company or 'Unknown'} "
            f"— match {app.match_score or 0}%"
        ):
            st.caption(f"{job.source} · {job.location or 'n/a'} · {job.url or ''}")
            if app.gaps:
                st.warning("Gaps: " + ", ".join(app.gaps))
            st.subheader("Cover letter")
            st.markdown(app.cover_letter_md or "_none_")
            with st.popover("View tailored resume"):
                st.markdown(app.tailored_resume_md or "_none_")

            c1, c2 = st.columns(2)
            if c1.button("Approve", key=f"approve_{app.id}"):
                _set_status(app.id, ApplicationStatus.APPROVED, approved=True)
                st.success("Approved. Submit manually on the portal, then mark submitted.")
                st.rerun()
            if c2.button("Skip", key=f"skip_{app.id}"):
                _set_status(app.id, ApplicationStatus.SKIPPED)
                st.rerun()


def render_emails() -> None:
    st.header("Inbox")
    with get_session() as session:
        threads = session.scalars(
            select(EmailThread).order_by(EmailThread.created_at.desc()).limit(50)
        ).all()
        replies = {
            r.thread_id: r
            for r in session.scalars(select(Reply)).all()
        }

    if not threads:
        st.info("No classified emails yet.")
        return

    for t in threads:
        badge = "reply" if t.requires_reply else "info"
        with st.expander(
            f"[{t.category.value}/{t.urgency}] {t.subject or '(no subject)'}"
        ):
            st.caption(f"From: {t.sender}")
            st.write(t.summary or "")
            draft = replies.get(t.id)
            if draft:
                st.subheader(f"Draft ({draft.confidence}% confident)")
                if draft.confidence is not None and draft.confidence < 70:
                    st.warning("Low confidence — rewrite before using.")
                st.markdown(draft.body_md or "")
                if draft.gmail_draft_id:
                    st.success(f"Saved to Gmail Drafts: {draft.gmail_draft_id}")
            elif t.requires_reply:
                st.info(f"Reply needed — badge: {badge}. Draft from the CLI or pipeline.")


def _set_status(
    app_id: int, status: ApplicationStatus, approved: bool = False
) -> None:
    with get_session() as session:
        app = session.get(Application, app_id)
        if app is None:
            return
        app.status = status
        app.approved_by_human = approved
    log_action("dashboard_status", f"app={app_id} status={status.value}")


def main() -> None:
    st.set_page_config(page_title="Job Application Agent", layout="wide")
    init_db()
    render_header()
    tab_apps, tab_mail = st.tabs(["Applications", "Inbox"])
    with tab_apps:
        render_applications()
    with tab_mail:
        render_emails()


main()
