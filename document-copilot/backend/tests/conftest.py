"""Shared test doubles. Nothing here touches the network or a database."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.auth.dependencies import CurrentUser
from app.chat import orchestrator

ALICE = CurrentUser(id=uuid4(), email="alice@example.com", access_token="alice-token")
BOB = CurrentUser(id=uuid4(), email="bob@example.com", access_token="bob-token")


class FakeStore:
    """In-memory stand-in for ChatStore, with the same methods."""

    def __init__(self) -> None:
        self.threads: dict[UUID, dict] = {}
        self.messages: dict[UUID, list[dict]] = {}
        self.saved_turns: list[dict] = []

    def add_thread(self, owner: CurrentUser, title: str | None = None) -> UUID:
        thread_id = uuid4()
        self.threads[thread_id] = {"owner": owner.id, "title": title}
        self.messages[thread_id] = []
        return thread_id

    async def list_threads(self) -> list[dict]:
        now = datetime.now(UTC).isoformat()
        return [
            {"id": str(i), "title": t["title"], "created_at": now, "updated_at": now}
            for i, t in self.threads.items()
        ]

    async def create_thread(self, user: CurrentUser) -> dict:
        thread_id = self.add_thread(user)
        now = datetime.now(UTC).isoformat()
        return {"id": str(thread_id), "title": None, "created_at": now, "updated_at": now}

    async def get_thread_owner(self, thread_id: UUID) -> UUID | None:
        thread = self.threads.get(thread_id)
        return thread["owner"] if thread else None

    async def get_thread_title(self, thread_id: UUID) -> str | None:
        return self.threads[thread_id]["title"]

    async def list_messages(self, thread_id: UUID) -> list[dict]:
        return self.messages[thread_id]

    async def save_turn(self, **turn) -> None:
        self.saved_turns.append(turn)


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture(autouse=True)
def no_stub_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orchestrator, "STUB_WORD_DELAY_SECONDS", 0)
