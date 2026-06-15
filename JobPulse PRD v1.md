# JobPulse — Product Requirements Document

**Version:** 3.0 | **Date:** June 2026 | **Status:** Draft — Free Stack
**Author:** Jimi Aboderin

-----

## 1. Product Overview

|                      |                                                                                                                                                                                                                                                   |
|----------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|**Working name**      |JobPulse                                                                                                                                                                                                                                           |
|**Tagline**           |Your personal AI headhunter for worldwide remote work                                                                                                                                                                                              |
|**One-liner**         |JobPulse aggregates remote jobs from 60+ boards and company career pages, scores them against your profile using AI, filters out geo-restricted and overqualified roles, and alerts you on Telegram when something genuinely worth your time drops.|
|**Total monthly cost**|**$0**                                                                                                                                                                                                                                             |

-----

## 2. Problem Statement

Finding a genuinely worldwide-remote, entry-level or internship role that matches your skill set is a frustrating, hours-long manual process:

- “Remote” on most boards secretly means “remote in the US/EU only”
- Hundreds of job sites post overlapping roles — deduplication is manual and tedious
- Reading 50 listings to find 2 relevant ones is unsustainable at scale
- There’s no way to monitor 60 sites simultaneously without a tool doing the watching
- Notifications from boards are noisy, untailored — they don’t know your actual skills or location constraints
- Many curated lists of remote job boards (GitHub repos, blog posts) exist but there’s no way to activate them all in one place

-----

## 3. Target User

**Primary user (MVP):** CS graduate based in Lagos, Nigeria. Seeking entry-level, junior, or internship roles in data analysis, backend/full-stack development, or product. Needs fully worldwide remote — no country restriction, no visa requirement. Dollar/GBP/EUR paying preferred. Open to many role types as long as qualifiable.

-----

## 4. Free Stack — Complete Breakdown

Every component is free. No credit card required for any of these.

|Layer                         |Technology                          |Why Free                                                  |Limit That Matters                      |
|------------------------------|------------------------------------|----------------------------------------------------------|----------------------------------------|
|**Frontend**                  |React 19 + Vite + Tailwind on Vercel|Free tier, unlimited static                               |None for personal use                   |
|**Backend API + Telegram Bot**|FastAPI (Python) on Fly.io          |Free tier: 3 shared CPUs, 256MB RAM, always-on (no sleep) |160GB bandwidth/month                   |
|**Scheduler**                 |GitHub Actions (cron)               |Public repo = unlimited minutes; private = 2,000 min/month|~10 min per run × 12/day = OK on private|
|**Database + Auth + Storage** |Supabase free tier                  |500MB DB, 1GB storage, 500K edge invocations              |500MB DB (plenty for MVP)               |
|**AI Stages 1 & 2**           |Groq API free tier (LLaMA 3.3 70B)  |No credit card, no cost                                   |~14,400 req/day — more than enough      |
|**AI Stage 3**                |Gemini Flash via Google AI Studio   |Free tier: 1,500 req/day, 15 RPM                          |1,500 scored jobs/day — sufficient      |
|**Web Scraping**              |Jina AI Reader (r.jina.ai)          |Completely free, no key needed                            |~10 req/min safe rate                   |
|**RSS Parsing**               |feedparser (Python library)         |Open source                                               |None                                    |
|**PDF Parsing**               |PyMuPDF / fitz (Python library)     |Open source                                               |None                                    |
|**GitHub Parsing**            |GitHub REST API                     |60 req/hr unauthenticated, 5,000 with free token          |None                                    |
|**Telegram Bot**              |python-telegram-bot                 |Always free                                               |None                                    |

**Jina AI replaces Firecrawl completely.** Usage: `GET https://r.jina.ai/{target_url}` — returns clean markdown, no API key, no registration. Covers most job boards. For heavy JavaScript-rendered pages that Jina can’t handle, requests + BeautifulSoup is the fallback (pure Python, free).

**Gemini is free separately from his Google One plan.** Google AI Studio (aistudio.google.com) provides free Gemini API access with no payment required — just a Google account. His Google One plan doesn’t affect this; the free API tier exists independently.

**Fly.io instead of Render** because Fly.io’s free tier doesn’t sleep (it uses a VM model, not a process model). Render’s free tier spins down after 15 minutes, which would break the Telegram bot and cause slow first loads. Fly.io stays warm.

-----

## 5. Architecture — Free Stack

```
┌──────────────────────────────────────────────────────────────┐
│                   React 19 Frontend                          │
│              (Vite + Tailwind + shadcn/ui)                   │
│                   Deployed on Vercel                         │
│  Dashboard │ Sources │ Profile │ Bulk Import │ Analytics     │
└───────────────────────┬──────────────────────────────────────┘
                        │ REST API + Supabase Realtime
┌───────────────────────▼──────────────────────────────────────┐
│         FastAPI Backend + Telegram Bot                       │
│                  Deployed on Fly.io                          │
│                  (always-on, no sleep)                       │
│  API routes: /jobs /sources /profile /resume /auth /health   │
│  Telegram bot: polling mode, runs continuously               │
└──────────────┬────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────┐
│                    Supabase                                  │
│       PostgreSQL + Auth + Storage (resume PDFs)              │
│              Realtime subscriptions                          │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│           GitHub Actions Scheduler (cron)                    │
│   Runs every 2 hours. Completely separate from backend.      │
│                                                              │
│  1. Read active sources from Supabase                        │
│  2. Fetch jobs: API clients + RSS (feedparser)               │
│  3. Scrape custom URLs: Jina AI → BeautifulSoup fallback     │
│  4. Deduplicate against existing jobs in Supabase            │
│  5. AI classify: Groq Stage 1 (remote) → Stage 2 (seniority) │
│  6. Score survivors: Gemini Flash Stage 3 (match score)      │
│  7. Write results to Supabase job_matches                    │
│  8. Trigger Telegram alerts for high-score matches           │
└──────────────────────────────────────────────────────────────┘

External free APIs:
  Groq (LLaMA 3.3 70B) │ Gemini Flash │ Jina AI │ GitHub API
```

**Why GitHub Actions for the scheduler?**
The scheduler is a batch process that runs every 2 hours — it doesn’t need to be part of the backend. GitHub Actions is a free, reliable cron runner. The Python script runs inside the Action, reads from/writes to Supabase directly, and calls Groq/Gemini. No always-on server needed just for scheduling. The backend (Fly.io) only handles user-facing API calls and the Telegram bot.

-----

## 6. Features

### 6.1 MVP (Build First)

-----

#### Feature 1 — Resume & Profile Setup

- Upload resume as PDF (stored in Supabase Storage)
- PyMuPDF extracts raw text → Groq LLaMA parses and structures it (skills, education, experience level, inferred roles)
- User reviews + edits parsed data before confirming
- **Natural language job description** — free-text box: *“I’m looking for entry-level or internship remote roles in data analysis, backend dev, or product. Open to being trained. Prefer USD/GBP/EUR. No country restrictions.”*
- Structured preferences (auto-populated from NL description, editable):
  - Target role categories (multi-select)
  - Seniority filter: Entry-level, Junior, Internship, Trainee (all on by default)
  - Min display score: 55 (low — user is very open)
  - Notification threshold: 70
  - Currency preference: Dollar/GBP/EUR preferred (soft signal — deprioritize local-currency-only roles, don’t hide them)
  - Notification frequency: Real-time or Daily digest

-----

#### Feature 2 — Source Library (Pre-loaded)

**2a. Job Boards Library — 60+ boards pre-loaded from awesome-remote-job repo**

Default enabled (free API or RSS — no scraping):

|Source          |Type|Endpoint                                         |
|----------------|----|-------------------------------------------------|
|Remotive        |API |`https://remotive.com/api/remote-jobs`           |
|Himalayas       |API |`https://himalayas.app/jobs/api`                 |
|Jobicy          |API |`https://jobicy.com/api/v2/remote-jobs`          |
|Arbeitnow       |API |`https://www.arbeitnow.com/api/job-board-api`    |
|RemoteOK        |API |`https://remoteok.com/api`                       |
|Working Nomads  |API |`https://www.workingnomads.com/api/exposed_jobs/`|
|We Work Remotely|RSS |`https://weworkremotely.com/remote-jobs.rss`     |
|Remote.co       |RSS |`https://remote.co/remote-jobs/feed/`            |

Available but disabled by default (require Jina AI scraping — free but slower):

Wellfound, Built In, Jobspresso, JustRemote, Career Vault, Daily Remote, JobsCollider, Remote Index, Findwork, Remote AI Jobs, Virtual Vocations, NODESK, Real Work From Anywhere, HN Hiring, Remote Backend Jobs, Dataaxy, and 40+ more from the library.

**2b. Company Career Pages (remoteintech/remote-jobs)**

900+ companies with career page URLs. User activates specific companies. System scans their pages daily via Jina AI.

-----

#### Feature 3 — Bulk URL Import + GitHub Repo Parser

**3a. Bulk URL Paste**

- Multiline textarea: paste one URL per line (50, 100, 200 at once)
- System processes each: detects type (API/RSS/Jina-scrape), deduplicates, quick validation fetch
- Results table: Valid / No jobs found / Error / Duplicate
- User selects which to activate

**3b. GitHub Repo Parser**

- User pastes any GitHub repo URL
- System fetches the README via GitHub API (free, 60 req/hr unauth)
- Groq LLaMA extracts all job board URLs from the README markdown
- Presents as selectable list for user to activate

**3c. Source Health Monitoring**
Per source, system tracks after every fetch:

- Last successful fetch datetime
- Jobs returned per run (rolling 7-day average)
- Error rate (last 10 runs)

Status badges: 🟢 Healthy | 🟡 Degraded | 🔴 Dead (auto-disabled at 3 errors) | ⚠️ Low Quality (fetches ok but most jobs fail remote filter)

User gets in-app notification + Telegram message when a source is auto-disabled.

-----

#### Feature 4 — AI Classification & Scoring Pipeline

Jobs are classified in 3 stages inside the GitHub Actions scheduler run.

**Groq handles Stages 1 & 2** (fast, free, structured JSON output)
**Only jobs that pass both stages go to Gemini for Stage 3** — this keeps Gemini API calls low.

**Stage 1 — Remote Verification (Groq LLaMA 3.3 70B)**

```
Prompt: Analyze this job listing. Is it available to workers anywhere in the world?
Return JSON only:
{
  "remote_type": "worldwide" | "us_only" | "eu_only" | "country_specific" | "hybrid_only" | "unknown",
  "confidence": "high" | "medium" | "low",
  "reason": "one sentence"
}

Job Title: {title}
Location Field: {location}
Description: {description}
```

Action: `us_only`, `eu_only`, `country_specific`, `hybrid_only` with high confidence → discard.
`unknown` → store, show with ⚠️ badge.

-----

**Stage 2 — Eligibility Check (Groq LLaMA 3.3 70B)**

```
Prompt: What seniority level and role type is this job?
Return JSON only:
{
  "seniority": "internship" | "entry" | "junior" | "mid" | "senior" | "lead" | "unknown",
  "role_type": "full-time" | "internship" | "contract" | "freelance" | "unknown",
  "years_required": number | null,
  "is_trainee_program": true | false,
  "confidence": "high" | "medium" | "low"
}

Job Title: {title}
Description: {description}
```

Action: `senior`/`lead` with high confidence → store but hide from main feed.

-----

**Stage 3 — Match Scoring (Gemini Flash — only for jobs that passed Stages 1 & 2)**

```
Prompt: Score this job against this candidate's profile.
Return JSON only:
{
  "score": 0-100,
  "match_reasons": ["max 4 specific reasons"],
  "currency_signal": "usd" | "gbp" | "eur" | "local" | "unknown",
  "disqualifiers": ["any red flags despite decent score"]
}

Candidate:
What I'm looking for: {natural_language_description}
Skills: {skills}
Acceptable seniority: {seniority_preference}

Job:
Title: {title}
Company: {company}
Stack/Tags: {tags}
Description: {description_excerpt_500_chars}
```

Score key: 90-100 near-perfect | 75-89 strong | 60-74 decent | 40-59 stretch | 0-39 weak.

-----

#### Feature 5 — Job Dashboard (Frontend)

**Main Feed:**

- Card layout: Title, Company, Source badge, Match score (colour-coded), Remote type, Role type (🎓 Internship / 🟢 Entry / 🔵 Junior), Posted time, Currency signal (💵💷💶❓)
- Status tabs: **New** | **Saved** | **Applied** | **All**
- Filters: Score range slider, Source, Date, Role type, Seniority
- Toggle: **Show senior roles** (off by default) | **Show unverified remote** (on by default)

**Job Detail Panel:**

- Full description, match breakdown, match reasons list, any disqualifiers, apply URL
- Actions: [Save] [Mark Applied] [Not Interested]
- Source health badge (so you know how reliable this source is)

**Sources Tab:**

- Two sections: **Job Boards** | **Company Career Pages**
- Per source: Name, Type, Health badge, Last fetched, Jobs last run, Pass rate
- Bulk import button | GitHub repo parser input
- Source library browser (all 60+ boards, filter by category)

**Profile Tab:**

- Natural language description (editable)
- Parsed skills (editable tags)
- Preferences (score thresholds, notification settings)
- Re-upload resume

**Analytics Tab:**

- Jobs seen/week/month
- Applications by status
- Top sources by match volume
- Match score distribution chart

-----

#### Feature 6 — Telegram Bot

**Account Linking:**

1. User sends `/start` to @JobPulseBot
1. Bot stores `(telegram_chat_id, 6-digit-code, expiry)` in Supabase
1. User enters code in app → linked
1. Bot confirms with settings summary

**Alert Format:**

```
🎯 New Match — 87/100

💼 Junior Data Analyst  [Entry-level]
🏢 Acme Corporation
🌍 Worldwide Remote | 💵 USD
📅 Posted 2h ago | Via: Remotive

✅ Python  ✅ SQL  ✅ Power BI

[Apply Now] [Save] [Not Interested]
```

**Bot Commands:**

|Command         |Action                |
|----------------|----------------------|
|`/start`        |Link account          |
|`/jobs`         |Top 5 current matches |
|`/pause`        |Pause notifications   |
|`/resume`       |Resume notifications  |
|`/threshold [n]`|Update score threshold|
|`/health`       |Source health summary |
|`/status`       |Current settings      |
|`/unlink`       |Unlink Telegram       |

Inline buttons update job status in Supabase via callback handlers on Fly.io backend.

-----

#### Feature 7 — Scraping Strategy (Free, No Firecrawl)

**Priority order for each source:**

1. **Official API** (if source has one) → fastest, most reliable, no scraping
1. **RSS feed** (if source has one) → also reliable, feedparser
1. **Jina AI Reader** → `GET https://r.jina.ai/{url}` → returns clean markdown, free, no key
1. **requests + BeautifulSoup** → fallback for Jina failures on simpler HTML pages

**Jina AI limitations to handle gracefully:**

- Rate limit: space requests ~6 seconds apart (10 req/min conservative)
- Some heavy SPA/auth-walled boards may return empty or partial content
- These get flagged as `⚠️ Low Quality` in source health after 3+ empty fetches
- User is shown: “This source may not scrape reliably — try adding a direct RSS or API URL for this board”

**GitHub Actions scheduler flow (every 2 hours):**

```python
for source in active_sources:
    if source.type == 'api':
        jobs = fetch_api(source.url)
    elif source.type == 'rss':
        jobs = fetch_rss(source.url)
    elif source.type == 'jina':
        raw = requests.get(f"https://r.jina.ai/{source.url}")
        jobs = groq_parse_jobs_from_markdown(raw.text)  # Groq extracts job listings
    
    new_jobs = deduplicate(jobs)
    
    for job in new_jobs:
        stage1 = groq_remote_check(job)
        if stage1.remote_type not in ['worldwide', 'unknown']:
            continue
        
        stage2 = groq_seniority_check(job)
        
        score_result = gemini_match_score(job, user_profile)
        
        save_to_supabase(job, score_result)
        
        if score_result.score >= user.notification_threshold:
            send_telegram_alert(job, score_result)
```

Note: Groq also handles job parsing from Jina markdown (extracting structured job listings from raw page content). This is a 4th use of Groq — cheap since free.

-----

#### Feature 8 — Scheduler (GitHub Actions)

`.github/workflows/job-fetch.yml`:

```yaml
name: JobPulse Job Fetcher
on:
  schedule:
    - cron: '0 */2 * * *'  # Every 2 hours
  workflow_dispatch:         # Manual trigger from GitHub UI

jobs:
  fetch-and-score:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r scheduler/requirements.txt
      - run: python scheduler/main.py
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
          GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
```

Secrets stored in GitHub repo Settings → Secrets and Variables → Actions.
Manual trigger available from the GitHub Actions tab for on-demand runs.

-----

### 6.2 Post-MVP (Future Phases)

**Phase 2:** Email digest, advanced health monitoring, source quality scoring, application analytics

**Phase 3:** Auto-apply (AI cover letter + form fill), interview prep, referral detection

**Phase 4:** Multi-user SaaS mode

-----

## 7. Data Models

### `users`

|Column                |Type     |Notes                |
|----------------------|---------|---------------------|
|id                    |uuid     |PK                   |
|email                 |text     |                     |
|telegram_chat_id      |bigint   |Null until linked    |
|notification_threshold|int      |Default: 70          |
|notification_frequency|text     |`realtime` or `daily`|
|daily_digest_time     |time     |Default: 08:00       |
|created_at            |timestamp|                     |

### `user_profiles`

|Column                      |Type   |Notes                                           |
|----------------------------|-------|------------------------------------------------|
|user_id                     |uuid   |FK → users, PK                                  |
|natural_language_description|text   |Free-text description of what they want         |
|target_roles                |jsonb  |Array of role strings                           |
|skills                      |jsonb  |Array of skill strings                          |
|seniority_levels            |jsonb  |Default: `["internship","entry","junior"]`      |
|role_types                  |jsonb  |Default: `["full-time","internship","contract"]`|
|min_display_score           |int    |Default: 55                                     |
|currency_preference         |text   |`usd_gbp_eur` or `any`                          |
|show_senior                 |boolean|Default: false                                  |
|show_unverified_remote      |boolean|Default: true                                   |

### `resumes`

|Column                 |Type     |Notes                |
|-----------------------|---------|---------------------|
|id                     |uuid     |PK                   |
|user_id                |uuid     |FK                   |
|raw_text               |text     |Extracted from PDF   |
|parsed_skills          |jsonb    |                     |
|parsed_experience_years|float    |                     |
|storage_path           |text     |Supabase Storage path|
|created_at             |timestamp|                     |

### `job_sources`

|Column                  |Type     |Notes                                       |
|------------------------|---------|--------------------------------------------|
|id                      |uuid     |PK                                          |
|name                    |text     |Display name                                |
|url                     |text     |API/RSS/page URL                            |
|source_type             |text     |`api`, `rss`, `jina`, `company_page`        |
|category                |text     |e.g. “Aggregator”, “Tech”, “Company”        |
|is_library              |boolean  |True = pre-loaded from GitHub repos         |
|user_id                 |uuid     |Null for library sources                    |
|is_active               |boolean  |                                            |
|health_status           |text     |`healthy`, `degraded`, `dead`, `low_quality`|
|consecutive_errors      |int      |Auto-disable at 3                           |
|last_fetched            |timestamp|                                            |
|last_job_count          |int      |                                            |
|jobs_passing_filter_rate|float    |7-day rolling avg                           |

### `jobs`

|Column         |Type     |Notes                                                           |
|---------------|---------|----------------------------------------------------------------|
|id             |uuid     |PK                                                              |
|source_id      |uuid     |FK                                                              |
|external_id    |text     |URL or ID from source                                           |
|title          |text     |                                                                |
|company        |text     |                                                                |
|remote_type    |text     |`worldwide`, `us_only`, `eu_only`, `country_specific`, `unknown`|
|seniority      |text     |`internship`, `entry`, `junior`, `mid`, `senior`, `unknown`     |
|role_type      |text     |`full-time`, `internship`, `contract`, `freelance`, `unknown`   |
|is_trainee     |boolean  |                                                                |
|description    |text     |                                                                |
|apply_url      |text     |                                                                |
|salary_range   |text     |                                                                |
|currency_signal|text     |`usd`, `gbp`, `eur`, `local`, `unknown`                         |
|tags           |jsonb    |Tech stack tags                                                 |
|posted_at      |timestamp|                                                                |
|fetched_at     |timestamp|                                                                |
|dedup_hash     |text     |`MD5(lower(title)+lower(company))`                              |

### `job_matches`

|Column            |Type     |Notes                                        |
|------------------|---------|---------------------------------------------|
|id                |uuid     |PK                                           |
|job_id            |uuid     |FK                                           |
|user_id           |uuid     |FK                                           |
|match_score       |int      |0-100                                        |
|match_reasons     |jsonb    |Array of strings (max 4)                     |
|disqualifiers     |jsonb    |Array of warning strings                     |
|remote_verified   |boolean  |                                             |
|seniority_verified|boolean  |                                             |
|status            |text     |`new`, `seen`, `saved`, `applied`, `rejected`|
|telegram_notified |boolean  |                                             |
|created_at        |timestamp|                                             |

### `source_imports`

|Column        |Type     |Notes                      |
|--------------|---------|---------------------------|
|id            |uuid     |PK                         |
|user_id       |uuid     |FK                         |
|import_type   |text     |`bulk_paste`, `github_repo`|
|raw_input     |text     |                           |
|urls_found    |int      |                           |
|urls_valid    |int      |                           |
|urls_activated|int      |                           |
|created_at    |timestamp|                           |

### `scheduler_logs`

|Column       |Type     |Notes            |
|-------------|---------|-----------------|
|id           |uuid     |PK               |
|source_id    |uuid     |FK               |
|run_at       |timestamp|                 |
|jobs_fetched |int      |                 |
|jobs_new     |int      |After dedup      |
|jobs_passed  |int      |After AI pipeline|
|error_message|text     |Nullable         |

### `telegram_link_codes`

|Column          |Type     |Notes        |
|----------------|---------|-------------|
|telegram_chat_id|bigint   |             |
|code            |text     |6-digit code |
|expires_at      |timestamp|10 min expiry|
|used            |boolean  |             |

-----

## 8. Environment Variables

```
# Supabase
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=    # Backend + scheduler (server-side only)
VITE_SUPABASE_URL=            # Frontend (public)
VITE_SUPABASE_ANON_KEY=       # Frontend (public)

# AI — all free
GROQ_API_KEY=                 # free at console.groq.com
GEMINI_API_KEY=               # free at aistudio.google.com

# Telegram
TELEGRAM_BOT_TOKEN=           # from @BotFather

# GitHub (optional — increases rate limit from 60 to 5000 req/hr)
GITHUB_TOKEN=                 # free personal access token
```

-----

## 9. Repo Structure

```
jobpulse/
├── .github/
│   └── workflows/
│       └── job-fetch.yml       # GitHub Actions scheduler
│
├── frontend/                   # React 19 + Vite + Tailwind
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Dashboard.jsx
│   │   │   ├── Sources.jsx
│   │   │   ├── Profile.jsx
│   │   │   └── Analytics.jsx
│   │   ├── components/
│   │   └── lib/supabase.js
│   └── package.json
│
├── backend/                    # FastAPI on Fly.io
│   ├── main.py                 # FastAPI app + Telegram bot (polling)
│   ├── routes/
│   ├── fly.toml                # Fly.io config
│   └── requirements.txt
│
├── scheduler/                  # Runs inside GitHub Actions
│   ├── main.py                 # Entry point
│   ├── fetchers/
│   │   ├── api_fetcher.py
│   │   ├── rss_fetcher.py
│   │   └── jina_fetcher.py
│   ├── pipeline/
│   │   ├── stage1_remote.py
│   │   ├── stage2_seniority.py
│   │   └── stage3_score.py
│   ├── notifier.py             # Telegram alerts
│   └── requirements.txt
│
└── supabase/
    └── migrations/             # All SQL schema migrations
```

-----

## 10. MVP Build Order

1. **Supabase schema** — All tables + RLS policies + migrations
1. **Resume upload + AI parsing** — PDF → PyMuPDF → Groq → structured profile
1. **API/RSS fetchers** — Remotive, Himalayas, Arbeitnow, RemoteOK, WWR, RSS feeds working
1. **GitHub Actions scheduler** — Skeleton cron job, runs fetchers, logs to Supabase
1. **AI pipeline** — Groq stage 1 + 2, Gemini stage 3, results in job_matches
1. **Dashboard feed** — React frontend showing scored job cards
1. **Status tracking** — Save / Apply / Not Interested working
1. **Source library** — Pre-loaded 60+ boards, activate/deactivate per source
1. **Jina AI scraping** — Enable non-API sources from the library
1. **Bulk URL import** — Paste-many-URLs feature
1. **GitHub repo parser** — Extract job boards from any GitHub README
1. **Source health monitoring** — Badges, auto-disable dead sources
1. **Telegram bot** — Linking + alerts with inline buttons (running on Fly.io)
1. **FastAPI backend** — REST API for frontend interactions, deployed Fly.io
1. **Polish** — Filters, analytics tab, dark mode, mobile layout

-----

## 11. Free Tier Limits & What Happens When You Hit Them

|Service       |Limit                    |What Happens           |Fix                                                                      |
|--------------|-------------------------|-----------------------|-------------------------------------------------------------------------|
|Groq          |~14,400 req/day          |Jobs stop classifying  |Spread runs over time; unlikely to hit with personal use                 |
|Gemini Flash  |1,500 req/day            |Stage 3 stops          |Pre-filter aggressively in Stages 1-2; only ~20-30% of jobs reach Stage 3|
|Supabase DB   |500MB                    |DB full                |Archive old job_matches rows; unlikely in first 6 months                 |
|GitHub Actions|2,000 min/month (private)|Scheduler stops running|Make repo public OR reduce frequency to every 4hrs                       |
|Fly.io        |3 shared CPUs, 256MB     |Slow response          |Optimize; or move to paid if traffic justifies                           |
|Jina AI       |~10 req/min              |Scraping slows         |Add delays between requests; already handled                             |

**Safe operating range at MVP scale:** well within all free limits. A personal job search tool is nowhere near hitting these thresholds.

-----

*Status: PRD v3.0 complete — fully free stack. Next: Antigravity build prompt.*