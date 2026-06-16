# JobPulse — Project GEMINI.md

## What This Is
AI-powered personal remote job aggregator. Monitors 60+ job boards every 2 hours via GitHub Actions,
runs a 3-stage AI pipeline (Groq → Groq → Groq), and delivers scored matches via Telegram and web dashboard.
Monthly cost: **$0** (all free tiers).

## Project Root
`c:\Users\Jimi\Downloads\The Anti-Gravity\New Gravity\jobpulse\`

## Architecture

```
GitHub Actions (cron every 2h)    → scheduler/main.py
  fetchers/     → fetch from API, RSS, Jina AI
  deduplicator  → MD5 hash dedup against DB
  pipeline/     → Stage 1 (Groq: remote check)
                → Stage 2 (Groq: seniority)
                → Stage 3 (Groq 70B: match score)
  notifier      → Telegram alerts with inline buttons

Render (always-on Starter OR free+UptimeRobot) → backend/main.py (FastAPI)
  routes/jobs.py         → GET /api/jobs/, PATCH status
  routes/profile.py      → POST resume, GET/PATCH profile
  routes/sources.py      → GET library, PATCH toggle
  routes/imports.py      → POST bulk, POST github
  routes/telegram_routes → POST verify, DELETE unlink
  telegram_handlers.py   → Bot: /start /jobs /pause /resume etc.

Telegram Bot (Option A: embedded in FastAPI | Option B: GitHub Actions)
  telegram_bot/run.py    → standalone runner for Option B

Vercel (static)                    → frontend/src/App.jsx (React 19 + Vite)
  pages/Dashboard.jsx     → job feed with real-time updates
  pages/Sources.jsx        → library, bulk import, GitHub parser
  pages/Profile.jsx        → resume upload, skills, Telegram link
  pages/Analytics.jsx      → stats, charts (recharts)

Supabase
  auth              → Supabase Auth (email/password)
  postgres          → 8 tables with RLS (job_matches now includes cover_letter)
  storage           → resumes bucket (private)
  realtime          → scoped per user_id
```

## Build Commands
```bash
# Frontend dev
cd frontend && npm run dev

# Frontend build
cd frontend && npm run build

# Backend dev
cd backend && uvicorn main:app --reload

# Scheduler local test (requires .env)
cd scheduler && python main.py
```

## Environment Variables

### Backend (.env)
```
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_JWT_SECRET=
GROQ_API_KEY=
GEMINI_API_KEY=
TELEGRAM_BOT_TOKEN=
FRONTEND_URL=http://localhost:5173   # or Vercel URL in prod
ENV=development
```

### Frontend (.env.local)
```
VITE_SUPABASE_URL=
VITE_SUPABASE_ANON_KEY=
VITE_API_URL=http://localhost:8000
```

### GitHub Secrets (for scheduler — job-fetch.yml)
```
SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, GROQ_API_KEY,
GEMINI_API_KEY, TELEGRAM_BOT_TOKEN
(GITHUB_TOKEN is auto-injected by Actions)
```

### GitHub Secrets (for bot — telegram-bot.yml, Option B only)
```
TELEGRAM_BOT_TOKEN, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
```

## Key Conventions

### Security (mandatory — from Security Patch doc)
- **JWT auth**: EVERY backend route uses `Depends(get_current_user_id)` from `backend/auth.py`
- **Never** accept `user_id` as a query param — always from JWT `.sub` claim
- **CORS**: locked to `FRONTEND_URL` env var in production (`ENV=production`)
- **Rate limiting**: slowapi — resume 5/hour, imports 10/hour, profile 30/minute
- **Request size**: 5MB max enforced in middleware
- **Global exception handler**: never exposes stack traces or internal errors to clients
- **Prompt safety**: ALL job data goes through `prepare_job_for_llm()` before any LLM call
- **Supabase Realtime**: scoped with `filter: user_id=eq.${user.id}` in frontend channel
- **GitHub Actions**: SHA-pinned action versions (see `.github/workflows/job-fetch.yml`)
- **Pydantic validation**: ALL LLM responses are validated through `pipeline/models.py`

### Architecture Rules
- Scheduler is **stateless** per run — circuit breakers reset on each GitHub Actions invocation
- Backend Telegram bot is optional — controlled by `START_TELEGRAM_BOT` env var (`true` = embedded in FastAPI, `false` = runs in GitHub Actions)
- Supabase `service_role` key ONLY in backend — `anon` key ONLY in frontend
- Frontend: `VITE_` prefix safe for `SUPABASE_URL` and `SUPABASE_ANON_KEY` only — never API keys

### AI Model Usage
- Stage 1, Stage 2, and Stage 3: **Groq LLaMA 3.1 8B** — fast JSON classification and contextual reasoning. (Migrated from Gemini Flash and Groq 70B due to strict rate limits and 6,000 TPM ceilings).
- Resume parsing + Jina extraction + GitHub README: **Groq LLaMA 3.3 70B**
- Cover Letter Generation: **Gemini Pro Latest** — deep reasoning applied to align resume skills with job descriptions for tailored applications.
- **Batched Processing**: The pipeline processes jobs in batches of 15 per API call. This speeds up the scheduler significantly and prevents GitHub Actions 25-minute timeouts during traffic spikes while respecting the Gemini 15 RPM limit.

### Database Conventions
- All tables have RLS enabled — no exceptions
- `user_id` FK always references `public.users(id)` → `auth.users(id)`
- Backend uses **service_role** key to bypass RLS (batch operations)
- Frontend queries use **anon** key + Auth JWT (respects RLS)

## Deployment

### Step 0 — Supabase (required by both options)
1. Create project at [supabase.com](https://supabase.com)
2. SQL Editor → paste and run `supabase/migrations/001_initial_schema.sql`
3. Verify: 8 tables created, 30 sources seeded in `job_sources`
4. Storage → New Bucket → name: `resumes`, **private** (no public access)
5. Collect: `Project URL`, `anon key`, `service_role key`, `JWT Secret` (Settings → API)

### Step 0b — GitHub Actions Scheduler (required by both options)
1. Push repo to GitHub (**public** = unlimited free Actions minutes)
2. Settings → Secrets → Actions → add:
   `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`
3. Actions → "Job Fetch Scheduler" → Run workflow manually first → check logs + `scheduler_logs` table
*(Note: To stay within the Groq 100,000 TPD free tier while using 70B models, the scheduler cron runs twice a day instead of every 2 hours).*

### Step 0c — Vercel Frontend (required by both options)
1. [vercel.com](https://vercel.com) → New Project → Import GitHub repo
2. Root Directory: `frontend`
3. Add env vars:
   - `VITE_SUPABASE_URL` = your Supabase project URL
   - `VITE_SUPABASE_ANON_KEY` = your Supabase anon key
   - `VITE_API_URL` = your backend URL (set after backend deploys)
4. Deploy → copy the Vercel URL for use in backend `FRONTEND_URL`

---

Two backend options are set up. Choose one:

---

### Option A — Render Starter Plan ($50 credit → ~7 months free)

**Architecture**: FastAPI + Telegram bot run together (always-on, no sleep)  
**Files**: `render.yaml`

```bash
# 1. Push repo to GitHub (public or private)
# 2. Render Dashboard → New → Blueprint → select repo
#    Render auto-reads render.yaml
# 3. After deploy, set secret env vars in Render Dashboard → Environment:
#    SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_JWT_SECRET
#    GROQ_API_KEY, GEMINI_API_KEY, TELEGRAM_BOT_TOKEN
#    FRONTEND_URL (your Vercel URL)
# 4. Verify: hit https://jobpulse-backend.onrender.com/health → {"status": "ok"}
```

**Env var to set on Render:**
```
START_TELEGRAM_BOT = true
ENV = production
```

---

### Option B — Render Free Tier + GitHub Actions Bot ($0 forever)

**Architecture**: FastAPI on Render free (sleeps, UptimeRobot keeps it awake), Telegram bot runs as a GitHub Actions job that restarts every 6 hours.  
**Files**: `render-free.yaml`, `.github/workflows/telegram-bot.yml`, `telegram_bot/run.py`

**Step 1 — Deploy FastAPI to Render (free tier):**
```bash
# Render Dashboard → New → Blueprint → select repo
# When prompted, point to render-free.yaml instead of render.yaml
# Set env vars (same as Option A, but WITHOUT TELEGRAM_BOT_TOKEN)
# Set START_TELEGRAM_BOT = false
```

**Step 2 — GitHub Actions bot secrets:**  
Settings → Secrets → Actions → New secret:
```
TELEGRAM_BOT_TOKEN   = your bot token
SUPABASE_URL         = your supabase URL
SUPABASE_SERVICE_ROLE_KEY = your service role key
```

**Step 3 — Enable the telegram-bot workflow:**  
GitHub → Actions → "Telegram Bot (Option B)" → Enable workflow  
Then trigger manually first to test: Run workflow → watch logs

**Step 4 — UptimeRobot keep-alive (prevents Render sleep):**
1. Sign up free at uptimerobot.com
2. New monitor → HTTP(S)
3. URL: `https://jobpulse-backend.onrender.com/health`
4. Interval: 5 minutes
5. This pings every 5 min — Render sleeps after 15min inactivity, so this prevents all sleep

**Bot restart gap:**  
The bot polls for ~5h 50min, then exits cleanly. GitHub restarts it at the next 6-hour cron mark (00:00, 06:00, 12:00, 18:00 UTC). During the ~10 min gap, Telegram queues all updates — the bot processes them on reconnect. No commands are lost.

---

### When to switch from B → A

When your $0 budget constraints relax OR if the 10-min bot gap bothers you:
1. Change `render-free.yaml` → `render.yaml` in Blueprint settings
2. Set `START_TELEGRAM_BOT = true` in Render env vars
3. Remove TELEGRAM_BOT_TOKEN from GitHub Actions secrets


## Known Issues / Gotchas
- **recharts**: Pinned to v2.13.3 (Vite 8/Rolldown requires `react-is` — installed separately)
- **autoprefixer**: Removed from PostCSS config — `caniuse-lite/dist/unpacker/agents` missing in v1.0.30001799. Vite handles vendor prefixes natively.
- **Render free tier + Telegram bot**: `START_TELEGRAM_BOT` MUST be `false` on free tier. If both run together and the service sleeps, the bot thread is killed on sleep but won't restart cleanly on wake.
- **Option B bot gap**: ~10 min gap between 6-hour GitHub Actions restarts. Telegram queues messages during the gap — no commands lost, just delayed.
- **UptimeRobot required for Option B**: Without it, Render free tier sleeps after 15min and cold starts take 30–60s, making the API feel broken.
- **Groq rate limits**: Free tier is generous but Stage 1 + Stage 2 call per job means ~2 calls/job. The 4.1s sleep handles this automatically.
- **Gemini Free Tier rate limits**: 15 requests per minute. `scheduler/main.py` enforces a strictly timed 4.1s `time.sleep()` per job to guarantee it never exceeds this.
- **GitHub Actions timeout**: Free tier runs are killed after 25 minutes. If >300 jobs are fetched at once, the 4.1s sleep will cause the workflow to timeout. Telegram alerts are dispatched *per source* to ensure alerts aren't lost if this happens.
- **Jina AI**: Rate-limited at ~10 req/min — 6s sleep after each Jina call is enforced in `jina_fetcher.py`
- **Render Blueprint**: Render reads `render.yaml` from repo root by default. To use `render-free.yaml`, you must specify it in the Blueprint settings during setup.
- **Library source toggles**: Toggling a library source affects ALL users globally (MVP single-user only). For multi-user: needs `user_source_overrides` junction table. See TODO in `sources.py`.
- **FastAPI `on_event` deprecation**: `@app.on_event("startup")` still works in FastAPI 0.115.5 but logs deprecation warnings. Will be replaced with lifespan handler in a future cleanup pass.
- **Jina circuit breaker**: `jina_breaker` is defined in `resilience.py` but not yet wired into `jina_fetcher.py`. Jina failures timeout naturally (45s) but don't trip the breaker.
- **Browser Caching on Frontend**: Fetch requests can be aggressively cached by the browser, causing stale data (especially empty arrays for `user_profiles`). `Cache-Control` headers are mandatory in `api.js`.
- **CORS Preflight**: Adding `Cache-Control` triggers `OPTIONS` preflight. `backend/main.py` must explicitly include it in `allow_headers`.
- **Supabase RS256 JWTs**: Supabase migrated to RS256 signing keys. Backend must use `supabase.auth.get_user(token)` instead of `PyJWT` local validation to handle this securely.
- **PostgREST 1-to-1 Joins**: PostgREST joins on 1-to-1 relationships can unexpectedly return empty arrays. Backend routes explicitly run sequential queries instead of relying on magic `.select('*, user_profiles(*)')` joins.

### Automated Application Phase (2026-06-15)
- Added `cover_letter` and `application_qa` columns to `job_matches` via migration `003_applications_phase.sql`.
- Created `applications.py` in the FastAPI backend to generate highly tailored markdown cover letters using `gemini-1.5-pro-latest` (Gemini Pro).
- Built frontend UI in `JobCard.jsx` to request, render, and copy AI-generated cover letters on demand.
- Updated `backend/requirements.txt` to include `google-generativeai`.

### Audit Fixes Applied (2026-06-15)
- Added `feedparser==6.0.11` to `backend/requirements.txt` (was missing — `imports.py` imports it)
- Added ownership check (chat_id → user_id) to Telegram callback handler for save/reject buttons
- Fixed `"now()"` string literal → `datetime.now(timezone.utc).isoformat()` in scheduler `update_source_health`
- Added `vercel.json` to `frontend/` with SPA rewrite rule (prevents 404 on page refresh)
- Fixed `user_profiles` list/dict normalization in scheduler `main.py` (Supabase joins return list)
- Refactored backend JWT auth verification to use Supabase's native RS256-compatible `get_user()`
- Refactored `get_profile` to use explicit sequential queries rather than PostgREST joins
- Added Auto-write AI description generator utilizing Groq LLaMA 3
- Added strict 4.1s circuit breaker delays to scheduler to respect 15 RPM Gemini limits
- Updated frontend CORS and cache-busting logic to fix vanishing profile data
- Moved scheduler Telegram alerts to dispatch mid-run (per-source) to protect against 25-minute workflow timeouts
- Refactored scheduler pipeline to use a **Batched Prompt Architecture**, processing jobs in batches of 15. This reduces Gemini requests by a factor of 15 and completely eliminates GitHub Action timeouts on massive fetches.
- Updated pipeline models to `RemoteCheckBatchResult`, `SeniorityBatchResult`, and `MatchScoreBatchResult` with `job_index` tracking to prevent crashing if the LLM drops a job.
- Added strict Pydantic model validators to deeply lowercase LLM outputs, preventing case-sensitive literal validation errors from breaking the pipeline and stalling scores at 50.
- Reduced Groq batch size to 7 and added a 60-second sleep handler for `groq.RateLimitError` to prevent the 6,000 TPM limit from causing the Jina fetcher to report 0 jobs and degrade source health.

### Opus Deep Audit (2026-06-15)
- **[C1]** Made `_lowercase_strings()` recursive in `pipeline/models.py` — now handles nested dicts, lists, and strings at any depth
- **[C2]** Fixed `pass_rate` in `scheduler/main.py` to divide by `len(new_jobs)` instead of `len(raw_jobs)` — prevents healthy sources from degrading as duplicates accumulate
- **[C3]** Created `backend/db.py` singleton Supabase client — all routes and auth now share one client instead of creating new ones per request
- **[C4]** Added logging when `save_match()` returns None (duplicate constraint) in `scheduler/main.py`
- **[C5]** Replaced unreliable PostgREST `.not_.in_()` on nested `jobs.seniority` with application-level filter in `routes/jobs.py`
- **[M1]** Wired `jina_breaker` circuit breaker into `jina_fetcher.py` — Jina HTTP calls now trip the breaker after persistent failures
- **[M2]** Fixed `deduplicator.py` logging to use `json.dumps()` instead of raw dict
- **[M3]** Made `notifier.py` `send_alerts()` accept an optional pre-created `Bot` instance to reuse
- **[M4]** Fixed `profile.py` `generate_description` error logging to use structured JSON
- **[L1]** Removed `PyJWT` from `backend/requirements.txt` (unused after auth refactor)
- **[L2]** Removed `tenacity` from both `requirements.txt` files (unused — circuit breaker has its own retry)
- **[L3]** Removed `PyMuPDF` from `scheduler/requirements.txt` (only used by backend)
- **[L4]** Stabilized Realtime subscription in `Dashboard.jsx` — subscribe once on mount instead of churning on filter changes
- **[L5]** Created `supabase/migrations/002_audit_fixes.sql` to tighten `telegram_link_codes` RLS from `using (true)` to `using (false)`
- **[P1]** Fixed `gemini-1.5-flash` API 404 error by migrating to `gemini-1.5-flash-latest` in `stage3_score.py`
- **[P2]** Fixed Groq 100k TPD token limit crashes by switching `stage1_remote.py` and `stage2_seniority.py` from 70B to `llama-3.1-8b-instant` and trimming description prompt lengths from 1000 to 600 characters.

### Pipeline Debugging & Hardening (2026-06-16)
- **[H1]** Fixed Jina fetcher Groq `429` rate limit crashes by downgrading the extraction model in `jina_fetcher.py` from 70B to `llama-3.1-8b-instant`.
- **[H2]** Replaced the deprecated `gemini-1.5-flash` model with `gemini-3.5-flash` in `stage3_score.py` as the 1.5 series was entirely removed from the Google API, which had been causing 404s.
- **[H3]** Added `"part-time"` to Pydantic literal validators in `pipeline/models.py` since the downgraded 8B model successfully extracts this role, which previously threw a `literal_error` and caused batches to drop.
- **[H4]** Hardened `rss_fetcher.py` to use `feedparser.published_parsed` to correctly format dates into ISO 8601 strings. This prevents Supabase `400 Bad Request` database insertion errors caused by non-standard RSS date strings.

## File Index (key files only)
```
jobpulse/
├── .gitignore
├── render.yaml                       ← Option A: Render Starter (always-on, bot embedded)
├── render-free.yaml                  ← Option B: Render free tier (bot in GitHub Actions)
├── .github/
│   ├── dependabot.yml
│   └── workflows/
│       ├── job-fetch.yml             ← SHA-pinned job scheduler (every 2h)
│       └── telegram-bot.yml         ← Option B: bot runner (every 6h)
├── supabase/migrations/
│   ├── 001_initial_schema.sql        ← Run in Supabase SQL Editor
│   └── 002_audit_fixes.sql           ← Opus audit: tightens telegram_link_codes RLS
├── scheduler/
│   ├── main.py                       ← Entry point
│   ├── deduplicator.py
│   ├── notifier.py
│   ├── requirements.txt
│   ├── fetchers/
│   │   ├── api_fetcher.py
│   │   ├── rss_fetcher.py
│   │   └── jina_fetcher.py
│   └── pipeline/
│       ├── llm_safety.py             ← Security Patch #6
│       ├── resilience.py             ← Security Patch #7
│       ├── models.py                 ← Security Patch #9
│       ├── stage1_remote.py
│       ├── stage2_seniority.py
│       └── stage3_score.py
├── telegram_bot/                     ← Option B standalone bot
│   ├── run.py                        ← Entry point (imports from backend/)
│   └── requirements.txt
├── backend/
│   ├── main.py                       ← FastAPI app (START_TELEGRAM_BOT controls bot)
│   ├── auth.py                       ← JWT middleware (Security Patch #1)
│   ├── db.py                         ← Singleton Supabase client (Opus audit C3)
│   ├── telegram_handlers.py          ← Bot handlers (used by both options)
│   ├── Dockerfile
│   ├── fly.toml                      ← Legacy Fly.io config (kept for reference)
│   ├── requirements.txt
│   ├── .env.example
│   └── routes/
│       ├── jobs.py
│       ├── profile.py
│       ├── sources.py
│       ├── imports.py
│       └── telegram_routes.py
└── frontend/
    ├── index.html
    ├── vercel.json                   ← SPA rewrites (all routes → index.html)
    ├── tailwind.config.js
    ├── postcss.config.js
    ├── .env.example
    └── src/
        ├── main.jsx
        ├── App.jsx                   ← Auth gate + sidebar + router
        ├── index.css                 ← Design system
        ├── lib/
        │   ├── supabase.js
        │   └── api.js                ← API client (auto-injects JWT)
        ├── components/
        │   ├── JobCard.jsx
        │   ├── ScoreBadge.jsx
        │   ├── HealthBadge.jsx
        │   └── SourceCard.jsx
        └── pages/
            ├── Dashboard.jsx
            ├── Sources.jsx
            ├── Profile.jsx
            └── Analytics.jsx
```
