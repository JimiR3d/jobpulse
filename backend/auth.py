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

import os

import jwt
from fastapi import Header, HTTPException

SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")


def get_current_user_id(authorization: str = Header(...)) -> str:
    """
    Extract and verify the Supabase JWT from the Authorization header.
    Returns the authenticated user's UUID string.

    Raises:
        401 — missing/malformed Authorization header
        401 — expired token
        401 — invalid token signature
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header. Expected: 'Bearer <token>'",
        )

    token = authorization.removeprefix("Bearer ").strip()

    if not token:
        raise HTTPException(status_code=401, detail="Empty bearer token")

    try:
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False},  # Supabase doesn't use the aud claim
        )
        user_id: str | None = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Token missing subject claim")
        return user_id

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired — please log in again")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
