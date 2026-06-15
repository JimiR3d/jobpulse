"""
backend/routes/profile.py

Resume upload, parsing, and user preference management.
Rate limited: resume upload 5/hour, profile updates 30/minute.
"""

import json
import logging
import os
import re
from typing import List, Optional

import fitz  # PyMuPDF
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from groq import Groq
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from supabase import create_client

from auth import get_current_user_id

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)
logger = logging.getLogger("jobpulse.backend")

_MAX_PDF_SIZE = 5 * 1024 * 1024  # 5MB


def get_supabase():
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )


# ── Resume upload + parsing ──────────────────────────────────────

@router.post("/resume")
@limiter.limit("5/hour")
async def upload_resume(
    request: Request,
    user_id: str = Depends(get_current_user_id),
    file: UploadFile = File(...),
):
    """
    Upload a PDF resume:
    1. Extract text via PyMuPDF
    2. Upload raw PDF to Supabase Storage (resumes bucket)
    3. Parse with Groq LLaMA → structured skills + inferred roles
    4. Store in resumes table and update user_profiles
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    content = await file.read()

    if len(content) > _MAX_PDF_SIZE:
        raise HTTPException(status_code=413, detail="PDF too large (5MB maximum)")

    # Extract text via PyMuPDF
    try:
        doc = fitz.open(stream=content, filetype="pdf")
        raw_text = ""
        for page in doc:
            raw_text += page.get_text()
        doc.close()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Could not read PDF file")

    if len(raw_text.strip()) < 100:
        raise HTTPException(
            status_code=400,
            detail="Could not extract meaningful text from this PDF",
        )

    supabase = get_supabase()

    # Upload to Supabase Storage
    storage_path = f"resumes/{user_id}/{file.filename}"
    try:
        supabase.storage.from_("resumes").upload(
            storage_path,
            content,
            {"content-type": "application/pdf", "upsert": "true"},
        )
    except Exception as e:
        logger.warning(json.dumps({"event": "resume_upload_storage_error", "error": str(e)}))
        # Non-fatal — continue with parsing even if storage upload fails

    # Parse with Groq LLaMA
    groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
    parse_prompt = f"""Extract structured information from this resume. Return ONLY valid JSON, no other text:
{{
  "skills": ["list of technical skills, tools, languages, frameworks — be thorough"],
  "experience_years": 0,
  "inferred_roles": ["2-4 specific job titles this person could realistically apply for"],
  "education": "highest degree and field of study"
}}

Rules:
- experience_years: 0 for fresh graduates, count only post-graduation professional work
- skills: include programming languages, frameworks, tools, databases, cloud platforms, soft skills
- inferred_roles: be specific (e.g. "Junior Data Analyst" not just "Analyst")

Resume text:
{raw_text[:4000]}"""

    try:
        resp = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": parse_prompt}],
            temperature=0.1,
            max_tokens=600,
        )
        text = resp.choices[0].message.content.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        parsed = json.loads(text)
    except Exception as e:
        logger.warning(json.dumps({"event": "resume_groq_parse_error", "error": str(e)}))
        parsed = {"skills": [], "experience_years": 0, "inferred_roles": [], "education": ""}

    # Save to resumes table
    supabase.table("resumes").insert(
        {
            "user_id": user_id,
            "raw_text": raw_text,
            "parsed_skills": parsed.get("skills", []),
            "parsed_experience_years": float(parsed.get("experience_years", 0)),
            "storage_path": storage_path,
        }
    ).execute()

    # Update user_profiles with parsed data
    supabase.table("user_profiles").update(
        {
            "skills": parsed.get("skills", []),
            "target_roles": parsed.get("inferred_roles", []),
        }
    ).eq("user_id", user_id).execute()

    return {"success": True, "parsed": parsed}


# ── Profile get/update ───────────────────────────────────────────

class ProfileUpdate(BaseModel):
    natural_language_description: Optional[str] = Field(None, max_length=1000)
    target_roles: Optional[List[str]] = None
    skills: Optional[List[str]] = None
    seniority_levels: Optional[List[str]] = None
    role_types: Optional[List[str]] = None
    min_display_score: Optional[int] = Field(None, ge=0, le=100)
    show_senior: Optional[bool] = None
    show_unverified_remote: Optional[bool] = None
    notification_threshold: Optional[int] = Field(None, ge=0, le=100)
    notification_frequency: Optional[str] = None
    currency_preference: Optional[str] = None


@router.get("/")
def get_profile(user_id: str = Depends(get_current_user_id)):
    """Return the full user record + profile joined."""
    supabase = get_supabase()
    resp = (
        supabase.table("users")
        .select("*, user_profiles(*), resumes(id, parsed_skills, created_at)")
        .eq("id", user_id)
        .order("created_at", desc=True, foreign_table="resumes")
        .limit(1, foreign_table="resumes")
        .execute()
    )
    return resp.data[0] if resp.data else {}


@router.patch("/")
@limiter.limit("30/minute")
def update_profile(
    request: Request,
    update: ProfileUpdate,
    user_id: str = Depends(get_current_user_id),
):
    """Update user preferences. Splits fields between users and user_profiles tables."""
    supabase = get_supabase()

    update_data = update.model_dump(exclude_none=True)

    # Fields that go to the users table
    user_fields = {"notification_threshold", "notification_frequency"}
    # Fields that go to user_profiles
    profile_fields = set(update_data.keys()) - user_fields

    if profile_data := {k: update_data[k] for k in profile_fields if k in update_data}:
        supabase.table("user_profiles").update(profile_data).eq(
            "user_id", user_id
        ).execute()

    if user_data := {k: update_data[k] for k in user_fields if k in update_data}:
        supabase.table("users").update(user_data).eq("id", user_id).execute()

    return {"success": True}
