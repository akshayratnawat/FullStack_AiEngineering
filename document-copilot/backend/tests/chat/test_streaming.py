import asyncio
import json

from app.chat.streaming import ui_message_stream


async def pieces(*texts: str):
    for text in texts:
        yield text


def collect(*texts: str, on_complete) -> list[str]:
    async def run() -> list[str]:
        return [e async for e in ui_message_stream("m1", pieces(*texts), on_complete)]

    return asyncio.run(run())


def parse(events: list[str]) -> list[dict | str]:
    out = []
    for event in events:
        assert event.startswith("data: ")
        assert event.endswith("\n\n")
        payload = event[len("data: ") : -2]
        out.append(payload if payload == "[DONE]" else json.loads(payload))
    return out


def test_one_message_is_start_text_finish_done_in_order():
    async def on_complete(_: str) -> None: ...

    result = parse(collect("Hel", "lo", on_complete=on_complete))

    assert result == [
        {"type": "start", "messageId": "m1"},
        {"type": "text-start", "id": "m1-text"},
        {"type": "text-delta", "id": "m1-text", "delta": "Hel"},
        {"type": "text-delta", "id": "m1-text", "delta": "lo"},
        {"type": "text-end", "id": "m1-text"},
        {"type": "finish"},
        "[DONE]",
    ]


def test_data_parts_are_sent_after_the_text_and_before_the_save_and_finish():
    order: list[str] = []
    parts = [{"type": "data-citations", "data": [{"marker": 1}]}]

    async def on_complete(_: str) -> None:
        order.append("saved")

    async def run() -> None:
        async for event in ui_message_stream("m1", pieces("a"), on_complete, data_parts=parts):
            chunk = parse([event])[0]
            order.append(chunk["type"] if isinstance(chunk, dict) else "done")

    asyncio.run(run())

    assert order == ["start", "text-start", "text-delta", "text-end", "data-citations", "saved", "finish", "done"]


def test_on_complete_gets_the_full_text_after_the_last_delta_and_before_finish():
    order: list[str] = []

    async def on_complete(text: str) -> None:
        order.append(f"saved:{text}")

    async def run() -> None:
        async for event in ui_message_stream("m1", pieces("a", "b"), on_complete):
            chunk = parse([event])[0]
            order.append(chunk["type"] if isinstance(chunk, dict) else "done")

    asyncio.run(run())

    assert order == [
        "start",
        "text-start",
        "text-delta",
        "text-delta",
        "text-end",
        "saved:ab",
        "finish",
        "done",
    ]


def test_a_failed_save_sends_an_error_event_and_no_finish():
    async def on_complete(_: str) -> None:
        raise RuntimeError("database is down")

    result = parse(collect("hi", on_complete=on_complete))

    types = [c["type"] if isinstance(c, dict) else c for c in result]
    assert types[-2:] == ["error", "[DONE]"]
    assert "finish" not in types
    assert "database is down" not in json.dumps(result)  # internals stay out of the stream
