import asyncio
import json

from app.chat.orchestrator import run_turn
from tests.conftest import ALICE


def run(store, thread_id, text) -> list[str]:
    async def go() -> list[str]:
        return [e async for e in run_turn(store, thread_id, text)]

    return asyncio.run(go())


def streamed_text(events: list[str]) -> str:
    chunks = [json.loads(e[len("data: ") : -2]) for e in events if '"text-delta"' in e]
    return "".join(c["delta"] for c in chunks)


def test_a_turn_saves_the_question_and_the_streamed_answer_once(store):
    thread_id = store.add_thread(ALICE)

    events = run(store, thread_id, "What was Apple's revenue?")

    assert len(store.saved_turns) == 1
    turn = store.saved_turns[0]
    assert turn["thread_id"] == thread_id
    assert turn["user_text"] == "What was Apple's revenue?"
    assert turn["assistant_text"] == streamed_text(events)  # saved exactly what was sent
    assert turn["assistant_parts"] == [{"type": "text", "text": turn["assistant_text"]}]


def test_only_a_threads_first_question_names_it(store):
    new_thread = store.add_thread(ALICE)
    named_thread = store.add_thread(ALICE, title="Existing title")

    run(store, new_thread, "What was Apple's revenue?")
    run(store, named_thread, "Another question")

    assert store.saved_turns[0]["set_title"] == "What was Apple's revenue?"
    assert store.saved_turns[1]["set_title"] is None


def test_nothing_is_saved_when_the_client_disconnects_mid_stream(store):
    thread_id = store.add_thread(ALICE)

    async def go() -> None:
        stream = run_turn(store, thread_id, "hello")
        await anext(stream)  # the client reads one event, then goes away
        await stream.aclose()

    asyncio.run(go())

    assert store.saved_turns == []
