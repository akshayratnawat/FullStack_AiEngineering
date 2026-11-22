"""Writes the AI SDK's "UI message stream": Server-Sent Events carrying small JSON chunks.

One assistant message is: start, any progress parts, text-start, text-delta (many), text-end,
the data parts (citations), finish, then the literal [DONE]. The client needs the header below to recognise the format.
Verify these chunk names against the installed AI SDK version when the frontend
chat is added; they have changed between major versions.
"""

import json
from collections.abc import AsyncIterator, Awaitable, Callable

import structlog

logger = structlog.get_logger()

STREAM_HEADERS = {
    "x-vercel-ai-ui-message-stream": "v1",
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",  # stops proxies from holding chunks back
}


def sse(chunk: dict | str) -> str:
    data = chunk if isinstance(chunk, str) else json.dumps(chunk)
    return f"data: {data}\n\n"


async def ui_message_stream(
    message_id: str,
    text_chunks: AsyncIterator[str],
    on_complete: Callable[[str], Awaitable[None]],
    error_text: str = "Something went wrong. Please try again.",
    data_parts: list[dict] | None = None,
    before_text: AsyncIterator[dict] | None = None,
) -> AsyncIterator[str]:
    """Streams `text_chunks` as one assistant message.

    `data_parts` are extra parts such as `{"type": "data-citations", "data": [...]}`. The
    list is read after the last text chunk, so the caller can fill it while the text streams.

    `before_text` yields parts sent before the text starts, such as research progress while the
    answer is being prepared.

    `on_complete` gets the full text once every chunk has been sent, and runs before
    the closing `finish` event. If it fails, the client receives an error event
    instead of a message that looks saved but is not.
    """
    text_id = f"{message_id}-text"
    full_text: list[str] = []
    yield sse({"type": "start", "messageId": message_id})
    if before_text is not None:
        async for part in before_text:
            yield sse(part)
    yield sse({"type": "text-start", "id": text_id})
    async for piece in text_chunks:
        full_text.append(piece)
        yield sse({"type": "text-delta", "id": text_id, "delta": piece})
    yield sse({"type": "text-end", "id": text_id})
    for part in data_parts or []:
        yield sse(part)
    try:
        await on_complete("".join(full_text))
    except Exception:
        # The response has already started, so an HTTP error is no longer possible:
        # the stream itself has to carry the failure.
        logger.exception("chat_turn_persist_failed", message_id=message_id)
        yield sse({"type": "error", "errorText": error_text})
        yield sse("[DONE]")
        return
    yield sse({"type": "finish"})
    yield sse("[DONE]")
