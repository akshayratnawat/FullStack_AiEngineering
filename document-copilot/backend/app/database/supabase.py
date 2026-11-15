"""Supabase API clients: one that acts as a signed-in user, one with full backend power.

Why two: a user-scoped client sends the user's token, so Postgres applies the
row-level security policies and the user can only touch their own rows. The
service-role client bypasses RLS; use it only for trusted backend work such as
ingestion. Never hand it to code that acts on a user's behalf.

These are plain factories, not shared globals. Create the service client once
at startup and keep it on `app.state`; create a user client per request.
"""

from supabase import AsyncClient, AsyncClientOptions, acreate_client

from app.config import settings


async def create_service_client() -> AsyncClient:
    """Client with the service-role key. Bypasses RLS: backend-only, never on a user's behalf."""
    return await acreate_client(
        settings.supabase_url,
        settings.supabase_service_role_key.get_secret_value(),
    )


async def create_user_client(access_token: str) -> AsyncClient:
    """Client that acts as the user who owns `access_token`; RLS applies to every query.

    `access_token` is the Supabase JWT from the request's Authorization header. Verify
    it first (the auth step does that); this function only attaches it.
    """
    options = AsyncClientOptions(
        # Sent on every request in place of the anon key, so auth.uid() is the user.
        headers={"Authorization": f"Bearer {access_token}"},
        # This client lives for one request: no background token refresh, no stored session.
        auto_refresh_token=False,
        persist_session=False,
    )
    return await acreate_client(
        settings.supabase_url,
        settings.supabase_anon_key.get_secret_value(),
        options,
    )
