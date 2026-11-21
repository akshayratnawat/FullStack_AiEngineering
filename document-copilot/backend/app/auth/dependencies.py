"""Who is calling? Verifies the caller's Supabase token and exposes `get_current_user`.

Use it on any route that needs a signed-in user:

    @router.get("/threads")
    async def list_threads(user: Annotated[CurrentUser, Depends(get_current_user)]): ...

The token is checked by asking Supabase Auth, not by verifying its signature here:
that is correct whatever key type the project signs with, and needs no extra package.
It costs one request to Supabase per call; local verification can replace it later
without changing any route.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

# auto_error=False so a missing header reaches us and gets our 401 (with the
# WWW-Authenticate header), instead of FastAPI's own response.
bearer_scheme = HTTPBearer(auto_error=False)

SUPABASE_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    email: str
    # Pass this to create_user_client() so database queries run as this user (RLS applies).
    access_token: str


NOT_ALLOWED = "Document Copilot is only for Driftwood email addresses."
NOT_CONFIRMED = "Confirm your email address first, using the link we sent you."


def email_allowed(email: str) -> bool:
    """True when the address is in an allowed domain or is listed on its own."""
    email = email.strip().lower()
    domain = email.rpartition("@")[2]
    return domain in settings.email_domains or email in settings.extra_emails


def forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_http_client() -> AsyncIterator[httpx.AsyncClient]:
    # A dependency (not a global) so tests can replace it with a fake Supabase.
    async with httpx.AsyncClient(
        base_url=settings.supabase_url.rstrip("/"), timeout=SUPABASE_TIMEOUT_SECONDS
    ) as client:
        yield client


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> CurrentUser:
    if credentials is None:
        raise unauthorized("Missing bearer token.")
    token = credentials.credentials

    try:
        response = await client.get(
            "/auth/v1/user",
            headers={
                "apikey": settings.supabase_anon_key.get_secret_value(),
                "Authorization": f"Bearer {token}",
            },
        )
    except httpx.HTTPError as error:
        # We could not ask Supabase at all: not the caller's fault, so not a 401.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not reach Supabase Auth.",
        ) from error

    if response.status_code in (
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    ):
        raise unauthorized("Invalid or expired token.")
    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Supabase Auth failed to verify the token.",
        )

    profile = response.json()
    user_id, email = profile.get("id"), profile.get("email")
    if not user_id or not email:
        # This app signs in with email only, so a verified user without one is unexpected.
        raise unauthorized("Token does not belong to an email user.")
    # Signing up is open in Supabase, so this is the gate: a valid login is not enough, the
    # address must be one we allow AND proven to belong to the person (confirmed). Without
    # the second check anyone could sign up as "someone@driftwood.com" without owning it.
    if not email_allowed(email):
        raise forbidden(NOT_ALLOWED)
    if not profile.get("email_confirmed_at"):
        raise forbidden(NOT_CONFIRMED)
    return CurrentUser(id=UUID(user_id), email=email, access_token=token)
