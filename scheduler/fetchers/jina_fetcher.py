"""
scheduler/fetchers/jina_fetcher.py

Scrapes job boards via Jina AI Reader (r.jina.ai) — free, no API key.
Falls back to requests + BeautifulSoup for simpler HTML pages.
Uses Groq LLaMA to extract structured job listings from raw markdown.

Rate limit: Jina allows ~10 req/min — we sleep 6s between calls.
"""

import json
import logging
import re
import time
from typing import List

import requests
from bs4 import BeautifulSoup
import groq

from pipeline.resilience import jina_breaker

logger = logging.getLogger("jobpulse.scheduler")

JINA_BASE = "https://r.jina.ai/"
HEADERS = {"User-Agent": "JobPulse/1.0 (personal job aggregator)"}

_JINA_EXTRACTION_PROMPT = """Extract all job listings from this webpage content.
Return ONLY a valid JSON array, no other text, no markdown fences.
Each job object must have these exact fields:
  title: string (job title)
  company: string (company name, empty string if not found)
  apply_url: string (application URL, empty string if not found)
  description_snippet: string (max 300 chars of description)
  tags: array of strings (tech stack, skills)
  salary_range: string (empty string if not found)

Rules:
- Only include actual job listings — not ads, navigation, or headers
- If no jobs are found, return: []
- Do not include any text before or after the JSON array

Content:
{content}"""


def _fetch_via_jina(url: str) -> str:
    """Fetch a URL via Jina AI Reader and return clean markdown text."""
    resp = requests.get(
        f"{JINA_BASE}{url}",
        timeout=45,
        headers=HEADERS,
    )
    resp.raise_for_status()
    return resp.text


def _fetch_via_beautifulsoup(url: str) -> str:
    """Fallback scraper using requests + BeautifulSoup."""
    try:
        resp = requests.get(url, timeout=30, headers=HEADERS)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)
    except Exception as e:
        logger.warning(json.dumps({"event": "bs4_fetch_failed", "url": url, "error": str(e)}))
        return ""


def _fetch_content(source: dict) -> str:
    """Fetch page content via Jina (circuit-breaker-protected) with BS4 fallback."""
    raw_text = jina_breaker.call_with_fallback(
        _fetch_via_jina,
        "",  # fallback = empty string
        source["url"],
        max_retries=2,
    )

    if len(raw_text) < 200:
        logger.info(json.dumps({
            "event": "jina_fallback_to_bs4",
            "source": source["name"],
        }))
        raw_text = _fetch_via_beautifulsoup(source["url"])

    return raw_text


def fetch_jina_source(source: dict, groq_client) -> List[dict]:
    """
    Fetch a source via Jina AI, then use Groq to extract structured job listings.
    Falls back to BeautifulSoup if Jina returns too little content.
    """
    raw_text = _fetch_content(source)

    if len(raw_text) < 200:
        logger.warning(json.dumps({
            "event": "jina_empty_content",
            "source": source["name"],
        }))
        return []

    # Truncate to 8000 chars to stay within Groq's context limit
    truncated = raw_text[:8000]
    prompt = _JINA_EXTRACTION_PROMPT.format(content=truncated)

    max_retries = 2
    for attempt in range(1, max_retries + 1):
        try:
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=2000,
            )
            text = response.choices[0].message.content.strip()
            # Strip any accidental markdown fences
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            raw_jobs = json.loads(text)

            if not isinstance(raw_jobs, list):
                return []

            result = []
            for j in raw_jobs:
                if not j.get("title"):
                    continue
                result.append(
                    {
                        "source_id": source["id"],
                        "external_id": j.get("apply_url") or "",
                        "title": (j.get("title") or "").strip(),
                        "company": (j.get("company") or "").strip(),
                        "description": j.get("description_snippet") or "",
                        "apply_url": j.get("apply_url") or source["url"],
                        "salary_range": j.get("salary_range") or "",
                        "tags": j.get("tags") or [],
                        "posted_at": None,
                    }
                )

            # Jina rate limit: ~10 req/min → 6s spacing
            time.sleep(6)
            return result

        except groq.RateLimitError as e:
            logger.warning(json.dumps({
                "event": "jina_rate_limit_hit",
                "source": source["name"],
                "attempt": attempt,
                "sleep": 60,
            }))
            time.sleep(60)
            if attempt == max_retries:
                # If we still fail, raise the exception so main.py sets error to not-None!
                raise e

        except json.JSONDecodeError as e:
            logger.error(json.dumps({
                "event": "jina_json_parse_error",
                "source": source["name"],
                "error": str(e),
            }))
            return []
        except Exception as e:
            logger.error(json.dumps({
                "event": "jina_groq_error",
                "source": source["name"],
                "error": str(e),
            }))
            return []
    
    return []

