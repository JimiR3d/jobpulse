"""
backend/routes/sources.py

Job source library management.
Library sources (is_library=true) are globally readable.
Custom user sources are private per user.
"""

import os
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from supabase import create_client

from auth import get_current_user_id

router = APIRouter()


def get_supabase():
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )


@router.get("/library")
def get_source_library(
    category: Optional[str] = Query(None),
    _user_id: str = Depends(get_current_user_id),  # Auth check — must be logged in
):
    """Return all pre-loaded library sources, optionally filtered by category."""
    supabase = get_supabase()
    query = (
        supabase.table("job_sources")
        .select("*")
        .eq("is_library", True)
        .order("name")
    )
    if category:
        query = query.eq("category", category)
    resp = query.execute()
    return resp.data


@router.get("/categories")
def get_library_categories(_user_id: str = Depends(get_current_user_id)):
    """Return distinct categories from the library for filter dropdowns."""
    supabase = get_supabase()
    resp = (
        supabase.table("job_sources")
        .select("category")
        .eq("is_library", True)
        .execute()
    )
    categories = sorted({r["category"] for r in resp.data if r.get("category")})
    return {"categories": categories}


@router.get("/")
def get_user_sources(user_id: str = Depends(get_current_user_id)):
    """Return library sources + the user's custom private sources."""
    supabase = get_supabase()
    lib = (
        supabase.table("job_sources")
        .select("*")
        .eq("is_library", True)
        .order("name")
        .execute()
    )
    custom = (
        supabase.table("job_sources")
        .select("*")
        .eq("user_id", user_id)
        .eq("is_library", False)
        .order("name")
        .execute()
    )
    return {"library": lib.data, "custom": custom.data}


class ToggleSource(BaseModel):
    is_active: bool


@router.patch("/{source_id}/toggle")
def toggle_source(
    source_id: str,
    body: ToggleSource,
    user_id: str = Depends(get_current_user_id),
):
    """
    Activate or deactivate a source.
    For library sources: any user can toggle (affects global state in MVP).
    For custom sources: only the owner can toggle.

    TODO(multi-user): Library source toggles mutate global state. When adding
    more users, create a `user_source_overrides(user_id, source_id, is_active)`
    junction table so each user has their own active/inactive state.
    """
    supabase = get_supabase()

    # Fetch the source to check ownership
    source_resp = (
        supabase.table("job_sources").select("*").eq("id", source_id).execute()
    )
    if not source_resp.data:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Source not found")

    source = source_resp.data[0]

    # Custom sources: ownership check
    if not source["is_library"] and source.get("user_id") != user_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Not authorized to modify this source")

    supabase.table("job_sources").update({"is_active": body.is_active}).eq(
        "id", source_id
    ).execute()

    return {"success": True, "source_id": source_id, "is_active": body.is_active}
