"""
scheduler/main.py

JobPulse Scheduler — entry point for GitHub Actions cron job.
Runs every 2 hours. Orchestrates the full job fetch → AI pipeline → alert cycle.

Structured JSON logging throughout (Security Patch #10 — no print() calls).
"""

import json as json_module
import logging
import os
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from groq import Groq
from supabase import create_client, Client

from deduplicator import deduplicate, make_hash
from fetchers.api_fetcher import fetch_from_api
from fetchers.jina_fetcher import fetch_jina_source
from fetchers.rss_fetcher import fetch_rss
from notifier import send_alerts
from pipeline.stage1_remote import check_remote, should_discard
from pipeline.stage2_seniority import check_seniority
from pipeline.stage3_score import score_job

# ── Logging setup ────────────────────────────────────────────────
load_dotenv()

logging.basicConfig(format="%(message)s", level=logging.INFO)
logger = logging.getLogger("jobpulse.scheduler")


def log(event: str, **kwargs) -> None:
    """Emit a structured JSON log line to stdout (captured by GitHub Actions)."""
    logger.info(json_module.dumps({"event": event, **kwargs}))


# ── Supabase + Groq clients ──────────────────────────────────────
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])


# ── DB helpers ───────────────────────────────────────────────────

def get_active_sources() -> list:
    resp = (
        supabase.table("job_sources")
        .select("*")
        .eq("is_active", True)
        .neq("health_status", "dead")
        .execute()
    )
    return resp.data


def get_all_users_with_profiles() -> list:
    resp = supabase.table("users").select("*, user_profiles(*)").execute()
    return resp.data


def save_job(job: dict) -> str | None:
    """Insert a job into the DB. Returns the new job ID or None if duplicate."""
    try:
        resp = supabase.table("jobs").insert(job).execute()
        return resp.data[0]["id"] if resp.data else None
    except Exception:
        return None  # Unique constraint on dedup_hash — expected for duplicates


def save_match(
    job_id: str,
    user_id: str,
    stage1: dict,
    stage2: dict,
    score_result: dict,
) -> dict | None:
    match = {
        "job_id": job_id,
        "user_id": user_id,
        "match_score": score_result["score"],
        "match_reasons": score_result.get("match_reasons") or [],
        "disqualifiers": score_result.get("disqualifiers") or [],
        "remote_verified": stage1["remote_type"] == "worldwide",
        "seniority_verified": stage2["seniority"] in (
            "internship", "entry", "junior", "unknown"
        ),
        "status": "new",
        "telegram_notified": False,
    }
    try:
        resp = supabase.table("job_matches").insert(match).execute()
        return resp.data[0] if resp.data else None
    except Exception:
        return None


def update_source_health(
    source_id: str,
    job_count: int,
    error: str | None,
    pass_rate: float,
) -> None:
    if error:
        try:
            supabase.rpc(
                "increment_source_errors", {"source_id_input": source_id}
            ).execute()
        except Exception as e:
            log("source_health_rpc_error", source_id=source_id, error=str(e))
        return

    # Determine health status from pass rate
    if job_count == 0:
        health = "degraded"
    elif pass_rate < 0.05 and job_count > 10:
        health = "low_quality"
    else:
        health = "healthy"

    supabase.table("job_sources").update(
        {
            "last_fetched": datetime.now(timezone.utc).isoformat(),
            "last_job_count": job_count,
            "jobs_passing_filter_rate": pass_rate,
            "consecutive_errors": 0,
            "health_status": health,
        }
    ).eq("id", source_id).execute()


# ── Main pipeline ────────────────────────────────────────────────

def run() -> None:
    log("scheduler_start")

    sources = get_active_sources()
    users = get_all_users_with_profiles()

    log("scheduler_context", source_count=len(sources), user_count=len(users))

    if not users:
        log("scheduler_no_users")
        return

    pending_alerts: list = []

    for source in sources:
        log("source_fetch_start", source=source["name"], type=source["source_type"])

        raw_jobs: list = []
        error: str | None = None

        try:
            if source["source_type"] == "api":
                raw_jobs = fetch_from_api(source)
            elif source["source_type"] == "rss":
                raw_jobs = fetch_rss(source)
            elif source["source_type"] == "jina":
                raw_jobs = fetch_jina_source(source, groq_client)
        except Exception as e:
            error = str(e)
            log("source_fetch_error", source=source["name"], error=error)

        new_jobs = deduplicate(raw_jobs, supabase)
        log(
            "source_fetch_complete",
            source=source["name"],
            raw_count=len(raw_jobs),
            new_count=len(new_jobs),
        )

        passed_count = 0

        for job in new_jobs:
            # ── Stage 1: Remote check ────────────────────────────
            stage1 = check_remote(job, groq_client)
            if should_discard(stage1):
                continue

            # ── Stage 2: Seniority check ─────────────────────────
            stage2 = check_seniority(job, groq_client)

            # Enrich job with classification data
            job["remote_type"] = stage1["remote_type"]
            job["seniority"] = stage2["seniority"]
            job["role_type"] = stage2["role_type"]
            job["is_trainee"] = stage2.get("is_trainee_program", False)

            # ── Save job to DB ────────────────────────────────────
            job_id = save_job(job)
            if not job_id:
                continue  # Already exists or insert error

            passed_count += 1

            # ── Stage 3: Score against each user ─────────────────
            for user in users:
                profiles = user.get("user_profiles")
                # Supabase joins may return a list or a dict — normalize
                if isinstance(profiles, list):
                    profile = profiles[0] if profiles else None
                else:
                    profile = profiles
                if not profile:
                    continue

                # Skip seniors if user hasn't enabled them
                if (
                    stage2["seniority"] in ("senior", "lead")
                    and not profile.get("show_senior")
                ):
                    continue

                score_result = score_job(job, profile)
                currency = score_result.get("currency_signal", "unknown")

                match = save_match(job_id, user["id"], stage1, stage2, score_result)

                # Queue Telegram alert if score meets threshold
                threshold = user.get("notification_threshold", 70)
                freq = user.get("notification_frequency", "realtime")
                if (
                    match
                    and score_result["score"] >= threshold
                    and user.get("telegram_chat_id")
                    and freq == "realtime"
                ):
                    job["source_name"] = source["name"]
                    pending_alerts.append(
                        (
                            user["telegram_chat_id"],
                            job,
                            {**match, "currency_signal": currency},
                        )
                    )

            # Free tier API rate limit buffer:
            # Gemini: 15 RPM limit = 1 request every 4 seconds.
            # Groq: 30 RPM limit = 2 requests per job * 15 jobs/min = 30 req/min.
            # 4.1 seconds perfectly respects BOTH free tier limits.
            time.sleep(4.1)

        # Send Telegram alerts for this source immediately so we don't lose them if GitHub Actions times out
        if pending_alerts:
            log("telegram_alerts_sending_batch", count=len(pending_alerts), source=source["name"])
            try:
                send_alerts(pending_alerts, BOT_TOKEN)
            except Exception as e:
                log("telegram_alerts_error", error=str(e))
            pending_alerts.clear()

        # Update source health after processing
        pass_rate = passed_count / max(len(raw_jobs), 1)
        update_source_health(source["id"], len(raw_jobs), error, pass_rate)

        # Log the run to scheduler_logs
        try:
            supabase.table("scheduler_logs").insert(
                {
                    "source_id": source["id"],
                    "jobs_fetched": len(raw_jobs),
                    "jobs_new": len(new_jobs),
                    "jobs_passed": passed_count,
                    "error_message": error,
                }
            ).execute()
        except Exception as e:
            log("scheduler_log_error", source=source["name"], error=str(e))

        log(
            "source_pipeline_complete",
            source=source["name"],
            passed=passed_count,
            alerts_queued=len(pending_alerts),
        )

    # ── Send all queued Telegram alerts ──────────────────────────
    log("telegram_alerts_sending", count=len(pending_alerts))
    if pending_alerts:
        try:
            send_alerts(pending_alerts, BOT_TOKEN)
        except Exception as e:
            log("telegram_alerts_error", error=str(e))

    log("scheduler_complete", total_alerts_sent=len(pending_alerts))


if __name__ == "__main__":
    run()
