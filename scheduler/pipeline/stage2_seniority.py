"""
scheduler/pipeline/stage2_seniority.py

Stage 2 of the AI pipeline: Seniority and role type classification via Groq LLaMA 3.3 70B.

Seniority levels:
  internship → explicitly internship or co-op
  entry      → 0-1 years, "entry-level", "new grad", "no experience required"
  junior     → 1-2 years, or "junior" in title
  mid        → 2-5 years (no explicit level = assume mid)
  senior     → 5+ years, or "senior" in title
  lead       → lead/principal/staff/director/VP/head
  unknown    → genuinely unclear

Role types: full-time | internship | contract | freelance | unknown

Jobs classified as senior/lead with high confidence are stored but hidden
from the main feed unless the user toggles "Show senior roles".
"""

import json
import logging
import re

from groq import Groq

from pipeline.llm_safety import prepare_job_for_llm
from pipeline.models import SeniorityBatchResult, SENIORITY_FALLBACK
from pipeline.resilience import groq_breaker

logger = logging.getLogger("jobpulse.scheduler")

_PROMPT_TEMPLATE = """What seniority level and role type are these jobs?
Return ONLY valid JSON, no other text, no markdown fences.
Your response MUST be a JSON object containing a "results" array.
Inside the array, return exactly one object per job with its matching job_index:
{{"results": [{{"job_index": 0, "seniority": "internship" | "entry" | "junior" | "mid" | "senior" | "lead" | "unknown", "role_type": "full-time" | "internship" | "contract" | "freelance" | "unknown", "years_required": number or null, "is_trainee_program": true | false, "confidence": "high" | "medium" | "low"}}]}}

Seniority rules:
- internship: explicitly internship or co-op
- entry: 0-1 years, "entry-level", "new grad", "no experience required", "fresh graduate"
- junior: 1-2 years, or "junior" in title
- mid: 2-5 years, or role described without explicit level (default when ambiguous)
- senior: 5+ years, or "senior" in title
- lead: lead/principal/staff/director/VP/head of department

is_trainee_program: true if explicitly a training program, apprenticeship, or rotational program.

Jobs to analyze:
{jobs_text}"""


def _call_groq_batch(jobs: list[dict], client: Groq) -> list[dict]:
    jobs_text_lines = []
    for idx, job in enumerate(jobs):
        safe = prepare_job_for_llm(job)
        jobs_text_lines.append(
            f"[{idx}] Title: {safe.get('title', '')}\n"
            f"Description: {(safe.get('description') or '')[:1000]}\n---"
        )

    prompt = _PROMPT_TEMPLATE.format(jobs_text="\n".join(jobs_text_lines))
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=3000,
        response_format={"type": "json_object"}
    )
    text = resp.choices[0].message.content.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    raw = json.loads(text)
    validated = SeniorityBatchResult(**raw)
    
    result_map = {r.job_index: r.model_dump() for r in validated.results}
    aligned = []
    for idx in range(len(jobs)):
        if idx in result_map:
            aligned.append(result_map[idx])
        else:
            f = SENIORITY_FALLBACK.model_dump()
            f["job_index"] = idx
            aligned.append(f)
    return aligned


def check_seniority_batch(jobs: list[dict], client: Groq) -> list[dict]:
    """
    Classify job seniority and role type for a batch of jobs.
    Returns a list of SeniorityResult dicts. Uses circuit breaker + retry.
    """
    fallback = []
    for idx in range(len(jobs)):
        f = SENIORITY_FALLBACK.model_dump()
        f["job_index"] = idx
        fallback.append(f)

    return groq_breaker.call_with_fallback(
        _call_groq_batch,
        fallback,
        jobs,
        client,
        max_retries=3,
    )

