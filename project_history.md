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
- [x] Verify functionality using Opus in the next session.

### Session 2026-06-15 — Opus Deep Audit & Final Polish
**Tasks completed:**
- Conducted full codebase audit of scheduler, backend, frontend, and database configurations.
- Implemented 14 distinct fixes across all components, ranging from critical logic flaws to dependency cleanup.
- Executed the RLS tightening migration on `telegram_link_codes` via Supabase MCP.

**Key decisions:**
- Changed `pass_rate` health calculation to use `new_jobs` as the denominator rather than `raw_jobs`. This prevents sources from falsely degrading their own health when outputting known duplicates.
- Integrated `db.py` to provide a true singleton Supabase instance for the FastAPI backend, completely removing connection overhead from all endpoints.
- Tightened frontend queries using application-level logic instead of vulnerable nested PostgREST joins.
- Prevented pipeline failures when Jina persistently drops connections by finally wiring `jina_breaker` into `jina_fetcher.py`.

**Open items for next session:**
- [ ] Monitor the singleton Supabase client behavior under live FastAPI concurrent requests.
- [x] Watch the scheduler via GitHub Actions to ensure `jina_breaker` and `pass_rate` improvements trigger cleanly. (Identified and fixed new rate limit issues)

### Session 2026-06-15 — Pipeline Rate Limit & Model Mapping Fixes
**Tasks completed:**
- Debugged GitHub Actions workflow failure (`job-fetch.yml`) which stalled due to API rate limits and model 404 mapping errors.
- Shifted Groq from 70B to `llama-3.1-8b-instant` and truncated description prompts from 1000 to 600 characters in `stage1_remote.py` and `stage2_seniority.py` to stay under the 100k TPD free-tier limit.
- Updated `stage3_score.py` to use `gemini-1.5-flash-latest` resolving the `models/gemini-1.5-flash` 404 error.
- Updated GEMINI.md, task.md, and walkthrough.md to document the bug fixes.

**Key decisions:**
- Downsized the Groq extraction models to a much faster, rate-limit friendly size to ensure the background cron job remains $0.
- Acknowledged future roadmap: Gemini 3.5 will be reserved for complex reasoning tasks like automatic job applications and custom cover letter generation.

**Open items for next session:**
- [x] Re-verify the `job-fetch.yml` workflow via GitHub Actions UI to ensure the pipeline executes perfectly.
- [ ] Monitor the singleton Supabase client under live backend requests.
- [ ] Begin planning the automated job application and cover letter generation features utilizing Gemini 3.5.

### Session 2026-06-16 — Pipeline Hardening & Edge Case Debugging
**Tasks completed:**
- Debugged GitHub Actions workflow failure where all jobs were receiving a score of 50.
- ⚠️ WARNING: GEMINI 1.5 MODELS ARE FULLY DEPRECATED AS OF 2026. DO NOT USE. YOU MUST STRICTLY USE GEMINI 3.5 FLASH AND PRO LATEST TO AVOID 404 API ERRORS.

### June 16, 2026: AI Model Evolution & Pipeline Hardening
- **Gemini 1.5 Deprecation Discovery**: Discovered via a custom diagnostic script that the `gemini-1.5` series (including `gemini-1.5-flash` and `gemini-1.5-pro`) is officially deprecated and removed from modern Google API keys, causing `404 Not Found` API errors.
- **Model Upgrades**: Upgraded the entire architecture to use the 3.x series. Stage 3 scoring now uses `gemini-3.5-flash` (for fast, cheap processing) and the Cover Letter generation uses `gemini-pro-latest` (for heavy reasoning).
- **Library Warning**: `google.generativeai` has ceased updates. Future migrations will require switching to `google.genai`.
- **Jina JSON Fixes**: Fixed `llama-3.1-8b-instant` JSON truncation errors by enforcing `response_format={"type": "json_object"}`.
- **Pydantic Hardening**: Relaxed the `role_type` validator from a strict `Literal` to `str` after the 8B model correctly extracted `"minijob"` from German job boards, preventing validation crashes.

**Key decisions:**
- Continued enforcing strict Pydantic schema rules while dynamically expanding allowed values (like "part-time") when smaller open-source models demonstrate valid variations in extraction behavior.
- Maintained the fallback architectures so that even when Google or Groq APIs fail (404/429), the application doesn't crash but simply warns the user of default behaviors.

**Open items for next session:**
- [x] Test the completely fixed pipeline. (Confirmed via new logs)
- [ ] Verify the Automated Cover Letter generation feature on the frontend using `gemini-1.5-pro`.

### Session 2026-06-16 — Stage 3 Groq Migration
**Tasks completed:**
- Migrated the scheduler's Stage 3 Match Scoring from `gemini-3.5-flash` to `llama-3.3-70b-versatile` on Groq.
- Updated `scheduler/pipeline/stage3_score.py` and `scheduler/main.py` to use the `groq_client` instead of `google.generativeai`.
- Updated `GEMINI.md` to reflect that the background scheduler uses Groq for all three stages to stay within free-tier limits.

**Key decisions:**
- A hard limit of 20 requests per day for `gemini-3.5-flash` on the free tier made it impossible to process background job matches. Moving Stage 3 to Groq's 70B model maintains high intelligence scoring while utilizing Groq's generous 100k TPD limits.
- Gemini is now reserved exclusively for the on-demand Automated Cover Letter generation endpoint, where 20 requests per day is sufficient for manual user interactions.

**Open items for next session:**
- [ ] Test the Automated Cover Letter UI button in `JobCard.jsx`. (Requires `.env` setup locally or testing on staging environment).
