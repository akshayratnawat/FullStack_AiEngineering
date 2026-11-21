"""Tests for chat/orchestrator.py: what one turn streams, saves and sends the agent.

The agent run is replaced (see `canned_agent` in conftest), so there is no model, database
or network. Tests that need a failure patch `orchestrator.answer_question` themselves.
"""

import asyncio
import json
from uuid import uuid4

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded

from app.assistant.deps import DocumentAgentDeps
from app.assistant.outputs import Citation, GroundedAnswer, SourcePassage
from app.chat import orchestrator
from app.chat.messages import (
    CITATIONS_PART_TYPE,
    FAILED_PART_TYPE,
    PROGRESS_PART_TYPE,
    to_ui_message,
)
from app.chat.orchestrator import run_turn
from app.retrieval.queries import ChunkHit
from tests.conftest import ALICE

# --- helpers -----------------------------------------------------------------


def new_deps() -> DocumentAgentDeps:
    # The agent call is faked, so the engine and client are never used.
    return DocumentAgentDeps(engine=object(), embedding_client=object())


def run(store, thread_id, text) -> list[str]:
    """All the SSE events one turn produces."""

    async def go() -> list[str]:
        return [e async for e in run_turn(store, thread_id, text, agent=None, deps=new_deps())]

    return asyncio.run(go())


def streamed_text(events: list[str]) -> str:
    """The answer text reassembled from the stream's text-delta events."""
    chunks = [json.loads(e[len("data: ") : -2]) for e in events if '"text-delta"' in e]
    return "".join(c["delta"] for c in chunks)


def event_types(events: list[str]) -> list[str]:
    """The `type` of each JSON event, in order (the closing [DONE] is not JSON)."""
    return [json.loads(e[len("data: ") : -2])["type"] for e in events if e != "data: [DONE]\n\n"]


def raising(error: Exception):
    """An agent run that fails with `error`."""

    async def fail(agent, deps, question, history=None):
        raise error

    return fail


# --- an answered turn --------------------------------------------------------


def test_a_turn_saves_the_question_and_the_streamed_answer_once(store):
    """The saved answer is exactly what was streamed, as plain text parts."""
    thread_id = store.add_thread(ALICE)

    events = run(store, thread_id, "What was Apple's revenue?")

    assert len(store.saved_turns) == 1
    turn = store.saved_turns[0]
    assert turn["thread_id"] == thread_id
    assert turn["user_text"] == "What was Apple's revenue?"
    assert turn["assistant_text"] == streamed_text(events) == "A grounded reply to: What was Apple's revenue?"
    assert turn["assistant_parts"] == [{"type": "text", "text": turn["assistant_text"]}]


def test_only_a_threads_first_question_names_it(store):
    """A thread with no title is named after its first question; an existing title is kept."""
    new_thread = store.add_thread(ALICE)
    named_thread = store.add_thread(ALICE, title="Existing title")

    run(store, new_thread, "What was Apple's revenue?")
    run(store, named_thread, "Another question")

    assert store.saved_turns[0]["set_title"] == "What was Apple's revenue?"
    assert store.saved_turns[1]["set_title"] is None


def test_nothing_is_saved_when_the_client_disconnects_mid_stream(store):
    """If the browser goes away before the answer finishes, no half answer is stored."""
    thread_id = store.add_thread(ALICE)

    async def go() -> None:
        stream = run_turn(store, thread_id, "hello", agent=None, deps=new_deps())
        await anext(stream)  # the client reads one event, then goes away
        await stream.aclose()

    asyncio.run(go())

    assert store.saved_turns == []


# --- citations ---------------------------------------------------------------

CHUNK = ChunkHit(uuid4(), uuid4(), 3, "iPhone net sales were $201,183 million.", "Item 7", "AAPL", "10-K", 2025,
                 "2025-10-31", "0000320193-25-000079")


def cited_answer(monkeypatch) -> None:
    """Make the agent return an answer that cites CHUNK as [1]."""

    async def answer(agent, deps, question, history=None):
        grounded = GroundedAnswer(
            answer="iPhone sold $201B [1].", citations=[Citation(marker=1, source_id="S1")], enough_evidence=True
        )
        return grounded, [SourcePassage.from_hit(CHUNK)]

    monkeypatch.setattr(orchestrator, "answer_question", answer)


def test_a_cited_answer_streams_its_sources_after_the_text_and_before_finish(monkeypatch, store):
    """The citations part arrives once the text is complete, carrying the marker and the exact excerpt."""
    cited_answer(monkeypatch)

    events = run(store, store.add_thread(ALICE), "iPhone sales?")

    types = event_types(events)
    assert types.index("text-end") < types.index("data-citations") < types.index("finish")
    part = next(json.loads(e[len("data: ") : -2]) for e in events if '"data-citations"' in e)
    (source,) = part["data"]
    assert source["marker"] == 1 and source["chunk_id"] == str(CHUNK.id)
    assert source["ticker"] == "AAPL" and source["excerpt"] == CHUNK.content


def test_the_sources_are_saved_with_the_answer(monkeypatch, store):
    """What the user saw is what is stored: the text part, then the same citations part."""
    cited_answer(monkeypatch)

    events = run(store, store.add_thread(ALICE), "iPhone sales?")

    (turn,) = store.saved_turns
    text_part, citations_part = turn["assistant_parts"]
    assert text_part == {"type": "text", "text": "iPhone sold $201B [1]."}
    assert citations_part["type"] == CITATIONS_PART_TYPE
    streamed = next(json.loads(e[len("data: ") : -2]) for e in events if '"data-citations"' in e)
    assert citations_part == streamed


def test_an_answer_without_sources_sends_no_citations_part(store):
    """The canned 'not enough evidence' answer cites nothing, so no empty citations part is sent or saved."""
    events = run(store, store.add_thread(ALICE), "unknown")

    assert "data-citations" not in event_types(events)
    assert [p["type"] for p in store.saved_turns[0]["assistant_parts"]] == ["text"]


def test_no_sources_are_sent_when_the_answer_could_not_be_given(monkeypatch, store):
    """A grounding failure sends no unsupported answer and no sources."""
    monkeypatch.setattr(orchestrator, "answer_question", raising(UnexpectedModelBehavior("bad")))

    events = run(store, store.add_thread(ALICE), "A hard question")

    assert "data-citations" not in event_types(events)


# --- conversation history ----------------------------------------------------


def test_earlier_messages_are_given_to_the_agent_as_history(store, canned_agent):
    """A follow-up question reaches the agent together with the thread's earlier exchange."""
    thread_id = store.add_thread(ALICE)
    store.messages[thread_id] = [
        {"id": "1", "role": "user", "content": "Apple revenue in 2024?", "parts": None},
        {"id": "2", "role": "assistant", "content": "It was $391B.", "parts": None},
    ]

    run(store, thread_id, "and in 2023?")

    (call,) = canned_agent
    assert call["question"] == "and in 2023?"  # the new question is the prompt, not part of the history
    assert [type(m).__name__ for m in call["history"]] == ["ModelRequest", "ModelResponse"]
    assert "Apple revenue in 2024?" in str(call["history"][0])


def test_a_new_thread_has_no_history(store, canned_agent):
    """The first question of a thread is asked with an empty history."""
    run(store, store.add_thread(ALICE), "first question")

    assert canned_agent[0]["history"] == []


# --- when no answer can be given ---------------------------------------------


@pytest.mark.parametrize(
    ("error", "expected_text"),
    [
        (UnexpectedModelBehavior("grounding failed twice"), orchestrator.CANNOT_ANSWER_TEXT),
        (UsageLimitExceeded("too many tool calls"), orchestrator.TOO_BROAD_TEXT),
    ],
)
def test_a_question_that_cannot_be_answered_is_kept_with_an_explanation(monkeypatch, store, error, expected_text):
    """Grounding failure or hitting a cap: the explanation is streamed and saved, flagged as a failure."""
    monkeypatch.setattr(orchestrator, "answer_question", raising(error))
    thread_id = store.add_thread(ALICE)

    events = run(store, thread_id, "A hard question")

    assert streamed_text(events) == expected_text
    assert "error" not in event_types(events) and event_types(events)[-1] == "finish"
    (turn,) = store.saved_turns
    assert turn["user_text"] == "A hard question"  # the question is not lost
    assert turn["assistant_text"] == expected_text
    assert {"type": FAILED_PART_TYPE, "data": {}} in turn["assistant_parts"]


def test_a_service_failure_sends_an_error_and_saves_nothing(monkeypatch, store):
    """Model or database down: not the question's fault, so show an error and let the user retry."""
    monkeypatch.setattr(orchestrator, "answer_question", raising(RuntimeError("azure is down")))
    thread_id = store.add_thread(ALICE)

    events = run(store, thread_id, "Any question")

    assert "error" in event_types(events)
    assert events[-1] == "data: [DONE]\n\n"
    assert store.saved_turns == []


def test_the_sources_reach_the_store_and_survive_a_reload(monkeypatch, store):
    """Save, then reload the thread as the API does: the answer still carries its sources."""
    cited_answer(monkeypatch)
    thread_id = store.add_thread(ALICE)

    run(store, thread_id, "iPhone sales?")

    (turn,) = store.saved_turns
    assert [c["marker"] for c in turn["citations"]] == [1]  # the rows to insert
    reloaded = [to_ui_message(row) for row in asyncio.run(store.list_messages(thread_id))]
    assert [m["role"] for m in reloaded] == ["user", "assistant"]
    citations_part = next(p for p in reloaded[1]["parts"] if p["type"] == CITATIONS_PART_TYPE)
    assert citations_part["data"][0]["excerpt"] == CHUNK.content


# --- research progress -------------------------------------------------------


DONE_EVENT = "data: [DONE]\n\n"


def events_of(events: list[str]) -> list[dict]:
    return [json.loads(e[len("data: ") : -2]) for e in events if e != DONE_EVENT]


def researching(monkeypatch, steps: list[str]) -> None:
    """An agent run that reports `steps` (as the tools do), then answers."""

    async def answer(agent, deps, question, history=None):
        for step in steps:
            deps.report(step)
            await asyncio.sleep(0)  # let the stream send it, as a real tool call would
        return GroundedAnswer(answer="An answer.", enough_evidence=False), []

    monkeypatch.setattr(orchestrator, "answer_question", answer)


def test_each_research_step_is_streamed_before_the_text(monkeypatch, store):
    researching(monkeypatch, ["Searching AAPL FY2024: iPhone net sales", "Checking every claim"])
    thread_id = store.add_thread(ALICE)

    events = events_of(run(store, thread_id, "iPhone sales?"))

    progress = [e for e in events if e["type"] == PROGRESS_PART_TYPE]
    # The first step goes out on its own while the agent works; the last part is the finished
    # list. (A step reported as the agent finishes may only arrive in that last part.) All share
    # one id, so the UI replaces the part in place instead of adding a new one each time.
    assert progress[0]["data"] == {"steps": ["Searching AAPL FY2024: iPhone net sales"], "done": False}
    assert progress[-1]["data"] == {
        "steps": ["Searching AAPL FY2024: iPhone net sales", "Checking every claim"],
        "done": True,
    }
    assert all(not p["data"]["done"] for p in progress[:-1])
    assert len({p["id"] for p in progress}) == 1
    types = [e["type"] for e in events]
    last_progress = len(types) - 1 - types[::-1].index(PROGRESS_PART_TYPE)
    assert types.index("start") < types.index(PROGRESS_PART_TYPE) and last_progress < types.index("text-start")


def test_the_research_steps_are_saved_with_the_answer(monkeypatch, store):
    researching(monkeypatch, ["Searching all filings: capex"])
    thread_id = store.add_thread(ALICE)

    run(store, thread_id, "Capex?")

    parts = store.saved_turns[0]["assistant_parts"]
    assert parts[0] == {
        "type": PROGRESS_PART_TYPE,
        "id": "progress",
        "data": {"steps": ["Searching all filings: capex"], "done": True},
    }
    assert parts[1] == {"type": "text", "text": "An answer."}


def test_the_research_steps_are_kept_when_no_answer_could_be_given(monkeypatch, store):
    async def answer(agent, deps, question, history=None):
        deps.report("Searching NVDA: data center demand")
        raise UnexpectedModelBehavior("no grounded answer")

    monkeypatch.setattr(orchestrator, "answer_question", answer)
    thread_id = store.add_thread(ALICE)

    run(store, thread_id, "NVIDIA demand?")

    types = [part["type"] for part in store.saved_turns[0]["assistant_parts"]]
    assert types == [PROGRESS_PART_TYPE, "text", FAILED_PART_TYPE]


def test_a_turn_without_research_steps_saves_no_progress_part(store):
    thread_id = store.add_thread(ALICE)

    run(store, thread_id, "hello")  # the canned agent reports nothing

    types = [part["type"] for part in store.saved_turns[0]["assistant_parts"]]
    assert PROGRESS_PART_TYPE not in types


def test_the_agent_is_stopped_when_the_client_disconnects(monkeypatch, store):
    started, stopped = asyncio.Event(), []

    async def slow(agent, deps, question, history=None):
        deps.report("Searching all filings: anything")
        started.set()
        try:
            await asyncio.sleep(60)  # a long model call
        except asyncio.CancelledError:
            stopped.append(True)
            raise

    monkeypatch.setattr(orchestrator, "answer_question", slow)
    thread_id = store.add_thread(ALICE)

    async def go() -> None:
        stream = run_turn(store, thread_id, "hello", agent=None, deps=new_deps())
        await anext(stream)  # start
        await anext(stream)  # the first progress step
        await stream.aclose()  # the browser goes away
        await asyncio.sleep(0)

    asyncio.run(go())

    assert stopped == [True]  # no tokens spent on a reply nobody reads
    assert store.saved_turns == []
