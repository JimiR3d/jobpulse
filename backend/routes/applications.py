"""
backend/routes/applications.py

Endpoints for automated job application materials (Cover Letters, QA).
Uses Gemini Pro for complex reasoning.
"""

import json
import logging
import os
from typing import Optional

import google.generativeai as genai
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from auth import get_current_user_id
from db import get_supabase

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)
logger = logging.getLogger("jobpulse.backend")

# Configure Gemini
genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))


class CoverLetterResponse(BaseModel):
    cover_letter: str


@router.post("/{match_id}/cover-letter", response_model=CoverLetterResponse)
@limiter.limit("5/minute")
def generate_cover_letter(
    request: Request,
    match_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Generate a tailored cover letter using Gemini Pro based on the job description,
    user profile, and resume. Saves it to the database.
    """
    if not os.environ.get("GEMINI_API_KEY"):
        raise HTTPException(status_code=500, detail="Gemini API key is not configured")

    supabase = get_supabase()

    # 1. Fetch Job Match with Job Details
    match_resp = (
        supabase.table("job_matches")
        .select("id, cover_letter, jobs(title, company, description)")
        .eq("id", match_id)
        .eq("user_id", user_id)
        .execute()
    )

    if not match_resp.data:
        raise HTTPException(status_code=404, detail="Job match not found")

    match_data = match_resp.data[0]
    job_data = match_data.get("jobs")
    if not job_data:
        raise HTTPException(status_code=400, detail="Associated job details not found")

    # 2. Fetch User Profile
    profile_resp = (
        supabase.table("user_profiles")
        .select("natural_language_description, skills")
        .eq("user_id", user_id)
        .execute()
    )
    profile_data = profile_resp.data[0] if profile_resp.data else {}

    # 3. Fetch Latest Resume
    resume_resp = (
        supabase.table("resumes")
        .select("raw_text")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    resume_text = resume_resp.data[0].get("raw_text", "") if resume_resp.data else ""

    if not resume_text:
        raise HTTPException(
            status_code=400, 
            detail="Please upload a resume first to generate a cover letter."
        )

    # 4. Construct Prompt
    prompt = f"""You are an expert career coach and copywriter.
Write a highly tailored, concise, and compelling cover letter for the following job.
Use the candidate's resume and preferences to highlight ONLY the most relevant skills.
Keep it under 300 words. Do NOT include generic filler.
Write the cover letter in Markdown format.

CANDIDATE PREFERENCES:
{profile_data.get('natural_language_description', 'N/A')}
CANDIDATE SKILLS:
{', '.join(profile_data.get('skills', []))}

CANDIDATE RESUME:
{resume_text}

---
JOB TITLE: {job_data.get('title')}
COMPANY: {job_data.get('company')}

JOB DESCRIPTION:
{job_data.get('description')}
"""

    try:
        # Use gemini-pro-latest for complex reasoning
        model = genai.GenerativeModel('gemini-pro-latest')
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.4,
                max_output_tokens=1000,
            )
        )
        
        cover_letter_markdown = response.text.strip()

        # Save to database
        supabase.table("job_matches").update(
            {"cover_letter": cover_letter_markdown}
        ).eq("id", match_id).eq("user_id", user_id).execute()

        return {"cover_letter": cover_letter_markdown}

    except Exception as e:
        logger.error(json.dumps({"event": "cover_letter_generation_error", "error": str(e)}))
        raise HTTPException(status_code=500, detail="Failed to generate cover letter using AI")
