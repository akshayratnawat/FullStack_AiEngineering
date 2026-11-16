"""Converts between the AI SDK's message format and what we store and return.

An AI SDK "UI message" looks like
`{"id": "...", "role": "user", "parts": [{"type": "text", "text": "Hello"}]}`.
Only text parts exist so far; citation parts arrive with retrieval.
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

TITLE_MAX_CHARS = 60


class UiMessage(BaseModel):
    # The SDK adds fields we do not use (metadata, ...): ignore them rather than fail.
    model_config = ConfigDict(extra="ignore")

    role: Literal["user", "assistant", "system"]
    parts: list[dict] = Field(default_factory=list)


class ChatStreamRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    thread_id: UUID = Field(alias="threadId")
    messages: list[UiMessage] = Field(min_length=1)


def text_parts(text: str) -> list[dict]:
    return [{"type": "text", "text": text}]


def message_text(parts: list[dict]) -> str:
    return "".join(p.get("text", "") for p in parts if p.get("type") == "text")


def new_user_text(messages: list[UiMessage]) -> str:
    """The text of the question being asked now: the last message, which must be the user's.

    The SDK resends the whole conversation on every request. We keep only the last
    message, because earlier ones are already stored (and stored copies are the ones
    that can be trusted). Raises ValueError if it is not a non-empty user message.
    """
    last = messages[-1]
    text = message_text(last.parts).strip()
    if last.role != "user" or not text:
        raise ValueError("The last message must be a non-empty user message.")
    return text


def title_from(text: str) -> str:
    return text if len(text) <= TITLE_MAX_CHARS else text[: TITLE_MAX_CHARS - 1].rstrip() + "…"


def to_ui_message(row: dict) -> dict:
    """A stored chat_messages row, shaped for the SDK's `initialMessages`."""
    return {
        "id": row["id"],
        "role": row["role"],
        "parts": row["parts"] or text_parts(row["content"]),
    }
