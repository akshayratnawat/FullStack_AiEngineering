"""get_current_user against a fake Supabase: no network, no database."""

from typing import Annotated

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import CurrentUser, get_current_user, get_http_client

USER_ID = "7b0f2c1e-3d4a-4e5f-8a9b-0c1d2e3f4a5b"


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
    return httpx.Response(200, json={"id": USER_ID, "email": "analyst@example.com"})


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
