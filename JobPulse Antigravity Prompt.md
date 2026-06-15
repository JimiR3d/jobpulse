# JobPulse — Full Build Prompt for Antigravity

> Paste this entire file into Antigravity. All manual setup steps are labeled ⚠️ MANUAL ACTION and must be completed by the user before or during the relevant build step. Everything else Antigravity builds autonomously.

-----

## PROJECT OVERVIEW

You are building **JobPulse** — a personal AI-powered remote job aggregator and scorer. It monitors 60+ remote job boards, scores every job against the user’s resume and preferences using AI, and sends Telegram alerts when high-match jobs drop.

**Core value:** Jimi (the user) is a CS grad based in Lagos, Nigeria, hunting for fully worldwide-remote, entry-level or internship roles paying in USD/GBP/EUR. He needs a tool that:

- Automatically monitors dozens of job boards every 2 hours
- Filters out jobs that are “remote in US/EU only” (the majority of “remote” listings)
- Scores remaining jobs against his skills and preferences
- Alerts him on Telegram with only the high-match ones
- Lets him track which jobs he’s seen, saved, and applied to

**Monthly cost: $0.** Every component uses a free tier.

-----

## COMPLETE TECH STACK

|Layer                     |Technology                                                         |
|--------------------------|-------------------------------------------------------------------|
|Frontend                  |React 19, Vite, Tailwind CSS, shadcn/ui — deployed on Vercel (free)|
|Backend API + Telegram Bot|FastAPI (Python 3.12) — deployed on Fly.io (free tier, always-on)  |
|Scheduler                 |GitHub Actions cron (every 2 hours) — Python script, free          |
|Database + Auth + Storage |Supabase free tier                                                 |
|AI Stages 1 & 2           |Groq API free tier — LLaMA 3.3 70B, structured JSON output         |
|AI Stage 3                |Google Gemini Flash — via Google AI Studio (free tier)             |
|Web Scraping              |Jina AI Reader (r.jina.ai) — free, no key needed                   |
|RSS Parsing               |feedparser (Python)                                                |
|PDF Parsing               |PyMuPDF (fitz)                                                     |
|Telegram Bot              |python-telegram-bot                                                |

-----

## ACCOUNTS & API KEYS NEEDED

```
SUPABASE_URL=               # from supabase.com project settings
SUPABASE_ANON_KEY=          # from supabase.com project settings (public)
SUPABASE_SERVICE_ROLE_KEY=  # from supabase.com project settings (secret)
GROQ_API_KEY=               # from console.groq.com (free)
GEMINI_API_KEY=             # from aistudio.google.com (free)
TELEGRAM_BOT_TOKEN=         # from @BotFather on Telegram
GITHUB_TOKEN=               # optional — free personal access token, raises GitHub API rate limit
```

-----

## REPO STRUCTURE TO CREATE

```
jobpulse/
├── .github/
│   └── workflows/
│       └── job-fetch.yml          # GitHub Actions cron scheduler
│
├── frontend/                      # React 19 app
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Dashboard.jsx      # Main job feed
│   │   │   ├── Sources.jsx        # Source library + bulk import
│   │   │   ├── Profile.jsx        # Resume + preferences
│   │   │   └── Analytics.jsx      # Stats
│   │   ├── components/
│   │   │   ├── JobCard.jsx
│   │   │   ├── SourceCard.jsx
│   │   │   ├── ScoreBadge.jsx
│   │   │   ├── HealthBadge.jsx
│   │   │   └── TelegramLink.jsx
│   │   ├── lib/
│   │   │   └── supabase.js
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── index.html
│   ├── vite.config.js
│   ├── tailwind.config.js
│   └── package.json
│
├── backend/                       # FastAPI app
│   ├── main.py                    # App entry + Telegram bot polling
│   ├── routes/
│   │   ├── jobs.py                # GET /jobs, PATCH /jobs/{id}/status
│   │   ├── sources.py             # CRUD for job sources
│   │   ├── profile.py             # Resume upload + profile
│   │   ├── imports.py             # Bulk URL paste + GitHub parser
│   │   └── telegram.py            # /telegram/link, /telegram/verify
│   ├── services/
│   │   ├── resume_parser.py       # PDF → PyMuPDF → Groq parse
│   │   └── github_parser.py       # GitHub README → Groq extract URLs
│   ├── fly.toml
│   ├── Dockerfile
│   └── requirements.txt
│
├── scheduler/                     # Runs inside GitHub Actions
│   ├── main.py                    # Entry point
│   ├── fetchers/
│   │   ├── api_fetcher.py         # Hits JSON APIs
│   │   ├── rss_fetcher.py         # Parses RSS feeds
│   │   └── jina_fetcher.py        # Jina AI scraping + BeautifulSoup fallback
│   ├── pipeline/
│   │   ├── stage1_remote.py       # Groq: remote verification
│   │   ├── stage2_seniority.py    # Groq: seniority + role type
│   │   └── stage3_score.py        # Gemini: match scoring
│   ├── notifier.py                # Telegram alert sender
│   ├── deduplicator.py            # MD5 hash dedup
│   └── requirements.txt
│
└── supabase/
    └── migrations/
        └── 001_initial_schema.sql
```

-----

## STEP 1 — SUPABASE SCHEMA

⚠️ **MANUAL ACTION 1: Create Supabase Project**

```
1. Go to https://supabase.com → sign up (free)
2. Create a new project
3. From Project Settings → API, copy:
   - Project URL → SUPABASE_URL
   - anon public key → SUPABASE_ANON_KEY
   - service_role secret key → SUPABASE_SERVICE_ROLE_KEY
4. From Storage tab → Create a new bucket called "resumes" (set to private)
```

Create `supabase/migrations/001_initial_schema.sql` with the following — then run it in Supabase SQL Editor:

```sql
-- Extensions
create extension if not exists "uuid-ossp";
create extension if not exists "pgcrypto";

-- ─────────────────────────────────────────
-- USERS (mirrors auth.users)
-- ─────────────────────────────────────────
create table public.users (
  id uuid references auth.users(id) on delete cascade primary key,
  email text not null,
  telegram_chat_id bigint unique,
  notification_threshold int default 70 check (notification_threshold between 0 and 100),
  notification_frequency text default 'realtime' check (notification_frequency in ('realtime', 'daily')),
  daily_digest_time time default '08:00',
  created_at timestamptz default now()
);

-- Auto-create user row on auth signup
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer as $$
begin
  insert into public.users (id, email)
  values (new.id, new.email);
  insert into public.user_profiles (user_id)
  values (new.id);
  return new;
end;
$$;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

-- ─────────────────────────────────────────
-- USER PROFILES
-- ─────────────────────────────────────────
create table public.user_profiles (
  user_id uuid references public.users(id) on delete cascade primary key,
  natural_language_description text,
  target_roles jsonb default '[]'::jsonb,
  skills jsonb default '[]'::jsonb,
  seniority_levels jsonb default '["internship","entry","junior"]'::jsonb,
  role_types jsonb default '["full-time","internship","contract"]'::jsonb,
  min_display_score int default 55,
  currency_preference text default 'usd_gbp_eur',
  show_senior boolean default false,
  show_unverified_remote boolean default true
);

-- ─────────────────────────────────────────
-- RESUMES
-- ─────────────────────────────────────────
create table public.resumes (
  id uuid default uuid_generate_v4() primary key,
  user_id uuid references public.users(id) on delete cascade,
  raw_text text,
  parsed_skills jsonb default '[]'::jsonb,
  parsed_experience_years float,
  storage_path text,
  created_at timestamptz default now()
);

-- ─────────────────────────────────────────
-- JOB SOURCES
-- ─────────────────────────────────────────
create table public.job_sources (
  id uuid default uuid_generate_v4() primary key,
  name text not null,
  url text not null,
  source_type text not null check (source_type in ('api', 'rss', 'jina', 'company_page')),
  category text default 'General',
  is_library boolean default false,
  user_id uuid references public.users(id) on delete cascade,
  is_active boolean default true,
  health_status text default 'healthy' check (health_status in ('healthy','degraded','dead','low_quality')),
  consecutive_errors int default 0,
  last_fetched timestamptz,
  last_job_count int default 0,
  jobs_passing_filter_rate float default 0,
  created_at timestamptz default now()
);

-- Seed default library sources (pre-loaded, is_library=true, user_id=null)
insert into public.job_sources (name, url, source_type, category, is_library, user_id, is_active) values
  ('Remotive', 'https://remotive.com/api/remote-jobs', 'api', 'Aggregator', true, null, true),
  ('Himalayas', 'https://himalayas.app/jobs/api', 'api', 'Aggregator', true, null, true),
  ('Jobicy', 'https://jobicy.com/api/v2/remote-jobs', 'api', 'Aggregator', true, null, true),
  ('Arbeitnow', 'https://www.arbeitnow.com/api/job-board-api', 'api', 'Aggregator', true, null, true),
  ('RemoteOK', 'https://remoteok.com/api', 'api', 'Aggregator', true, null, true),
  ('Working Nomads', 'https://www.workingnomads.com/api/exposed_jobs/', 'api', 'General', true, null, true),
  ('We Work Remotely', 'https://weworkremotely.com/remote-jobs.rss', 'rss', 'General', true, null, true),
  ('Remote.co', 'https://remote.co/remote-jobs/feed/', 'rss', 'General', true, null, true),
  ('Wellfound', 'https://wellfound.com/jobs/remote', 'jina', 'Startups', true, null, false),
  ('Built In', 'https://builtin.com/jobs/remote', 'jina', 'Tech', true, null, false),
  ('Jobspresso', 'https://jobspresso.co/', 'jina', 'General', true, null, false),
  ('JustRemote', 'https://justremote.co', 'jina', 'General', true, null, false),
  ('Daily Remote', 'https://dailyremote.com', 'jina', 'General', true, null, false),
  ('JobsCollider', 'https://jobscollider.com/remote-jobs', 'jina', 'Aggregator', true, null, false),
  ('Remote Index', 'https://remoteindex.co/', 'jina', 'Aggregator', true, null, false),
  ('Findwork', 'https://findwork.dev/', 'jina', 'Tech', true, null, false),
  ('Remote AI Jobs', 'https://www.moaijobs.com/remote-ai-jobs', 'jina', 'AI/Data', true, null, false),
  ('Remote Backend Jobs', 'https://www.remotebackendjobs.com/', 'jina', 'Backend', true, null, false),
  ('Remote Frontend Jobs', 'https://www.remotefrontendjobs.com/', 'jina', 'Frontend', true, null, false),
  ('Virtual Vocations', 'https://www.virtualvocations.com/', 'jina', 'General', true, null, false),
  ('NODESK', 'https://nodesk.co/remote-jobs/', 'jina', 'General', true, null, false),
  ('Real Work From Anywhere', 'https://www.realworkfromanywhere.com/', 'jina', 'Worldwide', true, null, false),
  ('HN Hiring', 'https://www.hnhiring.me/', 'jina', 'Tech', true, null, false),
  ('Career Vault', 'https://careervault.io/', 'jina', 'Aggregator', true, null, false),
  ('4 Day Week', 'https://4dayweek.io', 'jina', 'General', true, null, false),
  ('Dataaxy', 'https://dataaxy.com', 'jina', 'AI/Data', true, null, false),
  ('Freel', 'https://freel.ai', 'jina', 'AI/Data', true, null, false),
  ('Remote.io', 'https://www.remote.io/', 'jina', 'Aggregator', true, null, false),
  ('Authentic Jobs', 'https://authenticjobs.com/?search_location=remote', 'jina', 'Tech', true, null, false),
  ('Skip the Drive', 'https://www.skipthedrive.com/', 'jina', 'General', true, null, false);

-- ─────────────────────────────────────────
-- JOBS
-- ─────────────────────────────────────────
create table public.jobs (
  id uuid default uuid_generate_v4() primary key,
  source_id uuid references public.job_sources(id),
  external_id text,
  title text not null,
  company text not null,
  remote_type text default 'unknown',
  seniority text default 'unknown',
  role_type text default 'unknown',
  is_trainee boolean default false,
  description text,
  apply_url text,
  salary_range text,
  currency_signal text default 'unknown',
  tags jsonb default '[]'::jsonb,
  posted_at timestamptz,
  fetched_at timestamptz default now(),
  dedup_hash text unique
);
create index idx_jobs_dedup_hash on public.jobs(dedup_hash);
create index idx_jobs_fetched_at on public.jobs(fetched_at desc);

-- ─────────────────────────────────────────
-- JOB MATCHES
-- ─────────────────────────────────────────
create table public.job_matches (
  id uuid default uuid_generate_v4() primary key,
  job_id uuid references public.jobs(id) on delete cascade,
  user_id uuid references public.users(id) on delete cascade,
  match_score int check (match_score between 0 and 100),
  match_reasons jsonb default '[]'::jsonb,
  disqualifiers jsonb default '[]'::jsonb,
  remote_verified boolean default false,
  seniority_verified boolean default false,
  status text default 'new' check (status in ('new','seen','saved','applied','rejected')),
  telegram_notified boolean default false,
  created_at timestamptz default now(),
  unique(job_id, user_id)
);
create index idx_job_matches_user_status on public.job_matches(user_id, status);
create index idx_job_matches_score on public.job_matches(match_score desc);

-- ─────────────────────────────────────────
-- SOURCE IMPORTS
-- ─────────────────────────────────────────
create table public.source_imports (
  id uuid default uuid_generate_v4() primary key,
  user_id uuid references public.users(id) on delete cascade,
  import_type text check (import_type in ('bulk_paste','github_repo')),
  raw_input text,
  urls_found int default 0,
  urls_valid int default 0,
  urls_activated int default 0,
  created_at timestamptz default now()
);

-- ─────────────────────────────────────────
-- SCHEDULER LOGS
-- ─────────────────────────────────────────
create table public.scheduler_logs (
  id uuid default uuid_generate_v4() primary key,
  source_id uuid references public.job_sources(id),
  run_at timestamptz default now(),
  jobs_fetched int default 0,
  jobs_new int default 0,
  jobs_passed int default 0,
  error_message text
);

-- ─────────────────────────────────────────
-- TELEGRAM LINK CODES
-- ─────────────────────────────────────────
create table public.telegram_link_codes (
  id uuid default uuid_generate_v4() primary key,
  telegram_chat_id bigint,
  code text not null,
  expires_at timestamptz not null,
  used boolean default false,
  created_at timestamptz default now()
);

-- ─────────────────────────────────────────
-- ROW LEVEL SECURITY
-- ─────────────────────────────────────────
alter table public.users enable row level security;
alter table public.user_profiles enable row level security;
alter table public.resumes enable row level security;
alter table public.job_sources enable row level security;
alter table public.jobs enable row level security;
alter table public.job_matches enable row level security;
alter table public.source_imports enable row level security;
alter table public.scheduler_logs enable row level security;
alter table public.telegram_link_codes enable row level security;

create policy "users_own" on public.users for all using (auth.uid() = id);
create policy "profiles_own" on public.user_profiles for all using (auth.uid() = user_id);
create policy "resumes_own" on public.resumes for all using (auth.uid() = user_id);
create policy "sources_read_library" on public.job_sources for select using (is_library = true or auth.uid() = user_id);
create policy "sources_manage_own" on public.job_sources for all using (auth.uid() = user_id);
create policy "jobs_read_all" on public.jobs for select using (true);
create policy "matches_own" on public.job_matches for all using (auth.uid() = user_id);
create policy "imports_own" on public.source_imports for all using (auth.uid() = user_id);
create policy "logs_read_all" on public.scheduler_logs for select using (true);
create policy "telegram_codes_all" on public.telegram_link_codes for all using (true);
```

-----

## STEP 2 — GITHUB ACTIONS SCHEDULER

⚠️ **MANUAL ACTION 2: Create GitHub Repository**

```
1. Create a new GitHub repo called "jobpulse" (can be public for unlimited free Actions minutes)
2. Go to Settings → Secrets and Variables → Actions → New repository secret
3. Add all secrets: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, GROQ_API_KEY, GEMINI_API_KEY, TELEGRAM_BOT_TOKEN
   (GITHUB_TOKEN is automatically available in Actions as secrets.GITHUB_TOKEN)
```

Create `.github/workflows/job-fetch.yml`:

```yaml
name: JobPulse Scheduler
on:
  schedule:
    - cron: '0 */2 * * *'   # Every 2 hours
  workflow_dispatch:          # Manual trigger from GitHub Actions tab

jobs:
  fetch-and-score:
    runs-on: ubuntu-latest
    timeout-minutes: 25
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: pip install -r scheduler/requirements.txt
      - name: Run scheduler
        run: python scheduler/main.py
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
          GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
```

Create `scheduler/requirements.txt`:

```
supabase==2.9.1
groq==0.11.0
google-generativeai==0.8.3
feedparser==6.0.11
requests==2.32.3
beautifulsoup4==4.12.3
PyMuPDF==1.24.10
python-telegram-bot==21.6
```

-----

## STEP 3 — SCHEDULER: FETCHERS

Create `scheduler/fetchers/api_fetcher.py`:

```python
import requests
import time
from typing import List, Dict

def normalize_job(raw: dict, source_id: str) -> dict:
    """Normalize a raw job dict to the jobs table schema."""
    return {
        "source_id": source_id,
        "external_id": str(raw.get("id") or raw.get("url") or ""),
        "title": raw.get("title", "").strip(),
        "company": raw.get("company_name") or raw.get("company") or raw.get("organization") or "",
        "description": raw.get("description") or raw.get("description_short") or "",
        "apply_url": raw.get("url") or raw.get("apply_url") or raw.get("job_url") or "",
        "salary_range": raw.get("salary") or raw.get("salary_range") or "",
        "tags": raw.get("tags") or raw.get("skills") or raw.get("labels") or [],
        "posted_at": raw.get("publication_date") or raw.get("created_at") or raw.get("date") or None,
    }

def fetch_remotive(source_id: str) -> List[dict]:
    resp = requests.get("https://remotive.com/api/remote-jobs", timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return [normalize_job(j, source_id) for j in data.get("jobs", [])]

def fetch_himalayas(source_id: str) -> List[dict]:
    all_jobs = []
    page = 1
    while True:
        resp = requests.get(f"https://himalayas.app/jobs/api?limit=100&offset={(page-1)*100}", timeout=30)
        resp.raise_for_status()
        data = resp.json()
        jobs = data.get("jobs", [])
        if not jobs:
            break
        for j in jobs:
            all_jobs.append({
                "source_id": source_id,
                "external_id": str(j.get("slug") or j.get("id") or ""),
                "title": j.get("title", "").strip(),
                "company": j.get("company", {}).get("name") or j.get("companyName") or "",
                "description": j.get("description") or "",
                "apply_url": j.get("applicationLink") or j.get("url") or "",
                "salary_range": j.get("salary") or "",
                "tags": j.get("skills") or [],
                "posted_at": j.get("createdAt") or None,
            })
        page += 1
        if page > 10:  # Safety cap
            break
        time.sleep(1)
    return all_jobs

def fetch_jobicy(source_id: str) -> List[dict]:
    resp = requests.get("https://jobicy.com/api/v2/remote-jobs?count=50&industry=all", timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return [normalize_job(j, source_id) for j in data.get("jobs", [])]

def fetch_arbeitnow(source_id: str) -> List[dict]:
    resp = requests.get("https://www.arbeitnow.com/api/job-board-api", timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return [normalize_job(j, source_id) for j in data.get("data", [])]

def fetch_remoteok(source_id: str) -> List[dict]:
    # RemoteOK returns a JSON array; first item is metadata, skip it
    resp = requests.get("https://remoteok.com/api", timeout=30,
                        headers={"User-Agent": "JobPulse/1.0 (job aggregator)"})
    resp.raise_for_status()
    data = resp.json()
    jobs = [j for j in data if isinstance(j, dict) and j.get("id")]
    result = []
    for j in jobs:
        result.append({
            "source_id": source_id,
            "external_id": str(j.get("id") or ""),
            "title": j.get("position", "").strip(),
            "company": j.get("company") or "",
            "description": j.get("description") or "",
            "apply_url": j.get("apply_url") or j.get("url") or "",
            "salary_range": j.get("salary") or "",
            "tags": j.get("tags") or [],
            "posted_at": j.get("date") or None,
        })
    return result

def fetch_workingnomads(source_id: str) -> List[dict]:
    resp = requests.get("https://www.workingnomads.com/api/exposed_jobs/", timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return [normalize_job(j, source_id) for j in data]

API_FETCHERS = {
    "remotive.com": fetch_remotive,
    "himalayas.app": fetch_himalayas,
    "jobicy.com": fetch_jobicy,
    "arbeitnow.com": fetch_arbeitnow,
    "remoteok.com": fetch_remoteok,
    "workingnomads.com": fetch_workingnomads,
}

def fetch_from_api(source: dict) -> List[dict]:
    """Route to the correct fetcher based on URL domain."""
    url = source["url"]
    source_id = source["id"]
    for domain, fetcher in API_FETCHERS.items():
        if domain in url:
            return fetcher(source_id)
    # Generic fallback — attempt JSON GET
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list):
        return [normalize_job(j, source_id) for j in data]
    for key in ("jobs", "data", "results", "listings"):
        if key in data:
            return [normalize_job(j, source_id) for j in data[key]]
    return []
```

Create `scheduler/fetchers/rss_fetcher.py`:

```python
import feedparser
from typing import List, Dict

def fetch_rss(source: dict) -> List[dict]:
    feed = feedparser.parse(source["url"])
    jobs = []
    for entry in feed.entries:
        title = entry.get("title", "")
        # Skip non-job entries (categories, headers)
        if len(title) < 5:
            continue
        company = ""
        # Try to extract company from title "Role at Company" pattern
        if " at " in title:
            parts = title.rsplit(" at ", 1)
            title = parts[0].strip()
            company = parts[1].strip()
        jobs.append({
            "source_id": source["id"],
            "external_id": entry.get("link") or entry.get("id") or "",
            "title": title,
            "company": company,
            "description": entry.get("summary") or entry.get("description") or "",
            "apply_url": entry.get("link") or "",
            "salary_range": "",
            "tags": [],
            "posted_at": entry.get("published") or None,
        })
    return jobs
```

Create `scheduler/fetchers/jina_fetcher.py`:

```python
import requests
import time
from bs4 import BeautifulSoup
from typing import List, Dict
import re

JINA_BASE = "https://r.jina.ai/"
HEADERS = {"User-Agent": "JobPulse/1.0"}

def fetch_via_jina(url: str) -> str:
    """Fetch a URL via Jina AI Reader and return clean markdown text."""
    try:
        resp = requests.get(f"{JINA_BASE}{url}", timeout=45, headers=HEADERS)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        return ""

def fetch_via_beautifulsoup(url: str) -> str:
    """Fallback scraper for simpler HTML pages."""
    try:
        resp = requests.get(url, timeout=30, headers=HEADERS)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)
    except Exception as e:
        return ""

def fetch_jina_source(source: dict, groq_client) -> List[dict]:
    """
    Fetch a source via Jina AI, then use Groq to extract structured job listings
    from the raw markdown. Jina first, BeautifulSoup fallback.
    """
    raw_text = fetch_via_jina(source["url"])
    if len(raw_text) < 200:
        raw_text = fetch_via_beautifulsoup(source["url"])
    if len(raw_text) < 200:
        return []

    # Truncate to 8000 chars to stay within Groq context limits
    truncated = raw_text[:8000]

    prompt = f"""Extract all job listings from this webpage content. Return ONLY valid JSON array, no other text.
Each job object must have these fields: title, company, apply_url, description_snippet (max 300 chars), tags (array of strings), salary_range.
If a field is not found, use empty string or empty array.
Only include actual job listings, not ads or navigation elements.
Return [] if no jobs found.

Content:
{truncated}"""

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=2000,
        )
        text = response.choices[0].message.content.strip()
        # Strip any markdown fences
        text = re.sub(r'^```json\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        import json
        raw_jobs = json.loads(text)
        if not isinstance(raw_jobs, list):
            return []
        
        result = []
        for j in raw_jobs:
            if not j.get("title"):
                continue
            result.append({
                "source_id": source["id"],
                "external_id": j.get("apply_url") or "",
                "title": j.get("title", "").strip(),
                "company": j.get("company", "").strip(),
                "description": j.get("description_snippet") or "",
                "apply_url": j.get("apply_url") or source["url"],
                "salary_range": j.get("salary_range") or "",
                "tags": j.get("tags") or [],
                "posted_at": None,
            })
        time.sleep(6)  # Jina rate limit: ~10 req/min
        return result
    except Exception as e:
        return []
```

-----

## STEP 4 — SCHEDULER: DEDUPLICATOR

Create `scheduler/deduplicator.py`:

```python
import hashlib
from supabase import Client
from typing import List, Dict

def make_hash(title: str, company: str) -> str:
    key = f"{title.lower().strip()}{company.lower().strip()}"
    return hashlib.md5(key.encode()).hexdigest()

def deduplicate(jobs: List[dict], supabase: Client) -> List[dict]:
    """Return only jobs not already in the database."""
    if not jobs:
        return []
    
    hashes = [make_hash(j["title"], j["company"]) for j in jobs]
    
    # Batch check against DB in chunks of 100
    existing_hashes = set()
    chunk_size = 100
    for i in range(0, len(hashes), chunk_size):
        chunk = hashes[i:i+chunk_size]
        resp = supabase.table("jobs").select("dedup_hash").in_("dedup_hash", chunk).execute()
        for row in resp.data:
            existing_hashes.add(row["dedup_hash"])
    
    new_jobs = []
    for job, h in zip(jobs, hashes):
        if h not in existing_hashes:
            job["dedup_hash"] = h
            new_jobs.append(job)
    
    return new_jobs
```

-----

## STEP 5 — SCHEDULER: AI PIPELINE

Create `scheduler/pipeline/stage1_remote.py`:

```python
import json
import re
from groq import Groq

PROMPT_TEMPLATE = """Analyze this job listing. Can workers based ANYWHERE in the world apply? No visa or residency requirements?
Return ONLY valid JSON, no other text:
{{"remote_type": "worldwide" | "us_only" | "eu_only" | "country_specific" | "hybrid_only" | "unknown", "confidence": "high" | "medium" | "low", "reason": "one sentence"}}

Definitions:
- worldwide: genuinely no country restriction, no right-to-work requirement
- us_only: requires US residency, citizenship, or US work authorization (look for "authorized to work in the US", "US only", US state mentions)
- eu_only: requires EU residency or European work authorization
- country_specific: restricted to a specific named country or small region
- hybrid_only: requires regular in-person attendance (not fully remote)
- unknown: genuinely insufficient information

Job Title: {title}
Location Field: {location}
Description: {description}"""

def check_remote(job: dict, client: Groq) -> dict:
    prompt = PROMPT_TEMPLATE.format(
        title=job.get("title", ""),
        location=job.get("location", ""),
        description=(job.get("description") or "")[:1500]
    )
    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=150,
        )
        text = resp.choices[0].message.content.strip()
        text = re.sub(r'^```json\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        result = json.loads(text)
        return result
    except Exception:
        return {"remote_type": "unknown", "confidence": "low", "reason": "parse error"}

DISCARD_TYPES = {"us_only", "eu_only", "country_specific", "hybrid_only"}

def should_discard(result: dict) -> bool:
    return result["remote_type"] in DISCARD_TYPES and result["confidence"] == "high"
```

Create `scheduler/pipeline/stage2_seniority.py`:

```python
import json
import re
from groq import Groq

PROMPT_TEMPLATE = """What seniority level and role type is this job?
Return ONLY valid JSON, no other text:
{{"seniority": "internship" | "entry" | "junior" | "mid" | "senior" | "lead" | "unknown", "role_type": "full-time" | "internship" | "contract" | "freelance" | "unknown", "years_required": number or null, "is_trainee_program": true | false, "confidence": "high" | "medium" | "low"}}

Seniority rules:
- internship: explicitly internship or co-op
- entry: 0-1 years, "entry-level", "new grad", "no experience required", "fresh graduate"
- junior: 1-2 years, or "junior" in title
- mid: 2-5 years, or role described without level (assume mid)
- senior: 5+ years, or "senior" in title
- lead: lead/principal/staff/director/VP/head

Job Title: {title}
Description: {description}"""

def check_seniority(job: dict, client: Groq) -> dict:
    prompt = PROMPT_TEMPLATE.format(
        title=job.get("title", ""),
        description=(job.get("description") or "")[:1500]
    )
    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=150,
        )
        text = resp.choices[0].message.content.strip()
        text = re.sub(r'^```json\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        return json.loads(text)
    except Exception:
        return {"seniority": "unknown", "role_type": "unknown", "years_required": None, "is_trainee_program": False, "confidence": "low"}
```

Create `scheduler/pipeline/stage3_score.py`:

```python
import json
import re
import google.generativeai as genai
import os

genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-1.5-flash")

PROMPT_TEMPLATE = """Score this job against this candidate's profile. Be generous — the candidate is very open to new roles.
Return ONLY valid JSON, no other text:
{{"score": 0-100, "match_reasons": ["max 4 specific reasons like 'Python required — in your resume'"], "currency_signal": "usd" | "gbp" | "eur" | "local" | "unknown", "disqualifiers": ["any red flags despite decent score, empty array if none"]}}

Scoring guide:
90-100: Near-perfect match (most skills align, perfect role type)
75-89: Strong match (most key requirements met)
60-74: Decent match (worth reviewing)
40-59: Stretch (some overlap, clear gaps)
0-39: Weak (minimal overlap)

currency_signal: detect from salary currency symbols, "USD", "per year/month in $", company HQ country, or job board context.

Candidate profile:
What I'm looking for: {nl_description}
Skills: {skills}
Acceptable seniority: {seniority}
Open to: internships, trainee programs, entry-level, junior roles

Job:
Title: {title}
Company: {company}
Tags/Stack: {tags}
Description (first 500 chars): {description}"""

def score_job(job: dict, user_profile: dict) -> dict:
    prompt = PROMPT_TEMPLATE.format(
        nl_description=user_profile.get("natural_language_description") or "Entry-level remote roles, willing to be trained",
        skills=", ".join(user_profile.get("skills") or []),
        seniority=", ".join(user_profile.get("seniority_levels") or ["entry", "junior", "internship"]),
        title=job.get("title", ""),
        company=job.get("company", ""),
        tags=", ".join(job.get("tags") or []),
        description=(job.get("description") or "")[:500],
    )
    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        text = re.sub(r'^```json\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        return json.loads(text)
    except Exception:
        return {"score": 50, "match_reasons": [], "currency_signal": "unknown", "disqualifiers": []}
```

-----

## STEP 6 — SCHEDULER: NOTIFIER

Create `scheduler/notifier.py`:

```python
import asyncio
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

async def send_job_alert(bot: Bot, chat_id: int, job: dict, match: dict):
    score = match["match_score"]
    reasons = match.get("match_reasons") or []
    
    # Score emoji
    if score >= 90: emoji = "🔥"
    elif score >= 75: emoji = "🎯"
    elif score >= 60: emoji = "✅"
    else: emoji = "📋"
    
    # Currency emoji
    currency_map = {"usd": "💵", "gbp": "💷", "eur": "💶"}
    curr_emoji = currency_map.get(match.get("currency_signal", ""), "❓")
    
    # Seniority badge
    seniority_badge = ""
    if job.get("seniority") == "internship": seniority_badge = "[🎓 Internship]"
    elif job.get("seniority") == "entry": seniority_badge = "[🟢 Entry-level]"
    elif job.get("seniority") == "junior": seniority_badge = "[🔵 Junior]"
    elif job.get("is_trainee"): seniority_badge = "[📚 Trainee Program]"
    
    reasons_text = "  ".join([f"✅ {r}" for r in reasons[:3]]) if reasons else ""
    
    text = (
        f"{emoji} *New Match — {score}/100*\n\n"
        f"💼 {job['title']} {seniority_badge}\n"
        f"🏢 {job['company']}\n"
        f"🌍 Worldwide Remote | {curr_emoji}\n"
        f"📅 Via: {job.get('source_name', 'Job Board')}\n\n"
        f"{reasons_text}"
    )
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Apply Now 🔗", url=job["apply_url"]),
            InlineKeyboardButton("Save ⭐", callback_data=f"save:{match['id']}"),
            InlineKeyboardButton("Not for me ✖️", callback_data=f"reject:{match['id']}"),
        ]
    ])
    
    await bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="Markdown",
        reply_markup=keyboard,
    )

def send_alerts(alerts: list, bot_token: str):
    """alerts = list of (chat_id, job, match) tuples"""
    bot = Bot(token=bot_token)
    async def run():
        for chat_id, job, match in alerts:
            try:
                await send_job_alert(bot, chat_id, job, match)
            except Exception as e:
                print(f"Telegram send error: {e}")
    asyncio.run(run())
```

-----

## STEP 7 — SCHEDULER: MAIN ENTRY POINT

Create `scheduler/main.py`:

```python
import os
import time
from supabase import create_client, Client
from groq import Groq

from fetchers.api_fetcher import fetch_from_api
from fetchers.rss_fetcher import fetch_rss
from fetchers.jina_fetcher import fetch_jina_source
from deduplicator import deduplicate, make_hash
from pipeline.stage1_remote import check_remote, should_discard
from pipeline.stage2_seniority import check_seniority
from pipeline.stage3_score import score_job
from notifier import send_alerts

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
groq_client = Groq(api_key=GROQ_API_KEY)

def get_active_sources():
    resp = supabase.table("job_sources").select("*").eq("is_active", True).neq("health_status", "dead").execute()
    return resp.data

def get_all_users_with_profiles():
    users = supabase.table("users").select("*, user_profiles(*)").execute()
    return users.data

def save_job(job: dict) -> str | None:
    try:
        resp = supabase.table("jobs").insert(job).execute()
        return resp.data[0]["id"] if resp.data else None
    except Exception:
        return None  # Likely duplicate, ignore

def save_match(job_id: str, user_id: str, stage1: dict, stage2: dict, score_result: dict) -> dict | None:
    match = {
        "job_id": job_id,
        "user_id": user_id,
        "match_score": score_result["score"],
        "match_reasons": score_result.get("match_reasons") or [],
        "disqualifiers": score_result.get("disqualifiers") or [],
        "remote_verified": stage1["remote_type"] == "worldwide",
        "seniority_verified": stage2["seniority"] in ("internship", "entry", "junior", "unknown"),
        "status": "new",
        "telegram_notified": False,
    }
    try:
        resp = supabase.table("job_matches").insert(match).execute()
        return resp.data[0] if resp.data else None
    except Exception:
        return None

def update_source_health(source_id: str, job_count: int, error: str | None, pass_rate: float):
    update = {
        "last_fetched": "now()",
        "last_job_count": job_count,
        "jobs_passing_filter_rate": pass_rate,
    }
    if error:
        supabase.table("job_sources").rpc("increment_source_errors", {"source_id_input": source_id}).execute()
    else:
        update["consecutive_errors"] = 0
        # Determine health status
        if pass_rate < 0.05 and job_count > 10:
            update["health_status"] = "low_quality"
        elif job_count == 0:
            update["health_status"] = "degraded"
        else:
            update["health_status"] = "healthy"
    supabase.table("job_sources").update(update).eq("id", source_id).execute()

def run():
    print("=== JobPulse Scheduler Starting ===")
    sources = get_active_sources()
    users = get_all_users_with_profiles()
    
    if not users:
        print("No users found. Exiting.")
        return
    
    pending_alerts = []
    
    for source in sources:
        print(f"\nFetching: {source['name']} ({source['source_type']})")
        raw_jobs = []
        error = None
        
        try:
            if source["source_type"] == "api":
                raw_jobs = fetch_from_api(source)
            elif source["source_type"] == "rss":
                raw_jobs = fetch_rss(source)
            elif source["source_type"] == "jina":
                raw_jobs = fetch_jina_source(source, groq_client)
        except Exception as e:
            error = str(e)
            print(f"  Error fetching {source['name']}: {e}")
        
        print(f"  Fetched {len(raw_jobs)} raw jobs")
        new_jobs = deduplicate(raw_jobs, supabase)
        print(f"  {len(new_jobs)} new after dedup")
        
        passed_count = 0
        
        for job in new_jobs:
            # Stage 1: Remote check
            stage1 = check_remote(job, groq_client)
            if should_discard(stage1):
                continue
            
            # Stage 2: Seniority check
            stage2 = check_seniority(job, groq_client)
            
            # Enrich job with classification data
            job["remote_type"] = stage1["remote_type"]
            job["seniority"] = stage2["seniority"]
            job["role_type"] = stage2["role_type"]
            job["is_trainee"] = stage2.get("is_trainee_program", False)
            
            # Save job to DB
            job_id = save_job(job)
            if not job_id:
                continue
            
            passed_count += 1
            
            # Stage 3: Score against each user
            for user in users:
                profile = user.get("user_profiles")
                if not profile:
                    continue
                
                # Skip seniors if user doesn't want them
                if stage2["seniority"] in ("senior", "lead") and not profile.get("show_senior"):
                    continue
                
                score_result = score_job(job, profile)
                score_result["currency_signal"] = score_result.get("currency_signal", "unknown")
                
                match = save_match(job_id, user["id"], stage1, stage2, score_result)
                
                if match and score_result["score"] >= user.get("notification_threshold", 70):
                    if user.get("telegram_chat_id") and user.get("notification_frequency") == "realtime":
                        job["source_name"] = source["name"]
                        pending_alerts.append((user["telegram_chat_id"], job, {**match, "currency_signal": score_result["currency_signal"]}))
            
            time.sleep(0.5)  # Groq rate limit buffer
        
        pass_rate = passed_count / max(len(raw_jobs), 1)
        update_source_health(source["id"], len(raw_jobs), error, pass_rate)
        
        # Log the run
        supabase.table("scheduler_logs").insert({
            "source_id": source["id"],
            "jobs_fetched": len(raw_jobs),
            "jobs_new": len(new_jobs),
            "jobs_passed": passed_count,
            "error_message": error,
        }).execute()
        
        print(f"  Passed AI pipeline: {passed_count}")
    
    # Send all Telegram alerts
    if pending_alerts:
        print(f"\nSending {len(pending_alerts)} Telegram alerts")
        send_alerts(pending_alerts, BOT_TOKEN)
    
    print("\n=== Scheduler Complete ===")

if __name__ == "__main__":
    run()
```

Add this SQL to Supabase to support the increment function:

```sql
create or replace function increment_source_errors(source_id_input uuid)
returns void language plpgsql as $$
begin
  update public.job_sources
  set
    consecutive_errors = consecutive_errors + 1,
    health_status = case when consecutive_errors + 1 >= 3 then 'dead' else 'degraded' end,
    is_active = case when consecutive_errors + 1 >= 3 then false else is_active end
  where id = source_id_input;
end;
$$;
```

-----

## STEP 8 — FASTAPI BACKEND

⚠️ **MANUAL ACTION 3: Create Telegram Bot**

```
1. Open Telegram → search @BotFather
2. Send /newbot → follow prompts → name it "JobPulse Bot", username "jobpulseai_bot" (or similar)
3. Copy the bot token → TELEGRAM_BOT_TOKEN
4. Send /setcommands to BotFather and set:
   start - Link your Telegram to JobPulse
   jobs - See your top 5 matches
   pause - Pause notifications
   resume - Resume notifications
   threshold - Update score threshold
   health - Source health summary
   status - Your current settings
   unlink - Unlink Telegram
```

Create `backend/requirements.txt`:

```
fastapi==0.115.5
uvicorn==0.32.1
supabase==2.9.1
python-multipart==0.0.12
PyMuPDF==1.24.10
groq==0.11.0
python-telegram-bot==21.6
python-dotenv==1.0.1
httpx==0.27.2
requests==2.32.3
```

Create `backend/main.py`:

```python
import os
import asyncio
import threading
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
import telegram_handlers

load_dotenv()

app = FastAPI(title="JobPulse API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production to your Vercel domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from routes import jobs, sources, profile, imports, telegram_routes
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(sources.router, prefix="/api/sources", tags=["sources"])
app.include_router(profile.router, prefix="/api/profile", tags=["profile"])
app.include_router(imports.router, prefix="/api/imports", tags=["imports"])
app.include_router(telegram_routes.router, prefix="/api/telegram", tags=["telegram"])

@app.get("/health")
def health():
    return {"status": "ok", "service": "JobPulse API"}

# Start Telegram bot polling in a background thread
def start_telegram_bot():
    telegram_handlers.run_bot(os.environ["TELEGRAM_BOT_TOKEN"])

@app.on_event("startup")
async def startup_event():
    thread = threading.Thread(target=start_telegram_bot, daemon=True)
    thread.start()
```

Create `backend/telegram_handlers.py` — handles all bot commands and callback buttons:

```python
import os
import random
import string
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from supabase import create_client

def get_supabase():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

def generate_code():
    return ''.join(random.choices(string.digits, k=6))

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    supabase = get_supabase()
    
    # Check if already linked
    resp = supabase.table("users").select("id, email").eq("telegram_chat_id", chat_id).execute()
    if resp.data:
        await update.message.reply_text(
            f"✅ Your Telegram is already linked to {resp.data[0]['email']}.\n"
            "Use /jobs to see your latest matches."
        )
        return
    
    # Generate link code
    code = generate_code()
    expires = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
    supabase.table("telegram_link_codes").insert({
        "telegram_chat_id": chat_id,
        "code": code,
        "expires_at": expires,
        "used": False,
    }).execute()
    
    await update.message.reply_text(
        f"👋 Welcome to JobPulse!\n\n"
        f"To link your account, go to the JobPulse web app and enter this code:\n\n"
        f"*{code}*\n\n"
        f"_(Code expires in 10 minutes)_",
        parse_mode="Markdown"
    )

async def cmd_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    supabase = get_supabase()
    
    user_resp = supabase.table("users").select("id").eq("telegram_chat_id", chat_id).execute()
    if not user_resp.data:
        await update.message.reply_text("❌ Account not linked. Send /start to link.")
        return
    
    user_id = user_resp.data[0]["id"]
    
    matches_resp = (
        supabase.table("job_matches")
        .select("*, jobs(*)")
        .eq("user_id", user_id)
        .eq("status", "new")
        .order("match_score", desc=True)
        .limit(5)
        .execute()
    )
    
    if not matches_resp.data:
        await update.message.reply_text("No new matches right now. Check back soon! 🔍")
        return
    
    await update.message.reply_text(f"Here are your top {len(matches_resp.data)} matches:\n")
    
    for m in matches_resp.data:
        job = m["jobs"]
        text = (
            f"🎯 *{m['match_score']}/100* — {job['title']}\n"
            f"🏢 {job['company']} | 🌍 Worldwide Remote\n"
        )
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("Apply 🔗", url=job["apply_url"]),
            InlineKeyboardButton("Save ⭐", callback_data=f"save:{m['id']}"),
        ]])
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)

async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _update_frequency(update, "paused")

async def cmd_resume_notifs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _update_frequency(update, "realtime")

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    supabase = get_supabase()
    resp = supabase.table("users").select("*, user_profiles(*)").eq("telegram_chat_id", chat_id).execute()
    if not resp.data:
        await update.message.reply_text("Not linked. Send /start")
        return
    u = resp.data[0]
    profile = (u.get("user_profiles") or [{}])[0] if isinstance(u.get("user_profiles"), list) else u.get("user_profiles") or {}
    await update.message.reply_text(
        f"⚙️ *Your JobPulse Settings*\n\n"
        f"📧 Account: {u['email']}\n"
        f"📊 Notification threshold: {u['notification_threshold']}/100\n"
        f"🔔 Frequency: {u['notification_frequency']}\n"
        f"🎯 Min display score: {profile.get('min_display_score', 55)}\n"
        f"🎓 Seniority: {', '.join(profile.get('seniority_levels') or ['entry','junior','internship'])}",
        parse_mode="Markdown"
    )

async def cmd_threshold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    supabase = get_supabase()
    try:
        new_threshold = int(context.args[0])
        assert 0 <= new_threshold <= 100
    except (IndexError, ValueError, AssertionError):
        await update.message.reply_text("Usage: /threshold 75 (must be 0-100)")
        return
    user_resp = supabase.table("users").select("id").eq("telegram_chat_id", chat_id).execute()
    if not user_resp.data:
        await update.message.reply_text("Not linked. Send /start")
        return
    supabase.table("users").update({"notification_threshold": new_threshold}).eq("id", user_resp.data[0]["id"]).execute()
    await update.message.reply_text(f"✅ Threshold updated to {new_threshold}/100")

async def cmd_health(update: Update, context: ContextTypes.DEFAULT_TYPE):
    supabase = get_supabase()
    sources = supabase.table("job_sources").select("name, health_status, last_job_count, is_active").eq("is_active", True).execute()
    if not sources.data:
        await update.message.reply_text("No active sources configured.")
        return
    status_emoji = {"healthy": "🟢", "degraded": "🟡", "dead": "🔴", "low_quality": "⚠️"}
    lines = ["📡 *Source Health*\n"]
    for s in sources.data:
        emoji = status_emoji.get(s["health_status"], "❓")
        lines.append(f"{emoji} {s['name']} — {s['last_job_count'] or 0} jobs last run")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_unlink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    supabase = get_supabase()
    supabase.table("users").update({"telegram_chat_id": None}).eq("telegram_chat_id", chat_id).execute()
    await update.message.reply_text("✅ Telegram unlinked from your JobPulse account.")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    supabase = get_supabase()
    
    if data.startswith("save:"):
        match_id = data.split(":", 1)[1]
        supabase.table("job_matches").update({"status": "saved"}).eq("id", match_id).execute()
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("⭐ Saved!")
    elif data.startswith("reject:"):
        match_id = data.split(":", 1)[1]
        supabase.table("job_matches").update({"status": "rejected"}).eq("id", match_id).execute()
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("✖️ Dismissed.")

async def _update_frequency(update: Update, frequency: str):
    chat_id = update.effective_chat.id
    supabase = get_supabase()
    user_resp = supabase.table("users").select("id").eq("telegram_chat_id", chat_id).execute()
    if not user_resp.data:
        await update.message.reply_text("Not linked. Send /start")
        return
    supabase.table("users").update({"notification_frequency": frequency}).eq("id", user_resp.data[0]["id"]).execute()
    msg = "🔕 Notifications paused." if frequency == "paused" else "🔔 Notifications resumed!"
    await update.message.reply_text(msg)

def run_bot(token: str):
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("jobs", cmd_jobs))
    app.add_handler(CommandHandler("pause", cmd_pause))
    app.add_handler(CommandHandler("resume", cmd_resume_notifs))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("threshold", cmd_threshold))
    app.add_handler(CommandHandler("health", cmd_health))
    app.add_handler(CommandHandler("unlink", cmd_unlink))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    loop.run_until_complete(app.run_polling(drop_pending_updates=True))
```

-----

## STEP 9 — BACKEND ROUTES

Create `backend/routes/jobs.py`:

```python
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from supabase import create_client
import os

router = APIRouter()

def get_supabase():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

class StatusUpdate(BaseModel):
    status: str  # new, seen, saved, applied, rejected

@router.get("/")
def get_jobs(
    user_id: str = Query(...),
    status: str = Query(None),
    min_score: int = Query(0),
    max_score: int = Query(100),
    source_id: str = Query(None),
    seniority: str = Query(None),
    limit: int = Query(50),
    offset: int = Query(0),
):
    supabase = get_supabase()
    query = (
        supabase.table("job_matches")
        .select("*, jobs(*, job_sources(name, health_status))")
        .eq("user_id", user_id)
        .gte("match_score", min_score)
        .lte("match_score", max_score)
        .order("match_score", desc=True)
        .limit(limit)
        .offset(offset)
    )
    if status:
        query = query.eq("status", status)
    resp = query.execute()
    return {"jobs": resp.data, "count": len(resp.data)}

@router.patch("/{match_id}/status")
def update_job_status(match_id: str, update: StatusUpdate, user_id: str = Query(...)):
    supabase = get_supabase()
    resp = supabase.table("job_matches").update({"status": update.status}).eq("id", match_id).eq("user_id", user_id).execute()
    if not resp.data:
        raise HTTPException(404, "Match not found")
    return resp.data[0]
```

Create `backend/routes/profile.py`:

```python
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
import fitz  # PyMuPDF
import os, json, re
from supabase import create_client
from groq import Groq

router = APIRouter()

def get_supabase():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

@router.post("/resume")
async def upload_resume(user_id: str = Query(...), file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(400, "Only PDF files accepted")
    
    content = await file.read()
    
    # Extract text via PyMuPDF
    doc = fitz.open(stream=content, filetype="pdf")
    raw_text = ""
    for page in doc:
        raw_text += page.get_text()
    doc.close()
    
    if len(raw_text) < 100:
        raise HTTPException(400, "Could not extract text from PDF")
    
    # Upload to Supabase Storage
    supabase = get_supabase()
    storage_path = f"resumes/{user_id}/{file.filename}"
    supabase.storage.from_("resumes").upload(storage_path, content, {"content-type": "application/pdf"})
    
    # Parse with Groq
    groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
    parse_prompt = f"""Extract structured information from this resume. Return ONLY valid JSON:
{{
  "skills": ["list of technical skills, tools, languages, frameworks"],
  "experience_years": number (0 if fresh graduate),
  "inferred_roles": ["2-4 job titles this person could apply for"],
  "education": "highest degree and field"
}}

Resume:
{raw_text[:4000]}"""
    
    try:
        resp = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": parse_prompt}],
            temperature=0.1, max_tokens=500,
        )
        text = resp.choices[0].message.content.strip()
        text = re.sub(r'^```json\s*', '', text); text = re.sub(r'\s*```$', '', text)
        parsed = json.loads(text)
    except Exception:
        parsed = {"skills": [], "experience_years": 0, "inferred_roles": [], "education": ""}
    
    # Save to DB
    resume_record = {
        "user_id": user_id,
        "raw_text": raw_text,
        "parsed_skills": parsed.get("skills", []),
        "parsed_experience_years": parsed.get("experience_years", 0),
        "storage_path": storage_path,
    }
    supabase.table("resumes").insert(resume_record).execute()
    
    # Update user profile skills
    supabase.table("user_profiles").update({
        "skills": parsed.get("skills", []),
        "target_roles": parsed.get("inferred_roles", []),
    }).eq("user_id", user_id).execute()
    
    return {"success": True, "parsed": parsed}

class ProfileUpdate(BaseModel):
    natural_language_description: Optional[str] = None
    target_roles: Optional[List[str]] = None
    skills: Optional[List[str]] = None
    seniority_levels: Optional[List[str]] = None
    min_display_score: Optional[int] = None
    show_senior: Optional[bool] = None
    notification_threshold: Optional[int] = None

@router.get("/")
def get_profile(user_id: str = Query(...)):
    supabase = get_supabase()
    user = supabase.table("users").select("*, user_profiles(*)").eq("id", user_id).execute()
    return user.data[0] if user.data else {}

@router.patch("/")
def update_profile(user_id: str = Query(...), update: ProfileUpdate = None):
    supabase = get_supabase()
    profile_data = {k: v for k, v in update.dict().items() if v is not None and k not in ("notification_threshold",)}
    user_data = {k: v for k, v in update.dict().items() if k == "notification_threshold" and v is not None}
    if profile_data:
        supabase.table("user_profiles").update(profile_data).eq("user_id", user_id).execute()
    if user_data:
        supabase.table("users").update(user_data).eq("id", user_id).execute()
    return {"success": True}
```

Create `backend/routes/telegram_routes.py`:

```python
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from supabase import create_client
from datetime import datetime
import os

router = APIRouter()

def get_supabase():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

class LinkCode(BaseModel):
    code: str

@router.post("/verify")
def verify_link_code(user_id: str = Query(...), body: LinkCode = None):
    supabase = get_supabase()
    now = datetime.utcnow().isoformat()
    
    resp = supabase.table("telegram_link_codes").select("*").eq("code", body.code).eq("used", False).gte("expires_at", now).execute()
    
    if not resp.data:
        raise HTTPException(400, "Invalid or expired code")
    
    link_record = resp.data[0]
    chat_id = link_record["telegram_chat_id"]
    
    # Link the user
    supabase.table("users").update({"telegram_chat_id": chat_id}).eq("id", user_id).execute()
    supabase.table("telegram_link_codes").update({"used": True}).eq("id", link_record["id"]).execute()
    
    return {"success": True, "telegram_chat_id": chat_id}
```

Create `backend/routes/sources.py`:

```python
from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import Optional
from supabase import create_client
import os

router = APIRouter()

def get_supabase():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

@router.get("/library")
def get_source_library(category: str = Query(None)):
    supabase = get_supabase()
    query = supabase.table("job_sources").select("*").eq("is_library", True)
    if category:
        query = query.eq("category", category)
    resp = query.order("name").execute()
    return resp.data

@router.get("/")
def get_user_sources(user_id: str = Query(...)):
    supabase = get_supabase()
    # Return library sources + user's custom sources
    lib = supabase.table("job_sources").select("*").eq("is_library", True).execute()
    custom = supabase.table("job_sources").select("*").eq("user_id", user_id).eq("is_library", False).execute()
    return {"library": lib.data, "custom": custom.data}

class ToggleSource(BaseModel):
    is_active: bool

@router.patch("/{source_id}/toggle")
def toggle_source(source_id: str, body: ToggleSource, user_id: str = Query(...)):
    supabase = get_supabase()
    # For library sources, this creates a user preference override
    # For simplicity in MVP: just update the source directly
    supabase.table("job_sources").update({"is_active": body.is_active}).eq("id", source_id).execute()
    return {"success": True}
```

Create `backend/routes/imports.py`:

```python
from fastapi import APIRouter, Query
from pydantic import BaseModel
from supabase import create_client
from groq import Groq
import os, re, json, requests
from urllib.parse import urlparse

router = APIRouter()

def get_supabase():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

class BulkImport(BaseModel):
    raw_urls: str  # Newline-separated URLs

class GithubImport(BaseModel):
    repo_url: str  # e.g. https://github.com/lukasz-madon/awesome-remote-job

@router.post("/bulk")
def bulk_import(user_id: str = Query(...), body: BulkImport = None):
    supabase = get_supabase()
    lines = [l.strip() for l in body.raw_urls.split("\n") if l.strip()]
    
    results = {"valid": [], "duplicates": [], "errors": [], "no_jobs": []}
    
    # Get existing URLs to check duplicates
    existing = supabase.table("job_sources").select("url").execute()
    existing_urls = {r["url"] for r in existing.data}
    
    for url in lines[:200]:  # Cap at 200 per import
        if not url.startswith("http"):
            results["errors"].append({"url": url, "reason": "Invalid URL format"})
            continue
        if url in existing_urls:
            results["duplicates"].append(url)
            continue
        
        # Detect source type
        source_type = "jina"
        if "rss" in url or "feed" in url or "atom" in url:
            source_type = "rss"
        
        # Quick validation: try to fetch
        try:
            if source_type == "rss":
                import feedparser
                feed = feedparser.parse(url)
                job_count = len(feed.entries)
            else:
                resp = requests.get(f"https://r.jina.ai/{url}", timeout=30)
                job_count = 1 if len(resp.text) > 500 else 0
            
            if job_count == 0:
                results["no_jobs"].append(url)
            else:
                domain = urlparse(url).netloc.replace("www.", "")
                name = domain.split(".")[0].title()
                results["valid"].append({"url": url, "name": name, "source_type": source_type})
                existing_urls.add(url)
        except Exception as e:
            results["errors"].append({"url": url, "reason": str(e)[:100]})
    
    # Log the import
    supabase.table("source_imports").insert({
        "user_id": user_id,
        "import_type": "bulk_paste",
        "raw_input": body.raw_urls[:5000],
        "urls_found": len(lines),
        "urls_valid": len(results["valid"]),
    }).execute()
    
    return results

class ActivateSources(BaseModel):
    sources: list  # List of {url, name, source_type}

@router.post("/activate")
def activate_sources(user_id: str = Query(...), body: ActivateSources = None):
    supabase = get_supabase()
    inserted = []
    for s in body.sources:
        try:
            resp = supabase.table("job_sources").insert({
                "name": s["name"],
                "url": s["url"],
                "source_type": s.get("source_type", "jina"),
                "user_id": user_id,
                "is_library": False,
                "is_active": True,
                "health_status": "healthy",
            }).execute()
            inserted.append(resp.data[0])
        except Exception:
            pass  # Duplicate or error
    return {"activated": len(inserted), "sources": inserted}

@router.post("/github")
def import_from_github(user_id: str = Query(...), body: GithubImport = None):
    # Extract owner/repo from URL
    match = re.search(r"github\.com/([^/]+)/([^/]+)", body.repo_url)
    if not match:
        return {"error": "Invalid GitHub repo URL"}
    
    owner, repo = match.group(1), match.group(2).rstrip(".git")
    
    # Fetch README via GitHub API
    headers = {}
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
    
    readme_resp = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}/readme",
        headers={**headers, "Accept": "application/vnd.github.raw"},
        timeout=30
    )
    
    if readme_resp.status_code != 200:
        return {"error": f"Could not fetch README: {readme_resp.status_code}"}
    
    readme_content = readme_resp.text[:12000]  # Truncate for Groq
    
    # Use Groq to extract job board URLs
    groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
    prompt = f"""Extract all job board and job listing website URLs from this GitHub README.
Return ONLY valid JSON array of objects, no other text:
[{{"name": "Site Name", "url": "https://...", "category": "General|Tech|Aggregator|AI|Data|Backend|Startup"}}]

Only include actual job board websites (not GitHub repos, not documentation, not company homepages).
Return [] if none found.

README content:
{readme_content}"""
    
    try:
        resp = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1, max_tokens=2000,
        )
        text = resp.choices[0].message.content.strip()
        text = re.sub(r'^```json\s*', '', text); text = re.sub(r'\s*```$', '', text)
        boards = json.loads(text)
    except Exception as e:
        return {"error": f"AI extraction failed: {str(e)}"}
    
    # Get existing URLs
    supabase = get_supabase()
    existing = supabase.table("job_sources").select("url").execute()
    existing_urls = {r["url"] for r in existing.data}
    
    # Mark which are new vs already in library
    for board in boards:
        board["is_duplicate"] = board.get("url", "") in existing_urls
    
    # Log
    supabase.table("source_imports").insert({
        "user_id": user_id,
        "import_type": "github_repo",
        "raw_input": body.repo_url,
        "urls_found": len(boards),
        "urls_valid": sum(1 for b in boards if not b.get("is_duplicate")),
    }).execute()
    
    return {"boards": boards, "total_found": len(boards), "repo": f"{owner}/{repo}"}
```

-----

## STEP 10 — FLY.IO DEPLOYMENT (BACKEND)

⚠️ **MANUAL ACTION 4: Set Up Fly.io**

```
1. Go to https://fly.io → sign up (free)
2. Install flyctl: curl -L https://fly.io/install.sh | sh
3. Run: fly auth login
4. From the backend/ directory, run: fly launch
   - App name: jobpulse-backend
   - Region: Choose nearest to you (or ams/fra for EU proximity)
   - Don't create a PostgreSQL database (we use Supabase)
   - Don't deploy yet
5. Set secrets: fly secrets set SUPABASE_URL="..." SUPABASE_SERVICE_ROLE_KEY="..." GROQ_API_KEY="..." GEMINI_API_KEY="..." TELEGRAM_BOT_TOKEN="..."
6. Then deploy: fly deploy
```

Create `backend/fly.toml`:

```toml
app = "jobpulse-backend"
primary_region = "ams"

[build]

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = false
  auto_start_machines = true
  min_machines_running = 1

[[vm]]
  memory = "256mb"
  cpu_kind = "shared"
  cpus = 1
```

Create `backend/Dockerfile`:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

-----

## STEP 11 — REACT FRONTEND

⚠️ **MANUAL ACTION 5: Set Up Vercel**

```
1. Go to https://vercel.com → sign up with GitHub (free)
2. Import the jobpulse GitHub repo
3. Set root directory to "frontend"
4. Add environment variables:
   VITE_SUPABASE_URL=your_supabase_url
   VITE_SUPABASE_ANON_KEY=your_supabase_anon_key
   VITE_API_URL=https://jobpulse-backend.fly.dev
5. Deploy
```

Scaffold the frontend with:

```bash
cd frontend
npm create vite@latest . -- --template react
npm install
npm install @supabase/supabase-js @supabase/auth-helpers-react
npm install @radix-ui/react-* lucide-react tailwindcss autoprefixer postcss
npm install recharts clsx tailwind-merge
```

Create `frontend/src/lib/supabase.js`:

```javascript
import { createClient } from '@supabase/supabase-js'

export const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY
)
```

Create `frontend/src/App.jsx` — top-level routing:
Build a single-page app with a persistent left sidebar nav and these routes:

- `/` → `Dashboard.jsx` (main job feed)
- `/sources` → `Sources.jsx` (source library + bulk import + GitHub parser)
- `/profile` → `Profile.jsx` (resume upload + preferences + Telegram link)
- `/analytics` → `Analytics.jsx` (stats, charts)

**Dashboard.jsx** must include:

- Fetch job_matches joined with jobs and job_sources for the logged-in user
- Score colour coding: ≥90 → green, 75-89 → yellow-green, 60-74 → amber, <60 → grey
- Status tabs: New | Saved | Applied | All
- Filters: score range slider, source dropdown, seniority checkboxes, role type checkboxes
- “Show senior roles” toggle (default off)
- Each job card shows: title, company, source badge (with health dot), match score badge, remote type, seniority badge (🎓/🟢/🔵), currency signal emoji, posted time
- Click card → expand to show full description + match reasons list + disqualifiers + Apply button
- Job actions: [Save ⭐] [Mark Applied ✅] [Not Interested ✖️] — each calls PATCH /api/jobs/{id}/status
- Supabase realtime subscription on job_matches for live updates

**Sources.jsx** must include:

- Two tabs: “Job Boards Library” | “Custom Sources”
- Library tab: grid of source cards (all 30 seeded sources) with name, category badge, type badge (API/RSS/Jina), health badge, toggle switch to activate/deactivate
- “Bulk Import” section: large textarea + “Validate & Import” button → shows results table (valid/duplicate/error) → user checks boxes → “Activate Selected” button
- “Import from GitHub Repo” section: URL input + “Extract Job Boards” button → shows found boards → user selects → “Activate Selected” button

**Profile.jsx** must include:

- Resume upload zone (drag + drop or click) → POST /api/profile/resume → shows parsed skills + inferred roles for review
- Editable skills tags (add/remove individual skills)
- Natural language description textarea: “Describe what you’re looking for in plain English”
- Seniority checkboxes: Internship, Entry-level, Junior, Mid (default: first 3 checked)
- Score threshold slider: “Show jobs above: 55/100”
- Notification threshold slider: “Alert me on Telegram for jobs above: 70/100”
- Telegram linking section: shows current link status, “Link Telegram” button → shows 6-digit code input flow

**Analytics.jsx** must include:

- Cards: Total jobs seen, Jobs saved, Applications sent, Response rate (applications/applied count)
- Bar chart (recharts): Jobs by source (top 10 sources by match volume)
- Line chart: Jobs per day over last 30 days
- Match score distribution: histogram (recharts) showing distribution of all match scores

-----

## STEP 12 — FINAL WIRING & ENV FILES

Create `frontend/.env.local` (for local dev — do not commit):

```
VITE_SUPABASE_URL=your_supabase_url
VITE_SUPABASE_ANON_KEY=your_supabase_anon_key
VITE_API_URL=http://localhost:8000
```

Create `backend/.env` (for local dev — do not commit):

```
SUPABASE_URL=your_supabase_url
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
GROQ_API_KEY=your_groq_key
GEMINI_API_KEY=your_gemini_key
TELEGRAM_BOT_TOKEN=your_bot_token
```

Create `.gitignore` at repo root:

```
.env
.env.local
__pycache__/
*.pyc
node_modules/
dist/
.venv/
```

-----

## FINAL CHECKLIST

Before running the scheduler for the first time, verify:

- [ ] Supabase schema deployed (run `001_initial_schema.sql` in SQL Editor)
- [ ] `increment_source_errors` function created in Supabase
- [ ] Supabase “resumes” storage bucket created (private)
- [ ] Groq API key obtained from console.groq.com
- [ ] Gemini API key obtained from aistudio.google.com
- [ ] Telegram bot created via @BotFather, token stored
- [ ] GitHub repo created, all secrets added to Actions
- [ ] Fly.io account created, backend deployed
- [ ] Vercel connected to repo, frontend env vars set
- [ ] Manual trigger GitHub Actions workflow → verify it runs without errors → check Supabase job_matches table for results

-----

## KNOWN LIMITATIONS (FREE STACK)

- **Jina AI** may return empty/partial content for heavily JS-rendered pages (Wellfound, etc.). These sources will show as “Degraded” after a few failed runs — expected behaviour.
- **Gemini Flash** free tier allows 1,500 jobs scored per day. If more jobs pass Stages 1 & 2, Stage 3 will queue for the next run. Not an issue at MVP scale.
- **GitHub Actions** on a private repo has 2,000 free minutes/month. At ~10 min per run × 12 runs/day = ~3,600 min/month. **Make the repo public to get unlimited free minutes**, or reduce scheduler frequency to every 4 hours (6 runs/day = 1,800 min/month, within free limit).
- **Fly.io** free tier is 256MB RAM. If the bot or API uses more, the process will restart. Keep the backend lean.