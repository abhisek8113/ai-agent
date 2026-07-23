"""Tests for API-based scrapers (HTTP mocked) and resume rendering."""

from __future__ import annotations

import job_agent.scrapers.apis as apis
from job_agent.render import render_resume


def test_remotive_parses(monkeypatch):
    monkeypatch.setattr(apis, "_get_json", lambda url, params=None: {
        "jobs": [{"id": 7, "title": "Data Scientist", "company_name": "Acme",
                  "candidate_required_location": "India", "url": "http://x/7",
                  "description": "Python SQL"}]
    })
    jobs = list(apis.RemotiveScraper().fetch_jobs("data scientist", "India"))
    assert len(jobs) == 1
    assert jobs[0].source == "remotive"
    assert jobs[0].company == "Acme"


def test_remoteok_skips_legal_notice_and_filters(monkeypatch):
    monkeypatch.setattr(apis, "_get_json", lambda url, params=None: [
        {"legal": "notice, no position key"},
        {"id": 1, "position": "Data Scientist", "company": "Beta",
         "tags": ["python"], "url": "http://x/1", "description": "d"},
        {"id": 2, "position": "Chef", "company": "Kitchen", "tags": [],
         "url": "http://x/2", "description": "d"},
    ])
    jobs = list(apis.RemoteOKScraper().fetch_jobs("data scientist", ""))
    assert [j.title for j in jobs] == ["Data Scientist"]  # legal + Chef filtered out


def test_greenhouse_per_company(monkeypatch):
    monkeypatch.setattr(apis.settings, "greenhouse_companies", "acme")
    monkeypatch.setattr(apis, "_get_json", lambda url, params=None: {
        "jobs": [{"id": 99, "title": "Senior Data Scientist",
                  "location": {"name": "Remote"}, "absolute_url": "http://g/99",
                  "content": "ml python"}]
    })
    jobs = list(apis.GreenhouseScraper().fetch_jobs("data scientist", ""))
    assert jobs[0].external_id == "acme:99"
    assert jobs[0].company == "acme"


def test_adzuna_skipped_without_keys(monkeypatch):
    monkeypatch.setattr(apis.settings, "adzuna_app_id", "")
    monkeypatch.setattr(apis.settings, "adzuna_app_key", "")
    assert list(apis.AdzunaScraper().fetch_jobs("x", "y")) == []


def test_render_resume_writes_files(tmp_path, monkeypatch):
    monkeypatch.setattr("job_agent.render.settings.resume_output_dir", str(tmp_path))
    path = render_resume("# Abhi\n## Skills\n- Python", "Acme", "Data Scientist", 42)
    assert path.exists()
    assert path.suffix == ".html"
    assert "Python" in path.read_text()
    assert (tmp_path / "acme_data-scientist_42.md").exists()
