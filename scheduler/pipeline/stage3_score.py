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
from pipeline.models import MatchScoreBatchResult, SCORE_FALLBACK
from pipeline.resilience import gemini_breaker

logger = logging.getLogger("jobpulse.scheduler")

# Configure Gemini on module import
genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))
_model = genai.GenerativeModel("gemini-1.5-pro-latest")

_PROMPT_TEMPLATE = """Score these jobs against this candidate's profile. Be generous — the candidate is very open to new roles.
Return ONLY valid JSON, no other text, no markdown fences.
Your response MUST be a JSON object containing a "results" array.
Inside the array, return exactly one object per job with its matching job_index:
{{"results": [{{"job_index": 0, "score": 50, "match_reasons": ["max 4 specific reasons"], "currency_signal": "usd" | "gbp" | "eur" | "local" | "unknown", "disqualifiers": ["any red flags, empty array if none"]}}]}}

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

Jobs to analyze:
{jobs_text}"""


def _call_gemini_batch(jobs: list[dict], user_profile: dict) -> list[dict]:
    jobs_text_lines = []
    for idx, job in enumerate(jobs):
        safe = prepare_job_for_llm(job)
        jobs_text_lines.append(
            f"[{idx}] Title: {safe.get('title', '')}\n"
            f"Company: {safe.get('company', '')}\n"
            f"Tags/Stack: {', '.join(safe.get('tags') or [])}\n"
            f"Description: {(safe.get('description') or '')[:500]}\n---"
        )

    prompt = _PROMPT_TEMPLATE.format(
        nl_description=(
            user_profile.get("natural_language_description")
            or "Entry-level or internship remote roles, willing to be trained"
        ),
        skills=", ".join(user_profile.get("skills") or []),
        seniority=", ".join(
            user_profile.get("seniority_levels") or ["entry", "junior", "internship"]
        ),
        jobs_text="\n".join(jobs_text_lines),
    )
    
    response = _model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            response_mime_type="application/json",
        ),
    )
    text = response.text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    raw = json.loads(text)
    validated = MatchScoreBatchResult(**raw)
    
    result_map = {r.job_index: r.model_dump() for r in validated.results}
    aligned = []
    for idx in range(len(jobs)):
        if idx in result_map:
            aligned.append(result_map[idx])
        else:
            f = SCORE_FALLBACK.model_dump()
            f["job_index"] = idx
            aligned.append(f)
    return aligned


def score_job_batch(jobs: list[dict], user_profile: dict) -> list[dict]:
    """
    Score a batch of jobs against a user profile using Gemini Flash.
    Returns a list of MatchScoreResult dicts. Uses circuit breaker + retry.
    """
    fallback = []
    for idx in range(len(jobs)):
        f = SCORE_FALLBACK.model_dump()
        f["job_index"] = idx
        fallback.append(f)

    return gemini_breaker.call_with_fallback(
        _call_gemini_batch,
        fallback,
        jobs,
        user_profile,
        max_retries=3,
    )

