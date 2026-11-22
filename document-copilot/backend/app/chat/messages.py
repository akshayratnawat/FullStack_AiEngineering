"""Converts between the AI SDK's message format and what we store and return.

An AI SDK "UI message" looks like
`{"id": "...", "role": "user", "parts": [{"type": "text", "text": "Hello"}]}`.
Assistant messages have a text part, plus a `data-citations` part when the answer cites sources.
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from app.assistant.outputs import GroundedAnswer, SourcePassage

TITLE_MAX_CHARS = 60
# Marks an assistant message that is only an explanation of why no answer was given. The UI
# ignores unknown "data-" parts; we use it to keep such exchanges out of the agent's history.
FAILED_PART_TYPE = "data-turn-failed"
# Carries the sources behind an answer's [n] markers; streamed after the text and saved with it.
CITATIONS_PART_TYPE = "data-citations"
# The research steps (searches, reads, checks) shown while the answer is prepared. Sent again,
# with the same id, after each step, and the SDK replaces the part in place; saved with the reply.
PROGRESS_PART_TYPE = "data-progress"
# Marks a reply that replays a recorded example instead of a new answer; saved with the reply.
DEMO_PART_TYPE = "data-demo"
PROGRESS_PART_ID = "progress"


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


def progress_part(steps: list[str], done: bool) -> dict:
    return {"type": PROGRESS_PART_TYPE, "id": PROGRESS_PART_ID, "data": {"steps": steps, "done": done}}


def demo_parts(citations: list[dict], recorded_at: str, model: str) -> list[dict]:
    """The parts of a replayed recording: its sources (when it has any) and the recorded-example mark."""
    parts = [{"type": CITATIONS_PART_TYPE, "data": citations}] if citations else []
    return [*parts, {"type": DEMO_PART_TYPE, "data": {"recorded_at": recorded_at, "model": model}}]


def citation_parts(answer: GroundedAnswer, passages: list[SourcePassage]) -> list[dict]:
    """The data part that carries an answer's sources, or nothing when it cites none.

    `passages` come from `validate()` in marker order, so they pair up with the citations
    sorted by marker. Each entry is the passage plus the [n] marker it belongs to.
    """
    if not passages:
        return []
    markers = sorted(citation.marker for citation in answer.citations)
    sources = [{"marker": marker, **passage.model_dump(mode="json")} for marker, passage in zip(markers, passages)]
    return [{"type": CITATIONS_PART_TYPE, "data": sources}]


def failed_parts(text: str) -> list[dict]:
    """Parts for an assistant message that explains why no answer was given."""
    return [*text_parts(text), {"type": FAILED_PART_TYPE, "data": {}}]


def to_model_history(rows: list[dict], limit: int) -> list[ModelMessage]:
    """The thread's earlier messages as the agent's conversation history.

    `rows` are stored chat_messages in order, oldest first. Only the last `limit` are used.
    Rules, so the agent sees a clean alternating conversation:
    - a failed exchange (a question and its "could not answer" reply) is dropped as a pair;
    - the history starts with a user message and ends with an assistant message.
    Answers come back as plain text: they carry no chunk ids, so they can be read for
    context but never cited. The agent has to search again for anything it wants to cite.
    """
    kept: list[tuple[str, str]] = []  # (role, text)
    for row in rows:
        failed = any(part.get("type") == FAILED_PART_TYPE for part in row["parts"] or [])
        if row["role"] == "assistant" and failed:
            if kept and kept[-1][0] == "user":
                kept.pop()  # drop the question this failed reply answered
            continue
        kept.append((row["role"], row["content"] or message_text(row["parts"] or [])))

    kept = kept[-limit:] if limit > 0 else []
    while kept and kept[0][0] != "user":
        kept.pop(0)
    while kept and kept[-1][0] != "assistant":
        kept.pop()

    return [
        ModelRequest(parts=[UserPromptPart(content=text)])
        if role == "user"
        else ModelResponse(parts=[TextPart(content=text)])
        for role, text in kept
    ]


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
