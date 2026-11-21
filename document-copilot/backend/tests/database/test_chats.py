"""Tests for database/chats.py: the citation rows built for an answer and the order of the save.

A tiny fake of the Supabase client records each request, so there is no network or database.
"""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.database.chats import ChatStore, citation_rows

SOURCE = {
    "marker": 2,
    "chunk_id": str(uuid4()),
    "ticker": "AAPL",
    "section": "Item 7",
    "excerpt": "iPhone net sales were $201,183 million.",
}


class FakeClient:
    """Records `table(name).insert(rows)`, `.update(...)` and `.delete()` calls in order."""

    def __init__(self, fail_on: str | None = None) -> None:
        self.calls: list[tuple[str, str, object]] = []
        self.fail_on = fail_on
        self._pending: tuple[str, str, object] | None = None

    def table(self, name: str):
        self._table = name
        return self

    def insert(self, rows):
        self._pending = (self._table, "insert", rows)
        return self

    def update(self, changes):
        self._pending = (self._table, "update", changes)
        return self

    def delete(self):
        self._pending = (self._table, "delete", None)
        return self

    def eq(self, *args):
        return self

    def in_(self, column, values):
        self._pending = (self._pending[0], "delete", values)
        return self

    async def execute(self):
        self.calls.append(self._pending)
        if self._pending[0] == self.fail_on:
            raise RuntimeError("database is down")


def save(client: FakeClient, citations) -> None:
    store = ChatStore(client, client)
    asyncio.run(
        store.save_turn(
            thread_id=uuid4(),
            user_text="q",
            user_parts=[],
            assistant_text="a",
            assistant_parts=[],
            asked_at=datetime.now(UTC),
            set_title=None,
            citations=citations,
        )
    )


def test_a_row_is_built_per_source_with_a_snapshot_of_what_was_cited():
    message_id = uuid4()

    (row,) = citation_rows(message_id, [SOURCE])

    assert row["message_id"] == str(message_id)
    assert row["chunk_id"] == SOURCE["chunk_id"]
    assert row["citation_index"] == 2  # the [n] marker
    assert row["excerpt"] == SOURCE["excerpt"] and row["section"] == "Item 7"
    assert row["page"] is None


def test_citations_are_saved_after_the_message_they_belong_to():
    client = FakeClient()

    save(client, [SOURCE])

    assert [(table, action) for table, action, _ in client.calls] == [
        ("chat_messages", "insert"),
        ("message_citations", "insert"),
        ("chat_threads", "update"),
    ]
    assistant_id = client.calls[0][2][1]["id"]
    assert client.calls[1][2][0]["message_id"] == assistant_id


def test_an_answer_without_sources_writes_no_citation_rows():
    client = FakeClient()

    save(client, None)

    assert "message_citations" not in [table for table, _, _ in client.calls]


def test_a_failed_citation_save_removes_the_exchange_and_raises():
    client = FakeClient(fail_on="message_citations")

    with pytest.raises(RuntimeError):
        save(client, [SOURCE])

    table, action, ids = client.calls[-1]
    assert (table, action) == ("chat_messages", "delete")
    assert len(ids) == 2  # the question and the answer
    assert "chat_threads" not in [t for t, _, _ in client.calls]  # the thread was not touched
