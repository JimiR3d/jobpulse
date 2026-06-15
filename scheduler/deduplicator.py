"""
scheduler/deduplicator.py

MD5-based deduplication against the jobs table.
Hash key: lower(title) + lower(company) — stable across sources.
Batch-checks in chunks of 100 to avoid URL length limits.
"""

import hashlib
import logging
from typing import List

from supabase import Client

logger = logging.getLogger("jobpulse.scheduler")

_CHUNK_SIZE = 100


def make_hash(title: str, company: str) -> str:
    """Generate a stable MD5 dedup hash from title + company."""
    key = f"{title.lower().strip()}{company.lower().strip()}"
    return hashlib.md5(key.encode()).hexdigest()


def deduplicate(jobs: List[dict], supabase: Client) -> List[dict]:
    """
    Return only jobs whose dedup_hash is not already in the database.
    Attaches dedup_hash to each returned job dict.
    """
    if not jobs:
        return []

    hashes = [make_hash(j.get("title", ""), j.get("company", "")) for j in jobs]

    # Batch-query the DB in chunks to avoid query length limits
    existing_hashes: set = set()
    for i in range(0, len(hashes), _CHUNK_SIZE):
        chunk = hashes[i : i + _CHUNK_SIZE]
        try:
            resp = (
                supabase.table("jobs")
                .select("dedup_hash")
                .in_("dedup_hash", chunk)
                .execute()
            )
            for row in resp.data:
                existing_hashes.add(row["dedup_hash"])
        except Exception as e:
            logger.error({"event": "dedup_query_error", "error": str(e)})

    new_jobs = []
    for job, h in zip(jobs, hashes):
        if h not in existing_hashes:
            job["dedup_hash"] = h
            new_jobs.append(job)

    return new_jobs
