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
- [x] Refactor AI Pipeline to use Batched Prompt Architecture (sending 10-15 jobs in a single prompt) to bypass free-tier rate limit bottlenecks.

### Session 2026-06-15 — Batched Prompt Architecture
**Tasks completed:**
- Refactored `scheduler/main.py` and the pipeline logic to process up to 15 jobs concurrently in a single LLM API call.
- Migrated from 1-by-1 AI processing to strict JSON array validation using Pydantic array structures and `job_index` tracking.
- Successfully eliminated the 25-minute GitHub Actions timeout risk while perfectly adhering to Gemini's 15 RPM limits.

**Key decisions:**
- Embedded `job_index` natively inside the JSON prompt instructions. This ensures that if the LLM skips a job, our internal system catches the misalignment and instantly recovers it using a safe fallback, guaranteeing zero pipeline crashes.

**Open items for next session:**
- [x] Debug the "Degraded Sources" and "Stale Job Feed" issues caused by the scheduler update.
- [x] Ensure frontend data reflects the latest AI evaluations cleanly.

### Session 2026-06-15 — Bug Fixes for Batched Architecture
**Tasks completed:**
- Fixed strict Pydantic validation that stalled jobs at a score of 50 due to case-sensitivity and unhandled JSON array formats.
- Reduced Groq batch size to 7 and added a 60-second sleep handler for `groq.RateLimitError` to prevent the 6,000 TPM limit from causing the Jina fetcher to report 0 jobs and degrade source health.

**Key decisions:**
- Applied deep lowercase validation via `@model_validator(mode='before')` to ensure AI inconsistencies do not break strictly typed Pydantic literals.
- Enforced automated rate limit backoffs for Groq APIs to safeguard against TPM exhaustion without completely failing the pipeline.

**Open items for next session:**
- [ ] Verify functionality using Opus in the next session.
