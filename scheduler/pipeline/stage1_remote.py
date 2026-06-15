"""
scheduler/pipeline/stage1_remote.py

Stage 1 of the AI pipeline: Remote location verification via Groq LLaMA 3.3 70B.

Classifies each job's remote_type:
  worldwide       → genuinely open to workers anywhere on earth
  us_only         → requires US residency / work authorization
  eu_only         → requires EU residency / work authorization
  country_specific → restricted to one named country
  hybrid_only     → requires regular in-person office attendance
  unknown         → insufficient info to classify

Discard logic: us_only | eu_only | country_specific | hybrid_only with HIGH confidence.
Keep: worldwide + unknown (unknown shown with ⚠️ badge in frontend).
"""

import json
import logging
import re
from typing import Literal

from groq import Groq

from pipeline.llm_safety import prepare_job_for_llm
from pipeline.models import RemoteCheckResult, REMOTE_FALLBACK
from pipeline.resilience import groq_breaker

logger = logging.getLogger("jobpulse.scheduler")

_DISCARD_TYPES = {"us_only", "eu_only", "country_specific", "hybrid_only"}

_PROMPT_TEMPLATE = """Analyze this job listing. Can workers based ANYWHERE in the world apply? No visa or residency requirements?
Return ONLY valid JSON, no other text, no markdown fences:
{{"remote_type": "worldwide" | "us_only" | "eu_only" | "country_specific" | "hybrid_only" | "unknown", "confidence": "high" | "medium" | "low", "reason": "one sentence"}}

Definitions:
- worldwide: genuinely no country restriction, no right-to-work requirement
- us_only: requires US residency, citizenship, or US work authorization ("authorized to work in the US", "US only", US state mentions)
- eu_only: requires EU residency or European work authorization
- country_specific: restricted to a specific named country or small region
- hybrid_only: requires regular in-person attendance (not fully remote)
- unknown: genuinely insufficient information

Job Title: {title}
Location Field: {location}
Description: {description}"""


def _call_groq(job: dict, client: Groq) -> dict:
    safe = prepare_job_for_llm(job)
    prompt = _PROMPT_TEMPLATE.format(
        title=safe.get("title", ""),
        location=safe.get("location", ""),
        description=(safe.get("description") or "")[:1500],
    )
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=150,
    )
    text = resp.choices[0].message.content.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    raw = json.loads(text)
    validated = RemoteCheckResult(**raw)
    return validated.model_dump()


def check_remote(job: dict, client: Groq) -> dict:
    """
    Check if a job is open to worldwide applicants.
    Returns RemoteCheckResult dict. Uses circuit breaker + retry.
    """
    return groq_breaker.call_with_fallback(
        _call_groq,
        REMOTE_FALLBACK.model_dump(),
        job,
        client,
        max_retries=3,
    )


def should_discard(result: dict) -> bool:
    """
    Returns True if this job should be dropped from the pipeline.
    Only discards when confidence is HIGH — low/medium confidence jobs
    are kept and shown with an ⚠️ badge in the frontend.
    """
    return (
        result.get("remote_type") in _DISCARD_TYPES
        and result.get("confidence") == "high"
    )
