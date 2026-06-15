"""
scheduler/pipeline/llm_safety.py  — Security Patch #6

Two-layer LLM safety:
  1. sanitize_for_prompt() — strips prompt injection patterns before any LLM call
  2. redact_pii() — removes PII from job descriptions (GDPR/NDPA compliance)
  3. prepare_job_for_llm() — applies both; use on every job before building a prompt
"""

import re
import logging

logger = logging.getLogger("jobpulse.scheduler")

# Prompt injection patterns to neutralize
_INJECTION_PATTERNS = [
    r"ignore\s+(?:all\s+)?previous\s+instructions",
    r"forget\s+(?:everything|all|your\s+instructions)",
    r"system\s+override",
    r"you\s+are\s+now\s+(?:a|an)\s+",
    r"new\s+instructions\s*:",
    r"\[INST\]|\[\/INST\]|<<SYS>>|<\/SYS>",      # LLaMA jailbreak tokens
    r"###\s*(?:instruction|system|human|assistant)",
    r"<\|im_start\|>|<\|im_end\|>",               # ChatML tokens
    r"<\|endoftext\|>",                            # GPT-2/3 special token
    r"--ignore-previous",
    r"disregard\s+(?:all\s+)?(?:prior|previous)\s+",
]

# PII patterns (Nigerian + international)
_PII_PATTERNS = [
    # Credit/debit card numbers (4-4-4-4 format)
    (r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b", "[CARD_REDACTED]"),
    # Nigerian NIN (11-digit standalone number)
    (r"\b(?:NIN|nin|BVN|bvn)[:\s]*\d{11}\b", "[NIN_REDACTED]"),
    # International phone numbers (E.164 format)
    (r"\+\d{1,3}[\s\-]?\(?\d{1,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{4}", "[PHONE_REDACTED]"),
    # Nigerian local phone numbers (080x, 081x, 090x, etc.)
    (r"\b0[789][01]\d{8}\b", "[PHONE_REDACTED]"),
    # Email addresses
    (r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b", "[EMAIL_REDACTED]"),
    # API keys / bearer tokens (long alphanumeric strings 32+ chars)
    (r"\b(?:sk-|pk-|Bearer\s+)?[A-Za-z0-9_\-]{32,}\b", "[TOKEN_REDACTED]"),
    # Crypto private keys (64-char hex)
    (r"\b[0-9a-fA-F]{64}\b", "[KEY_REDACTED]"),
]


def sanitize_for_prompt(text: str, max_length: int = 2000) -> str:
    """
    Remove prompt injection patterns from text before sending to any LLM.
    Apply to ALL job descriptions, titles, and company names.
    """
    if not text:
        return ""
    sanitized = text
    for pattern in _INJECTION_PATTERNS:
        sanitized = re.sub(pattern, "[FILTERED]", sanitized, flags=re.IGNORECASE)
    return sanitized[:max_length]


def redact_pii(text: str) -> str:
    """
    Redact PII from job descriptions before sending to third-party LLMs.
    Required for GDPR/NDPA compliance — job descriptions may contain
    contact details, card numbers, or NIN/BVN from applicant instructions.
    """
    if not text:
        return ""
    result = text
    for pattern, replacement in _PII_PATTERNS:
        result = re.sub(pattern, replacement, result)
    return result


def prepare_job_for_llm(job: dict) -> dict:
    """
    Apply sanitization + PII redaction to a job dict before any LLM call.
    Returns a COPY — never mutates the original.
    """
    safe = job.copy()
    if safe.get("description"):
        safe["description"] = redact_pii(sanitize_for_prompt(safe["description"], max_length=2000))
    if safe.get("title"):
        safe["title"] = sanitize_for_prompt(safe["title"], max_length=200)
    if safe.get("company"):
        safe["company"] = sanitize_for_prompt(safe["company"], max_length=100)
    return safe
