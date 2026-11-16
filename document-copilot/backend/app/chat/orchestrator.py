"""Runs one chat turn: the user asks, the assistant answers, the exchange is saved.

The assistant is a stub for now. Phase 6 replaces `stub_reply` with retrieval and
the PydanticAI agent; the stream and the saving around it stay as they are.
"""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.chat.messages import text_parts, title_from
from app.chat.streaming import ui_message_stream
from app.database.chats import ChatStore

STUB_WORD_DELAY_SECONDS = 0.04


async def stub_reply(user_text: str) -> AsyncIterator[str]:
    """A canned answer, a word at a time, so the UI has something to stream."""
    reply = (
        "This is a placeholder reply. Document search is not connected yet, "
        f"so I cannot answer from filings. You asked: {user_text}"
    )
    words = reply.split(" ")
    for index, word in enumerate(words):
        await asyncio.sleep(STUB_WORD_DELAY_SECONDS)
        yield word if index == len(words) - 1 else word + " "


async def run_turn(store: ChatStore, thread_id: UUID, user_text: str) -> AsyncIterator[str]:
    """The SSE events for one turn. The caller has already checked the thread is the user's."""
    asked_at = datetime.now(UTC)
    # A thread with no title yet is a new one: name it after its first question.
    title = None
    if await store.get_thread_title(thread_id) is None:
        title = title_from(user_text)

    async def save(answer: str) -> None:
        await store.save_turn(
            thread_id=thread_id,
            user_text=user_text,
            user_parts=text_parts(user_text),
            assistant_text=answer,
            assistant_parts=text_parts(answer),
            asked_at=asked_at,
            set_title=title,
        )

    async for event in ui_message_stream(
        message_id=str(uuid4()),
        text_chunks=stub_reply(user_text),
        on_complete=save,
    ):
        yield event
