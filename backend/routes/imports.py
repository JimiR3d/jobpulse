"""
backend/routes/imports.py

Bulk URL paste and GitHub README parser for adding new job sources.
Rate limited: 10/hour (each import triggers Jina/Groq calls).
"""

import json
import logging
import os
import re
from typing import List
from urllib.parse import urlparse

import feedparser
import requests
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from groq import Groq
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from supabase import create_client

from auth import get_current_user_id

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)
logger = logging.getLogger("jobpulse.backend")

_JINA_BASE = "https://r.jina.ai/"
_HEADERS = {"User-Agent": "JobPulse/1.0"}


def get_supabase():
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )


# ── Bulk URL paste ───────────────────────────────────────────────

class BulkImport(BaseModel):
    raw_urls: str = Field(..., max_length=50_000)  # ~200 URLs


@router.post("/bulk")
@limiter.limit("10/hour")
def bulk_import(
    request: Request,
    body: BulkImport,
    user_id: str = Depends(get_current_user_id),
):
    """
    Validate up to 200 URLs from a newline-separated paste.
    For each URL: detect type (RSS/Jina), quick-fetch to confirm jobs exist.
    Returns categorized results for user to review before activating.
    """
    supabase = get_supabase()
    lines = [l.strip() for l in body.raw_urls.split("\n") if l.strip()]

    results = {"valid": [], "duplicates": [], "errors": [], "no_jobs": []}

    # Get existing URLs for dedup check
    existing_resp = supabase.table("job_sources").select("url").execute()
    existing_urls = {r["url"] for r in existing_resp.data}

    for url in lines[:200]:  # Hard cap at 200 per import
        if not url.startswith("http"):
            results["errors"].append({"url": url, "reason": "Invalid URL format (must start with http)"})
            continue

        if url in existing_urls:
            results["duplicates"].append(url)
            continue

        # Detect source type from URL patterns
        source_type = "jina"
        if any(kw in url.lower() for kw in ("rss", "feed", "atom", ".xml")):
            source_type = "rss"

        # Quick validation: try to fetch and count jobs
        try:
            if source_type == "rss":
                feed = feedparser.parse(url)
                job_count = len(feed.entries)
            else:
                resp = requests.get(f"{_JINA_BASE}{url}", timeout=30, headers=_HEADERS)
                job_count = 1 if len(resp.text) > 500 else 0

            if job_count == 0:
                results["no_jobs"].append(url)
            else:
                parsed = urlparse(url)
                domain = parsed.netloc.replace("www.", "")
                name = domain.split(".")[0].title()
                results["valid"].append(
                    {"url": url, "name": name, "source_type": source_type}
                )
                existing_urls.add(url)  # Prevent within-batch duplicates

        except Exception as e:
            results["errors"].append({"url": url, "reason": str(e)[:100]})

    # Log the import
    try:
        supabase.table("source_imports").insert(
            {
                "user_id": user_id,
                "import_type": "bulk_paste",
                "raw_input": body.raw_urls[:5000],
                "urls_found": len(lines),
                "urls_valid": len(results["valid"]),
            }
        ).execute()
    except Exception:
        pass  # Log failure is non-fatal

    return results


# ── Activate selected sources ────────────────────────────────────

class ActivateSourceItem(BaseModel):
    url: str
    name: str
    source_type: str = "jina"
    category: str = "General"


class ActivateSources(BaseModel):
    sources: List[ActivateSourceItem]


@router.post("/activate")
def activate_sources(
    body: ActivateSources,
    user_id: str = Depends(get_current_user_id),
):
    """Write validated sources to the database and activate them."""
    supabase = get_supabase()
    inserted = []
    errors = []

    for s in body.sources[:50]:  # Cap at 50 activations per call
        try:
            resp = supabase.table("job_sources").insert(
                {
                    "name": s.name,
                    "url": s.url,
                    "source_type": s.source_type,
                    "category": s.category,
                    "user_id": user_id,
                    "is_library": False,
                    "is_active": True,
                    "health_status": "healthy",
                }
            ).execute()
            if resp.data:
                inserted.append(resp.data[0])
        except Exception as e:
            errors.append({"url": s.url, "error": str(e)[:100]})

    return {"activated": len(inserted), "errors": errors, "sources": inserted}


# ── GitHub README parser ─────────────────────────────────────────

class GithubImport(BaseModel):
    repo_url: str = Field(..., max_length=200)


@router.post("/github")
@limiter.limit("10/hour")
def import_from_github(
    request: Request,
    body: GithubImport,
    user_id: str = Depends(get_current_user_id),
):
    """
    Parse a GitHub repo README for job board URLs using Groq LLaMA.
    Returns a list of found boards (with duplicate flags) for user to activate.
    """
    match = re.search(r"github\.com/([^/]+)/([^/]+)", body.repo_url)
    if not match:
        raise HTTPException(status_code=400, detail="Invalid GitHub repo URL")

    owner = match.group(1)
    repo = match.group(2).rstrip(".git")

    # Fetch README via GitHub API
    headers: dict = {}
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    readme_resp = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}/readme",
        headers={**headers, "Accept": "application/vnd.github.raw"},
        timeout=30,
    )

    if readme_resp.status_code == 404:
        raise HTTPException(status_code=404, detail=f"Repo {owner}/{repo} not found or has no README")
    if readme_resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"GitHub API error: {readme_resp.status_code}",
        )

    readme_content = readme_resp.text[:12000]  # Truncate for Groq context

    # Extract job boards with Groq
    groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
    prompt = f"""Extract all job board and job listing website URLs from this GitHub README.
Return ONLY a valid JSON array of objects, no other text, no markdown fences:
[{{"name": "Site Name", "url": "https://...", "category": "General|Tech|Aggregator|AI|Data|Backend|Startup|Worldwide"}}]

Only include actual job board websites. Exclude: GitHub repos, documentation sites, company homepages, tool/library links.
Return [] if none found.

README content:
{readme_content}"""

    try:
        resp = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=2000,
        )
        text = resp.choices[0].message.content.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        boards = json.loads(text)
        if not isinstance(boards, list):
            boards = []
    except Exception as e:
        logger.error(json.dumps({"event": "github_import_groq_error", "error": str(e)}))
        raise HTTPException(status_code=502, detail="AI extraction failed — try again")

    # Mark duplicates
    supabase = get_supabase()
    existing_resp = supabase.table("job_sources").select("url").execute()
    existing_urls = {r["url"] for r in existing_resp.data}

    for board in boards:
        board["is_duplicate"] = board.get("url", "") in existing_urls
        board["source_type"] = "jina"  # All scraped boards default to jina

    # Log
    try:
        supabase.table("source_imports").insert(
            {
                "user_id": user_id,
                "import_type": "github_repo",
                "raw_input": body.repo_url,
                "urls_found": len(boards),
                "urls_valid": sum(1 for b in boards if not b.get("is_duplicate")),
            }
        ).execute()
    except Exception:
        pass

    return {
        "boards": boards,
        "total_found": len(boards),
        "new_count": sum(1 for b in boards if not b.get("is_duplicate")),
        "repo": f"{owner}/{repo}",
    }
