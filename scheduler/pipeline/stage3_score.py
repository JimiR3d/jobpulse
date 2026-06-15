"""
scheduler/pipeline/stage3_score.py

Stage 3 of the AI pipeline: Match scoring via Google Gemini Flash.

Only jobs that survive Stages 1 & 2 reach here.
Scores 0-100 against the user's profile:
  90-100 → Near-perfect match
  75-89  → Strong match
  60-74  → Decent match (worth reviewing)
  40-59  → Stretch (some overlap, clear gaps)
  0-39   → Weak match

Also extracts currency_signal and any disqualifiers.
"""

import json
import logging
import os
import re

import google.generativeai as genai

from pipeline.llm_safety import prepare_job_for_llm
from pipeline.models import MatchScoreResult, SCORE_FALLBACK
from pipeline.resilience import gemini_breaker

logger = logging.getLogger("jobpulse.scheduler")

# Configure Gemini on module import
genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))
_model = genai.GenerativeModel("gemini-1.5-flash")

_PROMPT_TEMPLATE = """Score this job against this candidate's profile. Be generous — the candidate is very open to new roles.
Return ONLY valid JSON, no other text, no markdown fences:
{{"score": 0-100, "match_reasons": ["max 4 specific reasons like 'Python required — in your resume'"], "currency_signal": "usd" | "gbp" | "eur" | "local" | "unknown", "disqualifiers": ["any red flags despite decent score, empty array if none"]}}

Scoring guide:
90-100: Near-perfect match (most skills align, perfect role type and seniority)
75-89: Strong match (most key requirements met)
60-74: Decent match (worth reviewing, some gaps)
40-59: Stretch (some overlap, clear gaps)
0-39: Weak (minimal overlap)

currency_signal: detect from salary symbols ($, £, €), "USD/GBP/EUR" text, company HQ country, or job board context.

Candidate profile:
What I'm looking for: {nl_description}
Skills: {skills}
Acceptable seniority: {seniority}
Open to: internships, trainee programs, entry-level, junior roles, being trained from scratch

Job:
Title: {title}
Company: {company}
Tags/Stack: {tags}
Description (first 500 chars): {description}"""


def _call_gemini(job: dict, user_profile: dict) -> dict:
    safe = prepare_job_for_llm(job)
    prompt = _PROMPT_TEMPLATE.format(
        nl_description=(
            user_profile.get("natural_language_description")
            or "Entry-level or internship remote roles, willing to be trained"
        ),
        skills=", ".join(user_profile.get("skills") or []),
        seniority=", ".join(
            user_profile.get("seniority_levels") or ["entry", "junior", "internship"]
        ),
        title=safe.get("title", ""),
        company=safe.get("company", ""),
        tags=", ".join(safe.get("tags") or []),
        description=(safe.get("description") or "")[:500],
    )
    response = _model.generate_content(prompt)
    text = response.text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    raw = json.loads(text)
    validated = MatchScoreResult(**raw)
    return validated.model_dump()


def score_job(job: dict, user_profile: dict) -> dict:
    """
    Score a job against a user profile using Gemini Flash.
    Returns MatchScoreResult dict. Uses circuit breaker + retry.
    """
    return gemini_breaker.call_with_fallback(
        _call_gemini,
        SCORE_FALLBACK.model_dump(),
        job,
        user_profile,
        max_retries=3,
    )
