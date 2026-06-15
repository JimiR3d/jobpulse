# JobPulse — Project History

## Session Log

### Session 2026-06-15 — Environment Setup
**Tasks completed:**
- Read full build prompt (2,011 lines) and PRD
- Created GEMINI.md (project AI context document)
- Created project_history.md (this file)

**Key decisions:**
- Free-tier only architecture confirmed (Groq + Gemini Flash + Supabase + Fly.io + Vercel + GitHub Actions)
- 3-stage AI pipeline confirmed: Stage 1/2 = Groq LLaMA 3.3 70B, Stage 3 = Gemini Flash
- GitHub Actions cron every 2 hours — make repo public for unlimited free minutes
- Fly.io free tier (256MB RAM) — keep backend lean

**Files changed:**
- `GEMINI.md` — Created (project context)
- `project_history.md` — Created (this file)

**Nothing built yet — documentation and context setup only.**

**Open items for next session:**
- [x] Run `supabase/migrations/001_initial_schema.sql` in Supabase SQL Editor (manual step)
- [x] Build backend FastAPI app (`backend/` folder)
- [x] Build scheduler pipeline (`scheduler/` folder)
- [x] Build frontend React app (`frontend/` folder)
- [x] Set up GitHub Actions cron workflow
- [x] Deploy backend to Fly.io -> Changed to Render
- [x] Deploy frontend to Vercel
- [x] Configure Telegram bot via @BotFather

### Session 2026-06-15 — Debugging & Refactoring
**Tasks completed:**
- Refactored backend JWT auth verification to use `supabase.auth.get_user()` (RS256 compat).
- Refactored frontend and backend to fix vanishing `user_profiles` data (bypassed PostgREST join bugs via explicit queries).
- Fixed CORS Preflight issues by adding `Cache-Control` to `allow_headers`.
- Implemented Groq-powered Auto-Write AI profile description feature on the frontend.
- Added strict `4.1s` rate limit buffer to the scheduler to prevent Gemini 15 RPM free-tier crashes.
- Moved scheduler Telegram alerts to dispatch mid-run (per-source) instead of end-of-run to protect against 25-minute workflow timeouts.

**Key decisions:**
- Acknowledged that scaling up to 30+ sources requires a batch-processing architecture for the Gemini AI pipeline, otherwise the strict 15 RPM limit will cause the workflow to exceed the 25-minute GitHub Actions maximum limit.

**Open items for next session:**
- [ ] Refactor AI Pipeline to use Batched Prompt Architecture (sending 10-15 jobs in a single prompt) to bypass free-tier rate limit bottlenecks.
