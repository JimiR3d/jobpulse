"""
backend/routes/jobs.py

Job feed and status update endpoints.
user_id is always sourced from the verified JWT — never from query params.
"""

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from supabase import create_client

from auth import get_current_user_id

router = APIRouter()

_VALID_STATUSES = {"new", "seen", "saved", "applied", "rejected"}


def get_supabase():
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )


class StatusUpdate(BaseModel):
    status: str  # new | seen | saved | applied | rejected


@router.get("/")
def get_jobs(
    user_id: str = Depends(get_current_user_id),
    status: Optional[str] = Query(None),
    min_score: int = Query(0, ge=0, le=100),
    max_score: int = Query(100, ge=0, le=100),
    source_id: Optional[str] = Query(None),
    seniority: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    show_senior: bool = Query(False),
):
    """
    Return paginated job matches for the authenticated user.
    Joined with full job data and source health info.
    """
    supabase = get_supabase()

    query = (
        supabase.table("job_matches")
        .select("*, jobs(*, job_sources(name, health_status, category))")
        .eq("user_id", user_id)
        .gte("match_score", min_score)
        .lte("match_score", max_score)
        .order("match_score", desc=True)
        .limit(limit)
        .offset(offset)
    )

    if status:
        query = query.eq("status", status)

    if not show_senior:
        # Exclude senior/lead jobs from main feed unless user opted in
        query = query.not_.in_("jobs.seniority", ["senior", "lead"])

    resp = query.execute()

    # Auto-mark fetched "new" jobs as "seen"
    new_ids = [
        m["id"] for m in resp.data if m.get("status") == "new"
    ]
    if new_ids:
        supabase.table("job_matches").update({"status": "seen"}).in_(
            "id", new_ids
        ).execute()

    return {"jobs": resp.data, "count": len(resp.data), "offset": offset}


@router.patch("/{match_id}/status")
def update_job_status(
    match_id: str,
    update: StatusUpdate,
    user_id: str = Depends(get_current_user_id),
):
    """Update the status of a job match (save, apply, reject, etc.)."""
    if update.status not in _VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(_VALID_STATUSES)}",
        )

    supabase = get_supabase()
    # The eq("user_id", user_id) ensures users can only update their own matches
    resp = (
        supabase.table("job_matches")
        .update({"status": update.status})
        .eq("id", match_id)
        .eq("user_id", user_id)  # Ownership check — prevents cross-user mutations
        .execute()
    )

    if not resp.data:
        raise HTTPException(
            status_code=404,
            detail="Match not found or you don't have permission to update it",
        )

    return resp.data[0]
