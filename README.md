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
python -m job_agent.main init             # create the database
python -m job_agent.main scrape           # scrape all boards once
python -m job_agent.main mail             # poll Gmail + classify once
python -m job_agent.main tailor <job_id>  # tailor one job
python -m job_agent.main dashboard        # launch the Streamlit UI
python -m job_agent.main serve            # run the scheduler in foreground
python -m job_agent.main all              # scrape + tailor + classify

# Test one scraper without writing to the DB
python -m job_agent.scrapers.cli linkedin --dry-run
```

The dashboard has four tabs: **Jobs** (new postings, tailor on demand),
**Ready to apply** (tailored resume + cover letter side by side, approve to
queue), **Drafts** (Gmail draft replies), and **Tracker** (all applications
with status filters and the daily count).

## Troubleshooting

### "59 cards found, 0 jobs saved"
This is the classic scraper bug and it has a specific cause. Job boards append
a per-session tracking query string (`?trk=...`, `?ref=...`) to every job URL,
so the same posting looks unique on each scrape — then collides on the unique
constraint and is silently dropped, leaving 0 saved.

**Fixes already in the code:**
- `_strip_query()` in `scrapers/base.py` normalises URLs to the path before
  dedup, so the same posting dedups correctly.
- Each scraper logs every card *before* validation
  (`card i: title=... url=...`) and logs the reason it was dropped
  (`skipped: missing fields` / `skipped: duplicate`).
- `MAX_CARDS_PER_RUN` (default 25) caps a run so it finishes fast and within
  rate limits; `polite_delay()` runs between page navigations, not per card.

**How to diagnose your run:** run `python -m job_agent.scrapers.cli linkedin
--dry-run` and read the summary line — `saved=X duplicates_dropped=Y kept=Z`.
- `found 0 cards` → the container selector (e.g. `div.base-card`) is stale, or
  LinkedIn served a login wall (check the logged page title).
- `found N cards` but all `skipped: missing fields` → the inner title/url
  selectors in that scraper's `_parse_card` need updating.

### Google OAuth
First run of any Gmail/Calendar command opens a browser for consent and caches
`token.json`. Gmail is authorised with `gmail.compose` only — the agent can
create drafts but can never send. Delete `token.json` to re-consent (e.g. after
adding the Drive backup scope).

### Anthropic key
Set `ANTHROPIC_API_KEY` in `.env`. Tailoring uses Sonnet, classification uses
Haiku (see `TAILOR_MODEL` / `CLASSIFIER_MODEL`). Agent tests mock the client,
so they run without a key.

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
