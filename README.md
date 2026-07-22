# Job Application Agent

A local, **human-in-the-loop** job-search assistant for a Data Scientist
candidate. It scrapes jobs, tailors a resume + cover letter per posting with
Claude, classifies recruiter emails and drafts replies into Gmail Drafts, and
surfaces everything in a Streamlit dashboard where **you approve before
anything is submitted or sent**.

## Safety rails (non-negotiable)

1. **Human approval before submit** — the form bot fills fields but never
   clicks submit/apply. Approval happens in the dashboard.
2. **Emails land in Drafts, never sent** — Gmail is authorised with
   `gmail.compose` only; there is no send code path.
3. **Rate limit** — max `MAX_APPLICATIONS_PER_DAY` (default 20), enforced from
   the database so restarts don't reset it. Random 30–120s delays between
   browser actions.
4. **Kill switch** — set `PAUSE_ALL=true` in `.env` to halt all automation.
5. **Every action is logged** to the `action_log` table with a timestamp.

## Architecture

```
job_agent/
├── config.py            # env-loaded, validated settings (pydantic)
├── db/                  # SQLAlchemy models + session; alembic migrations
├── scrapers/            # base (rate limit, UA rotation, stealth) + boards
├── agents/              # tailor, classifier, replier + prompts + client
├── integrations/        # gmail (drafts only), calendar (propose slots)
├── autofill/            # form_bot (STOPS before submit) + rate_limit guard
├── dashboard/app.py     # Streamlit review UI
├── pipeline.py          # orchestration shared by CLI + scheduler
├── scheduler.py         # APScheduler daily jobs
└── main.py              # one-off CLI
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

cp .env.example .env          # then fill in ANTHROPIC_API_KEY etc.
# Put Google OAuth client secrets in credentials.json
# Edit master_resume.md and candidate_profile.yaml
```

## Usage

```bash
# Initialise the database
python -m job_agent.main init

# Test one scraper without writing to the DB
python -m job_agent.scrapers.cli linkedin --dry-run

# Run the whole pipeline once (scrape -> tailor -> classify inbox)
python -m job_agent.main all

# Launch the review dashboard
streamlit run job_agent/dashboard/app.py

# Run the daily scheduler
python -m job_agent.scheduler
```

## Database migrations (alembic)

```bash
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

## Tests

```bash
pytest
```

Agent tests mock the Claude client, so they run without an API key or network.

## Notes on scrapers

The board scrapers use Playwright with stealth and rotate user agents. Job
boards change their markup often; selectors are centralised at the top of each
scraper module so they are easy to update. Start with `--dry-run` to confirm
selectors before persisting.
