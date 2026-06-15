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
from pipeline.models import RemoteCheckBatchResult, REMOTE_FALLBACK
from pipeline.resilience import groq_breaker

logger = logging.getLogger("jobpulse.scheduler")

_DISCARD_TYPES = {"us_only", "eu_only", "country_specific", "hybrid_only"}

_PROMPT_TEMPLATE = """Analyze these job listings. Can workers based ANYWHERE in the world apply? No visa or residency requirements?
Return ONLY valid JSON, no other text, no markdown fences.
Your response MUST be a JSON object containing a "results" array.
Inside the array, return exactly one object per job with its matching job_index:
{{"results": [{{"job_index": 0, "remote_type": "worldwide" | "us_only" | "eu_only" | "country_specific" | "hybrid_only" | "unknown", "confidence": "high" | "medium" | "low", "reason": "one sentence"}}]}}

Definitions:
- worldwide: genuinely no country restriction, no right-to-work requirement
- us_only: requires US residency, citizenship, or US work authorization ("authorized to work in the US", "US only", US state mentions)
- eu_only: requires EU residency or European work authorization
- country_specific: restricted to a specific named country or small region
- hybrid_only: requires regular in-person attendance (not fully remote)
- unknown: genuinely insufficient information

Jobs to analyze:
{jobs_text}"""


def _call_groq_batch(jobs: list[dict], client: Groq) -> list[dict]:
    jobs_text_lines = []
    for idx, job in enumerate(jobs):
        safe = prepare_job_for_llm(job)
        jobs_text_lines.append(
            f"[{idx}] Title: {safe.get('title', '')}\n"
            f"Location Field: {safe.get('location', '')}\n"
            f"Description: {(safe.get('description') or '')[:600]}\n---"
        )

    prompt = _PROMPT_TEMPLATE.format(jobs_text="\n".join(jobs_text_lines))
    resp = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=3000,
        response_format={"type": "json_object"}
    )
    text = resp.choices[0].message.content.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    raw = json.loads(text)
    validated = RemoteCheckBatchResult(**raw)
    
    result_map = {r.job_index: r.model_dump() for r in validated.results}
    aligned = []
    for idx in range(len(jobs)):
        if idx in result_map:
            aligned.append(result_map[idx])
        else:
            f = REMOTE_FALLBACK.model_dump()
            f["job_index"] = idx
            aligned.append(f)
    return aligned


def check_remote_batch(jobs: list[dict], client: Groq) -> list[dict]:
    """
    Check if a batch of jobs are open to worldwide applicants.
    Returns a list of RemoteCheckResult dicts aligned with the input jobs. Uses circuit breaker + retry.
    """
    fallback = []
    for idx in range(len(jobs)):
        f = REMOTE_FALLBACK.model_dump()
        f["job_index"] = idx
        fallback.append(f)

    return groq_breaker.call_with_fallback(
        _call_groq_batch,
        fallback,
        jobs,
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

