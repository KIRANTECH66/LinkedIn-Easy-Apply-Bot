<img width="1200" height="655" alt="image" src="https://github.com/user-attachments/assets/ab83f6c8-5861-4630-8860-c804c3449f37" />






# Linkedin EasyApply Bot

Automate the application process on LinkedIn with an AI-driven agentic pipeline.

Write-up: https://substack.com/@nicolomantini/posts - How to apply for 1,000 jobs while sleeping

Video: https://www.youtube.com/watch?v=4R4E304fEAs

## 🚀 Agentic AI Architecture

The bot now runs a 9-agent pipeline plus a canonical job database:

```
┌─────────────────────┐
│ 1. Profile Agent    │  profile.json — candidate truth
│    (builds profile) │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 2. Job Discovery    │  →  ┌───────────────────────┐
│    (scrapes LinkedIn)│      │   JOBS DATABASE       │  ← Canonical store
└──────────┬──────────┘      │  jobs.db:               │
           │                 │  job_id, title, company,│
           ▼                 │  description, reqs,     │
┌─────────────────────┐      │  source, url, salary    │
│ 3. Job Matching     │      │  match/recruiter/hm/ats,│
│    (scores & filters)│     │  composite, decision,   │
└──────────┬──────────┘      │  status, timestamps     │
           │                 └───────────┬─────────────┘
           │                             │
           ▼                             │
┌─────────────────────────────────┐      │
│ 4. Resume Intelligence Agent    │      │
│    ┌──────────────────────────┐ │      │
│    │ 4.1 Senior Recruiter     │ │      │
│    │    Persona (0.3 weight)  │ │      │
│    └────────┬─────────────────┘ │      │
│             │                   │      │
│    ┌────────▼─────────────────┐ │      │
│    │ 4.2 Hiring Manager       │ │      │
│    │    Persona (0.4 weight)  │ │      │
│    └────────┬─────────────────┘ │      │
│             │                   │      │
│    ┌────────▼─────────────────┐ │      │
│    │ 4.3 ATS Evaluator        │ │      │
│    │    Persona (0.3 weight)  │ │      │
│    └──────────────────────────┘ │      │
│         Resume evaluate &       │      │
│         optimize per job        │      │
└──────────┬──────────────────────┘      │
           │                             │
           ▼                             │
┌─────────────────────┐                │
│ 5. Decision         │  → Update jobs.db
│    (approve/skip)   │  decision, status,
│    threshold: 0.7   │  composite_score
└──────────┬──────────┘
           │ APPROVED
           ▼
┌─────────────────────┐
│ 6. Application      │  → jobs.db.status = applied
│    (Easy Apply or   │  → out.csv log
│      company site)  │
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│ 7. Question         │  Q&A cached in qa.csv
│    (screening)      │
└─────────────────────┘
           ▼
┌─────────────────────┐
│ 8. Outcome          │  → jobs.db applied_timestamp
│    (success/fail)   │  → application_outcomes
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 9. Learning         │  learning.json:
│    (update rates)   │  company/role success rates
└──────────┬──────────┘
           │
           ▼
    ┌─────────────┐
    │ Re-rank     │  Learning feeds back to
    │ (matching)  │  JobMatchingAgent for
    └─────────────┘  next batch
```

## Setup

Python 3.10 using a conda virtual environment on Linux (Ubuntu)

The run the bot install requirements
```bash
pip3 install -r requirements.txt
```

## Configuration

### `.env` file (create from `.env.example`)

Required for AI agents — API keys for scoring, resume customization, and question answering.

```bash
cp .env.example .env
# Edit .env and add your API keys:
# OPENAI_API_KEY=...
# ANTHROPIC_API_KEY=...
```

### `config.yaml`

Enter your credentials, search settings, and AI config:

```yaml
username: # Your LinkedIn username
password: # Your LinkedIn password
phone_number: # Your phone number
name: # Your full name (for company career pages)
email: # Your email (for company career pages)

resume_sample: /path/to/your/resume.pdf  # Used by AI for resume optimization

positions:
- Software Engineer

locations:
- Michigan
- Remote

salary: 60,000
rate: 25

uploads:
  Resume: /path/to/resume.pdf
  Cover Letter: /path/to/cover_letter.pdf

ai:
  provider: "both"  # openai, anthropic, or both (fallback)
  model: "gpt-4o"
  anthropic_model: "claude-sonnet-4"
  scoring_threshold: 0.7
  max_jobs_per_run: 20
  batch_size: 10
  human_approval: false  # true = review_batch.md, false = auto-approve
  review_file: "review_batch.md"
  api_timeout_minutes: 10
  recency_priority: true

output_filename:
- /path/to/output.csv

# blacklist:
# - Company Name to skip
```

**NOTE: AFTER EDITING config.yaml, DO NOT COMMIT FILE**

### `profile.json`

The Profile Agent auto-generates and maintains this file. It captures your canonical truth:
- Skills, experience years, education, certifications
- Preferred roles, locations, salary expectations
- Blacklists, work authorization, remote preferences

## Execute

```bash
python3 easyapplybot.py
```

## Agent Reference

### 1. Profile Agent
- File: `agents/profile_agent.py`
- Builds/maintains `profile.json` from config + defaults
- Exposes: skills, experience, preferences, blacklists

### 2. Job Discovery Agent
- File: `agents/job_discovery.py`
- Scrapes LinkedIn search results across pages
- Extracts: jobID, title, company, location, posting date

### 3. Job Matching Agent
- File: `agents/job_matching.py`
- AI scores each job 0.0–1.0 against candidate profile
- Filters by `scoring_threshold`, sorts, applies diversity filter

### 4. Resume Intelligence Agent
- File: `agents/resume_intelligence.py`
- Three evaluation personas evaluate resume fit:
  - **Senior Technical Recruiter** (30% weight)
  - **Hiring Manager** (40% weight)
  - **ATS Evaluator** (30% weight)
- Composite score drives accept/reject decision
- Rewrites resume highlights per job description

### 5. Application Agent
- File: `agents/application.py`
- Tries Easy Apply first, falls back to company career page
- Uses `CompanyFiller` (8 ATS integrations) for company sites

### 6. Question Agent
- File: `agents/question.py`
- AI answers screening questions based on profile + job context
- Caches answers in `qa.csv`

### 7. Approval Agent
- File: `agents/approval.py`
- Auto-approves when `human_approval: false`
- When `true`: writes `review_batch.md`, polls for edits, times out to auto-approve

### 8. Tracking Agent
- File: `agents/tracking.py`
- Records every application to `out.csv`
- Tracks lifecycle: applied → interview → offer → rejected

### 9. Learning Agent
- File: `agents/learning.py`
- Learns from outcomes in `out.csv` + `jobs.db`
- Updates per-company and per-role success rates
- Feeds back into matching for future prioritization

### Jobs Database
- File: `agents/job_database.py`
- SQLite store: `jobs.db`
- Canonical record of all discovered + evaluated jobs
- Schema: job_id, title, company, location, description, scores, decision, status

## Outputs

| File | Description |
|---|---|
| `profile.json` | Candidate truth profile |
| `learning.json` | Company/role success rates |
| `jobs.db` | Canonical job store (SQLite) |
| `qa.csv` | Screening question/answer cache |
| `out.csv` | Application log |
| `review_batch.md` | Batch review (when `human_approval: true`) |
| `logs/` | Timestamped bot logs |
| `screenshots/` | Screenshots of applications |
