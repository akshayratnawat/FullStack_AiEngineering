"""Tests for assistant/agent.py: the grounding contract, with a scripted fake model.

A FunctionModel stands in for the LLM and plays back a script (call a tool, then give an
answer). The retriever is faked too, so there is no network or database. What is tested is
the agent's behaviour: good answers pass, bad ones are sent back, then rejected.

The model's answer is a list of claims; the program joins them and places the markers.
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


def fact(text: str, *sources: str) -> dict:
    return {"kind": "fact", "text": text, "sources": list(sources)}


def note(text: str) -> dict:
    return {"kind": "note", "text": text, "sources": []}


def answer_call(info: AgentInfo, claims: list[dict], enough: bool = True) -> ToolCallPart:
    """The model gives its final answer (PydanticAI exposes the output type as a tool).

    The model returns only claims and the evidence flag: the program joins the claims, numbers
    the sources and places the markers.
    """
    args = {"claims": claims, "enough_evidence": enough}
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


GOOD = lambda info: answer_call(info, [fact("iPhone net sales were $201,183 million.", "S1")])

# --- the grounding contract --------------------------------------------------


def test_a_grounded_answer_is_returned_with_its_marker_right_after_the_claim():
    """Search, then answer with a claim citing the passage that was found: accepted, marker in place."""
    script = Script(lambda info: search_call(), GOOD)

    answer, passages = run(script)

    assert answer.enough_evidence and answer.citations[0].source_id == "S1"
    assert answer.answer == "iPhone net sales were $201,183 million[1]."  # the program placed the marker
    assert [p.chunk_id for p in passages] == [REAL.id]
    assert passages[0].excerpt == REAL.content  # the UI shows the exact text


def test_an_honest_not_enough_evidence_answer_passes_without_searching():
    """Saying the filings don't cover it needs no sources."""
    script = Script(lambda info: answer_call(info, [note("The filings do not say.")], enough=False))

    answer, passages = run(script)

    assert not answer.enough_evidence and passages == []
    assert answer.answer == "The filings do not say."


def test_a_fact_without_a_source_is_sent_back_once_and_then_accepted_when_fixed():
    """A claim with no source fails; the retry message says which claim; the fixed answer passes."""
    script = Script(
        lambda info: search_call(),
        lambda info: answer_call(info, [fact("iPhone net sales were $201,183 million.")]),  # no source: rejected
        GOOD,  # the retry cites the passage
    )

    answer, _ = run(script)

    assert script.calls == 3
    retry_text = str(script.messages[2])  # what the model saw on its retry
    assert "has no sources" in retry_text and "iPhone net sales were" in retry_text
    assert answer.citations[0].source_id == "S1"


def test_a_figure_the_cited_passage_does_not_contain_is_sent_back_then_accepted_when_fixed():
    """The correctness check end to end: a mis-copied figure is rejected and the retry says why."""
    script = Script(
        lambda info: search_call(),
        lambda info: answer_call(info, [fact("iPhone net sales were $210,000 million.", "S1")]),
        GOOD,
    )

    answer, _ = run(script)

    assert script.calls == 3
    assert "none of its cited passages" in str(script.messages[2]) and "$210,000 million" in str(script.messages[2])
    assert answer.answer == "iPhone net sales were $201,183 million[1]."


def test_the_model_only_ever_sees_short_source_ids_never_uuids():
    """The search result handed to the model names the passage S1; the chunk's UUID stays server-side."""
    script = Script(lambda info: search_call(), GOOD)

    run(script)

    shown_to_model = str(script.messages[1])  # the model's second turn: it contains the search result
    assert "source_id=S1" in shown_to_model and str(REAL.id) not in shown_to_model


def test_citing_a_source_no_tool_returned_is_rejected_after_the_retry():
    """An invented source_id fails, gets one retry, and if it persists the question is not answered."""
    script = Script(
        lambda info: search_call(),
        lambda info: answer_call(info, [fact("iPhone net sales were $201,183 million.", "S9")]),  # repeated on retry
    )

    with pytest.raises(UnexpectedModelBehavior):
        run(script)

    assert script.calls == 3  # search, first attempt, the single retry: then it gives up


def test_an_answer_citing_nothing_it_searched_for_is_rejected():
    """Citing a source without ever searching (so nothing was retrieved) is rejected."""
    script = Script(lambda info: answer_call(info, [fact("iPhone net sales were $201,183 million.", "S1")]))

    with pytest.raises(UnexpectedModelBehavior):
        run(script)


# --- wiring and limits -------------------------------------------------------


def test_the_model_is_given_the_instructions_and_the_three_tools():
    """The product contract is sent as instructions, and exactly the three tools are offered."""
    script = Script(lambda info: answer_call(info, [note("The filings do not say.")], enough=False))

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
