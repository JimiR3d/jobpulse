"""
backend/auth.py  — Security Patch #1: JWT Auth Middleware

Replaces the vulnerable pattern of client-supplied user_id query parameters.
Every protected route uses this as a FastAPI dependency to extract the
authenticated user's UUID from the Supabase JWT in the Authorization header.

Usage in routes:
    from auth import get_current_user_id

    @router.get("/")
    def my_endpoint(user_id: str = Depends(get_current_user_id)):
        ...

"""

from fastapi import Header, HTTPException

from db import get_supabase


def get_current_user_id(authorization: str = Header(...)) -> str:
    """
    Extract and verify the Supabase JWT from the Authorization header using Supabase Auth.
    Returns the authenticated user's UUID string.

    Raises:
        401 — missing/malformed Authorization header
        401 — expired or invalid token
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header. Expected: 'Bearer <token>'",
        )

    token = authorization.removeprefix("Bearer ").strip()

    if not token:
        raise HTTPException(status_code=401, detail="Empty bearer token")

    supabase = get_supabase()

    try:
        user_response = supabase.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Token invalid or missing subject claim")
        return user_response.user.id

    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

