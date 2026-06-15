"""
scheduler/pipeline/models.py  — Security Patch #9

Pydantic models for validating LLM output from all 3 AI pipeline stages.
If the LLM returns malformed JSON or missing fields, the model fills in
safe defaults — the pipeline never crashes on bad LLM output.
"""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


class RemoteCheckResult(BaseModel):
    """Output of Stage 1 — remote location verification."""
    
    job_index: int = -1
    remote_type: Literal[
        "worldwide", "us_only", "eu_only", "country_specific", "hybrid_only", "unknown"
    ] = "unknown"
    confidence: Literal["high", "medium", "low"] = "low"
    reason: str = ""

class RemoteCheckBatchResult(BaseModel):
    """Batch wrapper for Stage 1."""
    results: List[RemoteCheckResult] = Field(default_factory=list)


class SeniorityResult(BaseModel):
    """Output of Stage 2 — seniority and role type classification."""
    
    job_index: int = -1
    seniority: Literal[
        "internship", "entry", "junior", "mid", "senior", "lead", "unknown"
    ] = "unknown"
    role_type: Literal[
        "full-time", "internship", "contract", "freelance", "unknown"
    ] = "unknown"
    years_required: Optional[float] = None
    is_trainee_program: bool = False
    confidence: Literal["high", "medium", "low"] = "low"

class SeniorityBatchResult(BaseModel):
    """Batch wrapper for Stage 2."""
    results: List[SeniorityResult] = Field(default_factory=list)


class MatchScoreResult(BaseModel):
    """Output of Stage 3 — candidate match scoring."""
    
    job_index: int = -1
    score: int = Field(default=50, ge=0, le=100)
    match_reasons: List[str] = Field(default_factory=list)
    currency_signal: Literal["usd", "gbp", "eur", "local", "unknown"] = "unknown"
    disqualifiers: List[str] = Field(default_factory=list)

    @field_validator("match_reasons")
    @classmethod
    def cap_reasons(cls, v: List[str]) -> List[str]:
        """Never allow more than 4 match reasons regardless of LLM output."""
        return v[:4]

    @field_validator("disqualifiers")
    @classmethod
    def cap_disqualifiers(cls, v: List[str]) -> List[str]:
        """Cap disqualifiers at 3."""
        return v[:3]

class MatchScoreBatchResult(BaseModel):
    """Batch wrapper for Stage 3."""
    results: List[MatchScoreResult] = Field(default_factory=list)


# Pre-instantiated fallbacks — returned when LLM fails or circuit opens
REMOTE_FALLBACK = RemoteCheckResult()
SENIORITY_FALLBACK = SeniorityResult()
SCORE_FALLBACK = MatchScoreResult()

