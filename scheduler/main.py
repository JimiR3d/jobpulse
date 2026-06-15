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
from pipeline.stage1_remote import check_remote_batch, should_discard
from pipeline.stage2_seniority import check_seniority_batch
from pipeline.stage3_score import score_job_batch

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
    
    def chunk_list(lst, size):
        for i in range(0, len(lst), size):
            yield lst[i:i + size]

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
        BATCH_SIZE = 7

        for batch in chunk_list(new_jobs, BATCH_SIZE):
            # ── Stage 1: Remote check ────────────────────────────
            stage1_results = check_remote_batch(batch, groq_client)
            
            valid_jobs = []
            for job, stage1 in zip(batch, stage1_results):
                if should_discard(stage1):
                    continue
                valid_jobs.append((job, stage1))

            if not valid_jobs:
                time.sleep(2.1)
                continue

            # ── Stage 2: Seniority check ─────────────────────────
            jobs_to_check_seniority = [job for job, _ in valid_jobs]
            stage2_results = check_seniority_batch(jobs_to_check_seniority, groq_client)

            passed_batch_jobs = []
            for (job, stage1), stage2 in zip(valid_jobs, stage2_results):
                # Enrich job with classification data
                job["remote_type"] = stage1["remote_type"]
                job["seniority"] = stage2["seniority"]
                job["role_type"] = stage2["role_type"]
                job["is_trainee"] = stage2.get("is_trainee_program", False)

                # ── Save job to DB ────────────────────────────────────
                job_id = save_job(job)
                if job_id:
                    passed_count += 1
                    passed_batch_jobs.append((job_id, job, stage1, stage2))

            if passed_batch_jobs:
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

                    jobs_for_user = []
                    job_ids_for_user = []
                    stage_data_for_user = []

                    for job_id, job, stage1, stage2 in passed_batch_jobs:
                        # Skip seniors if user hasn't enabled them
                        if (
                            stage2["seniority"] in ("senior", "lead")
                            and not profile.get("show_senior")
                        ):
                            continue
                        jobs_for_user.append(job)
                        job_ids_for_user.append(job_id)
                        stage_data_for_user.append((stage1, stage2))
                    
                    if jobs_for_user:
                        score_results = score_job_batch(jobs_for_user, profile)
                        
                        for i, score_result in enumerate(score_results):
                            job = jobs_for_user[i]
                            job_id = job_ids_for_user[i]
                            stage1, stage2 = stage_data_for_user[i]
                            
                            currency = score_result.get("currency_signal", "unknown")
                            match = save_match(job_id, user["id"], stage1, stage2, score_result)
                            if match is None:
                                log("save_match_duplicate", job_id=job_id, user_id=user["id"])


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
                        
                        # Gemini: 15 RPM limit = 1 request every 4 seconds.
                        time.sleep(4.1)

            # Free tier API rate limit buffer for Groq:
            time.sleep(2.1)


        # Send Telegram alerts for this source immediately so we don't lose them if GitHub Actions times out
        if pending_alerts:
            log("telegram_alerts_sending_batch", count=len(pending_alerts), source=source["name"])
            try:
                send_alerts(pending_alerts, BOT_TOKEN)
            except Exception as e:
                log("telegram_alerts_error", error=str(e))
            pending_alerts.clear()

        # Update source health after processing
        pass_rate = passed_count / max(len(new_jobs), 1)
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
