"""
scheduler/fetchers/rss_fetcher.py

Parses RSS/Atom feeds using feedparser.
Handles the common "Role at Company" title pattern from WWR, Remote.co etc.
"""

import logging
from typing import List

import time
import feedparser

logger = logging.getLogger("jobpulse.scheduler")


def fetch_rss(source: dict) -> List[dict]:
    """Parse an RSS/Atom feed and return normalized job dicts."""
    feed = feedparser.parse(source["url"])
    jobs = []

    for entry in feed.entries:
        title: str = entry.get("title", "").strip()
        # Skip non-job entries (category headers, nav items)
        if len(title) < 5:
            continue

        company = ""
        # Extract company from "Role at Company" pattern (WWR style)
        if " at " in title:
            parts = title.rsplit(" at ", 1)
            title = parts[0].strip()
            company = parts[1].strip()

        posted_at = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                posted_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", entry.published_parsed)
            except Exception:
                pass

        jobs.append(
            {
                "source_id": source["id"],
                "external_id": entry.get("link") or entry.get("id") or "",
                "title": title,
                "company": company,
                "description": entry.get("summary") or entry.get("description") or "",
                "apply_url": entry.get("link") or "",
                "salary_range": "",
                "tags": [],
                "posted_at": posted_at,
            }
        )

    return jobs
