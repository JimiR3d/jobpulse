"""
backend/db.py

Singleton Supabase client for the backend.
All routes should import get_supabase() from here instead of creating
their own client instances on every request.
"""

import os

from supabase import create_client, Client

_client: Client | None = None


def get_supabase() -> Client:
    """Return a module-level Supabase client, created once on first call."""
    global _client
    if _client is None:
        _client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        )
    return _client
