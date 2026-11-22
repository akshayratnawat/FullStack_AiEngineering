"""Shared test doubles. Nothing here touches the network or a database."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.assistant.outputs import GroundedAnswer
from app.auth.dependencies import CurrentUser
from app.chat import orchestrator
from app.config import settings

ALICE = CurrentUser(id=uuid4(), email="alice@example.com", access_token="alice-token")
BOB = CurrentUser(id=uuid4(), email="bob@example.com", access_token="bob-token")


@pytest.fixture(autouse=True)
def demo_accounts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Alice may ask questions; Bob (and anyone else) is a visitor. Independent of the real .env."""
    monkeypatch.setattr(settings, "llm_allowed_emails", "alice@example.com, owner@example.com")
    monkeypatch.setattr(settings, "llm_allowed_domains", "driftwood.com")


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

    async def delete_thread(self, thread_id: UUID) -> None:
        del self.threads[thread_id]
        del self.messages[thread_id]

    async def rename_thread(self, thread_id: UUID, title: str) -> dict:
        self.threads[thread_id]["title"] = title
        now = datetime.now(UTC).isoformat()
        return {"id": str(thread_id), "title": title, "created_at": now, "updated_at": now}

    async def get_thread_owner(self, thread_id: UUID) -> UUID | None:
        thread = self.threads.get(thread_id)
        return thread["owner"] if thread else None

    async def get_thread_title(self, thread_id: UUID) -> str | None:
        return self.threads[thread_id]["title"]

    async def list_messages(self, thread_id: UUID) -> list[dict]:
        return self.messages[thread_id]

    async def save_turn(self, **turn) -> None:
        self.saved_turns.append(turn)
        # Also keep the messages, as the real store does, so a test can reload the thread.
        for role, text, parts in (
            ("user", turn["user_text"], turn["user_parts"]),
            ("assistant", turn["assistant_text"], turn["assistant_parts"]),
        ):
            row = {"id": str(uuid4()), "role": role, "content": text, "parts": parts}
            self.messages[turn["thread_id"]].append(row)


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture(autouse=True)
def no_stream_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip the typing-effect pause between streamed words."""
    monkeypatch.setattr(orchestrator, "STREAM_WORD_DELAY_SECONDS", 0)


@pytest.fixture(autouse=True)
def canned_agent(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Replace the real agent run with a canned reply; returns a log of the calls it received.

    A test that needs a failure or a different answer patches `orchestrator.answer_question` itself.
    """
    calls: list[dict] = []

    async def canned(agent, deps, question, history=None):
        calls.append({"question": question, "history": history})
        return GroundedAnswer(answer=f"A grounded reply to: {question}", enough_evidence=False), []

    monkeypatch.setattr(orchestrator, "answer_question", canned)
    return calls
