"""
scheduler/fetchers/api_fetcher.py

Fetches jobs from sources that expose a JSON API.
Dedicated fetchers for each known source; generic fallback for unknown ones.
"""

import logging
import time
from typing import List, Dict, Any, Optional

import requests

logger = logging.getLogger("jobpulse.scheduler")


def _normalize_job(raw: dict, source_id: str) -> dict:
    """Normalize a raw API job dict to the jobs table schema."""
    return {
        "source_id": source_id,
        "external_id": str(raw.get("id") or raw.get("url") or ""),
        "title": (raw.get("title") or "").strip(),
        "company": (
            raw.get("company_name")
            or raw.get("company")
            or raw.get("organization")
            or ""
        ),
        "description": raw.get("description") or raw.get("description_short") or "",
        "apply_url": raw.get("url") or raw.get("apply_url") or raw.get("job_url") or "",
        "salary_range": raw.get("salary") or raw.get("salary_range") or "",
        "tags": raw.get("tags") or raw.get("skills") or raw.get("labels") or [],
        "posted_at": (
            raw.get("publication_date")
            or raw.get("created_at")
            or raw.get("date")
            or None
        ),
    }


def fetch_remotive(source_id: str) -> List[dict]:
    resp = requests.get("https://remotive.com/api/remote-jobs", timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return [_normalize_job(j, source_id) for j in data.get("jobs", [])]


def fetch_himalayas(source_id: str) -> List[dict]:
    all_jobs: List[dict] = []
    page = 1
    while True:
        resp = requests.get(
            f"https://himalayas.app/jobs/api?limit=100&offset={(page - 1) * 100}",
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        jobs = data.get("jobs", [])
        if not jobs:
            break
        for j in jobs:
            all_jobs.append(
                {
                    "source_id": source_id,
                    "external_id": str(j.get("slug") or j.get("id") or ""),
                    "title": (j.get("title") or "").strip(),
                    "company": (
                        j.get("company", {}).get("name") or j.get("companyName") or ""
                    ),
                    "description": j.get("description") or "",
                    "apply_url": j.get("applicationLink") or j.get("url") or "",
                    "salary_range": j.get("salary") or "",
                    "tags": j.get("skills") or [],
                    "posted_at": j.get("createdAt") or None,
                }
            )
        page += 1
        if page > 10:  # Safety cap — ~1000 jobs max per run
            break
        time.sleep(1)
    return all_jobs


def fetch_jobicy(source_id: str) -> List[dict]:
    resp = requests.get(
        "https://jobicy.com/api/v2/remote-jobs?count=50&industry=all", timeout=30
    )
    resp.raise_for_status()
    data = resp.json()
    return [_normalize_job(j, source_id) for j in data.get("jobs", [])]


def fetch_arbeitnow(source_id: str) -> List[dict]:
    resp = requests.get(
        "https://www.arbeitnow.com/api/job-board-api", timeout=30
    )
    resp.raise_for_status()
    data = resp.json()
    return [_normalize_job(j, source_id) for j in data.get("data", [])]


def fetch_remoteok(source_id: str) -> List[dict]:
    """RemoteOK returns a JSON array; first item is metadata — skip it."""
    resp = requests.get(
        "https://remoteok.com/api",
        timeout=30,
        headers={"User-Agent": "JobPulse/1.0 (personal job aggregator)"},
    )
    resp.raise_for_status()
    data = resp.json()
    jobs = [j for j in data if isinstance(j, dict) and j.get("id")]
    result = []
    for j in jobs:
        result.append(
            {
                "source_id": source_id,
                "external_id": str(j.get("id") or ""),
                "title": (j.get("position") or "").strip(),
                "company": j.get("company") or "",
                "description": j.get("description") or "",
                "apply_url": j.get("apply_url") or j.get("url") or "",
                "salary_range": j.get("salary") or "",
                "tags": j.get("tags") or [],
                "posted_at": j.get("date") or None,
            }
        )
    return result


def fetch_workingnomads(source_id: str) -> List[dict]:
    resp = requests.get(
        "https://www.workingnomads.com/api/exposed_jobs/", timeout=30
    )
    resp.raise_for_status()
    data = resp.json()
    return [_normalize_job(j, source_id) for j in data]


# Domain → fetcher function mapping
_API_FETCHERS = {
    "remotive.com": fetch_remotive,
    "himalayas.app": fetch_himalayas,
    "jobicy.com": fetch_jobicy,
    "arbeitnow.com": fetch_arbeitnow,
    "remoteok.com": fetch_remoteok,
    "workingnomads.com": fetch_workingnomads,
}


def fetch_from_api(source: dict) -> List[dict]:
    """Route to the correct fetcher based on URL domain.
    Falls back to a generic JSON GET for unknown API sources.
    """
    url: str = source["url"]
    source_id: str = source["id"]

    for domain, fetcher in _API_FETCHERS.items():
        if domain in url:
            return fetcher(source_id)

    # Generic fallback — attempt JSON GET
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list):
        return [_normalize_job(j, source_id) for j in data]
    for key in ("jobs", "data", "results", "listings"):
        if key in data:
            return [_normalize_job(j, source_id) for j in data[key]]
    return []
