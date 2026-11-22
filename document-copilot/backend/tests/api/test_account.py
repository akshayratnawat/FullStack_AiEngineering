"""GET /me: the browser's check that a signed-in account may use the app."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.account import router
from app.auth.dependencies import get_current_user
from tests.conftest import ALICE, BOB


def test_me_returns_the_allowed_user():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: ALICE

    response = TestClient(app).get("/me")

    assert response.status_code == 200
    assert response.json() == {"id": str(ALICE.id), "email": ALICE.email, "can_ask": True}


def test_me_tells_a_visitor_they_cannot_ask():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: BOB

    body = TestClient(app).get("/me").json()

    assert body["can_ask"] is False


def test_me_without_a_token_is_401():
    app = FastAPI()
    app.include_router(router)

    assert TestClient(app).get("/me").status_code == 401
