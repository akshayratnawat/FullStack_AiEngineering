"""get_current_user against a fake Supabase: no network, no database."""

from typing import Annotated

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import (
    CurrentUser,
    can_use_llm,
    get_current_user,
    get_http_client,
)

USER_ID = "7b0f2c1e-3d4a-4e5f-8a9b-0c1d2e3f4a5b"
CONFIRMED = "2026-01-05T10:00:00Z"


def make_client(handler) -> tuple[TestClient, list[httpx.Request]]:
    """A tiny app with one protected route, whose Supabase is replaced by `handler`."""
    seen: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    app = FastAPI()

    @app.get("/me")
    async def me(
        user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> dict[str, str]:
        return {"id": str(user.id), "email": user.email, "token": user.access_token}

    async def fake_http_client():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(recording),
            base_url="https://fake.supabase.co",
        ) as client:
            yield client

    app.dependency_overrides[get_http_client] = fake_http_client
    return TestClient(app), seen


def supabase_ok(_: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200, json={"id": USER_ID, "email": "analyst@example.com", "email_confirmed_at": CONFIRMED}
    )


def test_valid_token_returns_the_user_and_asks_supabase_with_that_token():
    client, seen = make_client(supabase_ok)

    response = client.get("/me", headers={"Authorization": "Bearer good-token"})

    assert response.status_code == 200
    assert response.json() == {
        "id": USER_ID,
        "email": "analyst@example.com",
        "token": "good-token",
    }
    assert seen[0].url.path == "/auth/v1/user"
    assert seen[0].headers["authorization"] == "Bearer good-token"
    assert seen[0].headers["apikey"]  # Supabase requires the project key on this call


@pytest.mark.parametrize(
    "headers", [{}, {"Authorization": "Basic abc123"}, {"Authorization": "Bearer"}]
)
def test_missing_or_malformed_header_is_401_and_never_calls_supabase(headers):
    client, seen = make_client(supabase_ok)

    response = client.get("/me", headers=headers)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert seen == []


@pytest.mark.parametrize("supabase_status", [401, 403])
def test_token_supabase_rejects_is_401(supabase_status):
    client, _ = make_client(
        lambda _: httpx.Response(supabase_status, json={"msg": "bad_jwt"})
    )

    response = client.get("/me", headers={"Authorization": "Bearer expired"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired token."


def test_supabase_server_error_is_502_not_401():
    client, _ = make_client(lambda _: httpx.Response(500))

    response = client.get("/me", headers={"Authorization": "Bearer good-token"})

    assert response.status_code == 502


def test_supabase_unreachable_is_502_not_401():
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host", request=request)

    client, _ = make_client(down)

    response = client.get("/me", headers={"Authorization": "Bearer good-token"})

    assert response.status_code == 502


def test_verified_user_without_an_email_is_401():
    client, _ = make_client(
        lambda _: httpx.Response(200, json={"id": USER_ID, "email": None})
    )

    response = client.get("/me", headers={"Authorization": "Bearer good-token"})

    assert response.status_code == 401


def test_any_confirmed_address_may_sign_in_and_look_around():
    # Visitors are welcome; only asking questions is limited (see require_llm_access).
    client, _ = make_client(
        lambda _: httpx.Response(
            200, json={"id": USER_ID, "email": "recruiter@gmail.com", "email_confirmed_at": CONFIRMED}
        )
    )

    assert client.get("/me", headers={"Authorization": "Bearer good-token"}).status_code == 200


def test_an_unconfirmed_address_is_403():
    # Otherwise anyone could sign up as the owner's address without owning the mailbox.
    client, _ = make_client(
        lambda _: httpx.Response(200, json={"id": USER_ID, "email": "owner@example.com"})
    )

    response = client.get("/me", headers={"Authorization": "Bearer good-token"})

    assert response.status_code == 403
    assert "Confirm" in response.json()["detail"]


@pytest.mark.parametrize(
    ("email", "allowed"),
    [
        ("owner@example.com", True),  # listed
        ("Owner@Example.COM", True),  # case-insensitive
        ("analyst@driftwood.com", True),  # an allowed domain
        ("recruiter@gmail.com", False),
        ("owner@example.com.evil.io", False),  # a domain must match exactly
        ("analyst@notdriftwood.com", False),
    ],
)
def test_can_use_llm(email, allowed):
    assert can_use_llm(email) is allowed
