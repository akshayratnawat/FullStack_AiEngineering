"""Tests for assistant/agent.py: the grounding contract, with a scripted fake model.

A FunctionModel stands in for the LLM and plays back a script (call a tool, then give an
answer). The retriever is faked too, so there is no network or database. What is tested is
the agent's behaviour: good answers pass, bad ones get one retry, then are rejected.
"""

import asyncio
from uuid import uuid4

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.assistant import agent as agent_module
from app.assistant import tools
from app.assistant.agent import answer_question, create_agent
from app.assistant.deps import DocumentAgentDeps
from app.retrieval.queries import ChunkHit
from app.retrieval.retriever import Passage

# --- helpers -----------------------------------------------------------------

REAL = ChunkHit(uuid4(), uuid4(), 49, "iPhone net sales were $201,183 million.", "Item 7", "AAPL", "10-K",
                2025, "2025-10-31", "acc")


@pytest.fixture(autouse=True)
def one_output_retry(monkeypatch):
    """These tests script exactly one retry; the app's default (agent_output_retries) may be higher."""
    monkeypatch.setattr(agent_module.settings, "agent_output_retries", 1)


@pytest.fixture(autouse=True)
def fake_search(monkeypatch):
    """Every search returns the one REAL chunk, whatever the query."""

    async def fake_retrieve(*args, **kwargs):
        return [Passage(hit=REAL, score=0.03, neighbors=[])]

    monkeypatch.setattr(tools, "retrieve", fake_retrieve)


def search_call() -> ToolCallPart:
    """The model asks to run search_filings."""
    return ToolCallPart(tool_name="search_filings", args={"query": "iPhone sales", "ticker": "AAPL"})


def answer_call(info: AgentInfo, text: str, enough: bool = True) -> ToolCallPart:
    """The model gives its final answer (PydanticAI exposes the output type as a tool).

    The model writes only the text, with `[S1]`-style markers, and the evidence flag: the
    program numbers the markers and builds the citation list.
    """
    args = {"answer": text, "enough_evidence": enough}
    return ToolCallPart(tool_name=info.output_tools[0].name, args=args)


class Script:
    """A fake model: each call to the model runs the next step and returns its parts."""

    def __init__(self, *steps):
        self.steps = list(steps)
        self.calls = 0
        self.seen: list[AgentInfo] = []
        self.messages: list = []

    def __call__(self, messages, info: AgentInfo) -> ModelResponse:
        self.seen.append(info)
        self.messages.append(messages)
        step = self.steps[min(self.calls, len(self.steps) - 1)]  # the last step repeats
        self.calls += 1
        return ModelResponse(parts=[step(info)])


def run(script: Script):
    """Ask one question with the scripted model and return (answer, passages)."""
    agent = create_agent(FunctionModel(script))
    deps = DocumentAgentDeps(engine=None, embedding_client=None)
    return asyncio.run(answer_question(agent, deps, "How much did iPhone sell?"))


GOOD = lambda info: answer_call(info, "iPhone sold $201B [S1].")

# --- the grounding contract --------------------------------------------------


def test_a_grounded_answer_is_returned_with_its_passages():
    """Search, then answer citing the passage that was found: accepted, with the passage attached."""
    script = Script(lambda info: search_call(), GOOD)

    answer, passages = run(script)

    assert answer.enough_evidence and answer.citations[0].source_id == "S1"
    assert answer.answer == "iPhone sold $201B [1]."  # the program numbered the marker
    assert [p.chunk_id for p in passages] == [REAL.id]
    assert passages[0].excerpt == REAL.content  # the UI shows the exact text


def test_an_honest_not_enough_evidence_answer_passes_without_searching():
    """Saying the filings don't cover it needs no citations."""
    script = Script(lambda info: answer_call(info, "The filings do not say.", enough=False))

    answer, passages = run(script)

    assert not answer.enough_evidence and passages == []


def test_an_uncited_answer_is_sent_back_once_and_then_accepted_when_fixed():
    """Claiming evidence with no citation fails; the retry message says why; the fixed answer passes."""
    script = Script(
        lambda info: search_call(),
        lambda info: answer_call(info, "iPhone sold $201B."),  # no marker: rejected
        GOOD,  # the retry cites the passage
    )

    answer, _ = run(script)

    assert script.calls == 3
    retry_text = str(script.messages[2])  # what the model saw on its retry
    assert "enough_evidence is true but there are no citations" in retry_text
    assert answer.citations[0].source_id == "S1"


def test_a_badly_formatted_answer_is_sent_back_once_and_then_accepted_when_fixed():
    """Real citations are not enough: ids in the text, bundled markers and uncited figures are retried."""
    script = Script(
        lambda info: search_call(),
        # Cites correctly, but writes the id into the text and leaves a figure paragraph uncited.
        lambda info: answer_call(info, "iPhone sold $201B [S1] (source_id S1).\n\nMac sold $30B."),
        GOOD,
    )

    answer, _ = run(script)

    assert script.calls == 3
    retry_text = str(script.messages[2])  # what the model saw on its retry
    assert "contains a chunk_id, source_id" in retry_text and "states a figure but has no citation marker" in retry_text
    assert answer.answer == "iPhone sold $201B [1]."


def test_the_program_numbers_the_markers_in_order_of_first_use():
    """The model cites S1 after S1's claim twice and never numbers anything: the app numbers [1] and [2]."""
    script = Script(
        lambda info: search_call(),
        lambda info: answer_call(info, "iPhone sold $201B [S1]. Services grew [S1]."),
    )

    answer, passages = run(script)

    assert answer.answer == "iPhone sold $201B [1]. Services grew [1]."  # the same source keeps its number
    assert [(c.marker, c.source_id) for c in answer.citations] == [(1, "S1")]
    assert len(passages) == 1


def test_a_model_that_numbers_its_own_markers_is_told_to_use_source_ids():
    """Writing [1] instead of [S1] is sent back with the instruction, then the fixed answer is accepted."""
    script = Script(
        lambda info: search_call(),
        lambda info: answer_call(info, "iPhone sold $201B [1]."),
        GOOD,
    )

    answer, _ = run(script)

    assert script.calls == 3
    assert "Write the source_id as the marker, like [S3]" in str(script.messages[2])
    assert answer.answer == "iPhone sold $201B [1]."


def test_the_model_only_ever_sees_short_source_ids_never_uuids():
    """The search result handed to the model names the passage S1; the chunk's UUID stays server-side."""
    script = Script(lambda info: search_call(), GOOD)

    run(script)

    shown_to_model = str(script.messages[1])  # the model's second turn: it contains the search result
    assert "source_id=S1" in shown_to_model and str(REAL.id) not in shown_to_model


def test_citing_a_chunk_no_tool_returned_is_rejected_after_the_retry():
    """An invented source_id fails, gets one retry, and if it persists the question is not answered."""
    invented = "S9"  # a source id no search ever showed
    script = Script(
        lambda info: search_call(),
        lambda info: answer_call(info, f"iPhone sold $201B [{invented}]."),  # repeated on retry
    )

    with pytest.raises(UnexpectedModelBehavior):
        run(script)

    assert script.calls == 3  # search, first attempt, the single retry: then it gives up


def test_an_answer_citing_nothing_it_searched_for_is_rejected():
    """Citing a source without ever searching (so nothing was retrieved) is rejected."""
    script = Script(lambda info: answer_call(info, "iPhone sold $201B [S1]."))

    with pytest.raises(UnexpectedModelBehavior):
        run(script)


# --- wiring and limits -------------------------------------------------------


def test_the_model_is_given_the_instructions_and_the_three_tools():
    """The product contract is sent as instructions, and exactly the three tools are offered."""
    script = Script(lambda info: answer_call(info, "The filings do not say.", enough=False))

    run(script)

    info = script.seen[0]
    assert "enough_evidence" in info.instructions and "investment advice" in info.instructions
    assert {t.name for t in info.function_tools} == {"search_filings", "read_chunk", "read_surrounding_chunks"}


def test_a_model_that_keeps_searching_is_stopped_by_the_tool_call_cap(monkeypatch):
    """The per-question cap on tool calls ends a looping model instead of letting it run on."""
    monkeypatch.setattr(agent_module.settings, "agent_max_tool_calls", 3)
    script = Script(lambda info: search_call())  # searches forever

    with pytest.raises(UsageLimitExceeded):
        run(script)
