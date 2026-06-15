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
from pipeline.models import SeniorityResult, SENIORITY_FALLBACK
from pipeline.resilience import groq_breaker

logger = logging.getLogger("jobpulse.scheduler")

_PROMPT_TEMPLATE = """What seniority level and role type is this job?
Return ONLY valid JSON, no other text, no markdown fences:
{{"seniority": "internship" | "entry" | "junior" | "mid" | "senior" | "lead" | "unknown", "role_type": "full-time" | "internship" | "contract" | "freelance" | "unknown", "years_required": number or null, "is_trainee_program": true | false, "confidence": "high" | "medium" | "low"}}

Seniority rules:
- internship: explicitly internship or co-op
- entry: 0-1 years, "entry-level", "new grad", "no experience required", "fresh graduate"
- junior: 1-2 years, or "junior" in title
- mid: 2-5 years, or role described without explicit level (default when ambiguous)
- senior: 5+ years, or "senior" in title
- lead: lead/principal/staff/director/VP/head of department

is_trainee_program: true if explicitly a training program, apprenticeship, or rotational program.

Job Title: {title}
Description: {description}"""


def _call_groq(job: dict, client: Groq) -> dict:
    safe = prepare_job_for_llm(job)
    prompt = _PROMPT_TEMPLATE.format(
        title=safe.get("title", ""),
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
    validated = SeniorityResult(**raw)
    return validated.model_dump()


def check_seniority(job: dict, client: Groq) -> dict:
    """
    Classify job seniority and role type.
    Returns SeniorityResult dict. Uses circuit breaker + retry.
    """
    return groq_breaker.call_with_fallback(
        _call_groq,
        SENIORITY_FALLBACK.model_dump(),
        job,
        client,
        max_retries=3,
    )
