"""The chat routes with a fake store and a fake signed-in user: no network, no database."""

import json
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.chat import get_agent, get_agent_deps, get_chat_store, router
from app.auth.dependencies import get_current_user
from tests.conftest import ALICE, BOB


def make_client(store, user=ALICE) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.state.service_client = object()  # never used: auth fails first, or the store is faked
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_chat_store] = lambda: store
        # The orchestrator's agent call is faked in conftest, so any placeholder will do.
        app.dependency_overrides[get_agent] = lambda: object()
        app.dependency_overrides[get_agent_deps] = lambda: object()
    return TestClient(app)


def stream_request(thread_id, text="What was Apple's revenue?") -> dict:
    return {
        "threadId": str(thread_id),
        "messages": [{"id": "c1", "role": "user", "parts": [{"type": "text", "text": text}]}],
    }


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/threads"),
        ("post", "/threads"),
        ("patch", f"/threads/{uuid4()}"),
        ("delete", f"/threads/{uuid4()}"),
        ("get", f"/threads/{uuid4()}/messages"),
        ("post", "/chat/stream"),
    ],
)
def test_every_route_rejects_a_missing_token_with_401(store, method, path):
    client = make_client(store, user=None)

    response = getattr(client, method)(path)

    assert response.status_code == 401


def test_create_then_list_threads(store):
    client = make_client(store)

    created = client.post("/threads")
    listed = client.get("/threads")

    assert created.status_code == 201
    assert listed.json()[0]["id"] == created.json()["id"]


def test_messages_load_in_sdk_shape(store):
    thread_id = store.add_thread(ALICE)
    store.messages[thread_id] = [
        {"id": "m1", "role": "user", "content": "hi", "parts": None},
        {
            "id": "m2",
            "role": "assistant",
            "content": "hello",
            "parts": [{"type": "text", "text": "hello"}],
        },
    ]

    response = make_client(store).get(f"/threads/{thread_id}/messages")

    assert response.status_code == 200
    assert response.json() == [
        {"id": "m1", "role": "user", "parts": [{"type": "text", "text": "hi"}]},
        {"id": "m2", "role": "assistant", "parts": [{"type": "text", "text": "hello"}]},
    ]


def test_another_users_thread_is_403_for_history_and_for_streaming(store):
    bobs_thread = store.add_thread(BOB)
    client = make_client(store, user=ALICE)

    history = client.get(f"/threads/{bobs_thread}/messages")
    stream = client.post("/chat/stream", json=stream_request(bobs_thread))

    assert history.status_code == 403
    assert stream.status_code == 403
    assert store.saved_turns == []  # rejected before any work


def test_unknown_thread_is_404(store):
    client = make_client(store)

    assert client.get(f"/threads/{uuid4()}/messages").status_code == 404
    assert client.post("/chat/stream", json=stream_request(uuid4())).status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"messages": []},  # no threadId, no messages
        {"threadId": "not-a-uuid", "messages": [{"role": "user", "parts": []}]},
    ],
)
def test_malformed_requests_are_422(store, body):
    assert make_client(store).post("/chat/stream", json=body).status_code == 422


def test_a_last_message_that_is_not_a_user_question_is_422(store):
    thread_id = store.add_thread(ALICE)
    body = stream_request(thread_id)
    body["messages"][0]["role"] = "assistant"

    response = make_client(store).post("/chat/stream", json=body)

    assert response.status_code == 422
    assert store.saved_turns == []


def test_streaming_returns_sse_with_the_sdk_header_and_then_saves(store):
    thread_id = store.add_thread(ALICE)

    response = make_client(store).post("/chat/stream", json=stream_request(thread_id))

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-vercel-ai-ui-message-stream"] == "v1"
    events = [e for e in response.text.split("\n\n") if e]
    assert json.loads(events[0][len("data: ") :])["type"] == "start"
    assert events[-1] == "data: [DONE]"
    assert len(store.saved_turns) == 1


def test_delete_removes_the_thread_and_its_messages(store):
    thread_id = store.add_thread(ALICE, title="Apple revenue")
    client = make_client(store)

    response = client.delete(f"/threads/{thread_id}")

    assert response.status_code == 204
    assert thread_id not in store.threads
    assert client.get(f"/threads/{thread_id}/messages").status_code == 404


def test_delete_and_rename_refuse_another_users_thread(store):
    bobs_thread = store.add_thread(BOB, title="Bob's")
    client = make_client(store, user=ALICE)

    assert client.delete(f"/threads/{bobs_thread}").status_code == 403
    assert client.patch(f"/threads/{bobs_thread}", json={"title": "mine now"}).status_code == 403
    assert store.threads[bobs_thread]["title"] == "Bob's"  # untouched


def test_delete_and_rename_unknown_thread_is_404(store):
    client = make_client(store)

    assert client.delete(f"/threads/{uuid4()}").status_code == 404
    assert client.patch(f"/threads/{uuid4()}", json={"title": "x"}).status_code == 404


def test_rename_trims_and_saves_the_title(store):
    thread_id = store.add_thread(ALICE, title="Old")

    response = make_client(store).patch(f"/threads/{thread_id}", json={"title": "  AWS   margin  "})

    assert response.status_code == 200
    assert response.json()["title"] == "AWS margin"
    assert store.threads[thread_id]["title"] == "AWS margin"


@pytest.mark.parametrize("title", ["", "   ", "x" * 121])
def test_rename_rejects_a_blank_or_too_long_title(store, title):
    thread_id = store.add_thread(ALICE, title="Old")

    response = make_client(store).patch(f"/threads/{thread_id}", json={"title": title})

    assert response.status_code == 422
    assert store.threads[thread_id]["title"] == "Old"
