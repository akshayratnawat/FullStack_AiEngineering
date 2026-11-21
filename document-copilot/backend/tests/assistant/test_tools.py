"""Tests for assistant/tools.py: what each tool asks for, shows, and records.

The retriever and database queries are replaced with fakes, so there is no database,
model or network. Tools only use `ctx.deps`, so a tiny stand-in for the run context is enough.
"""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic_ai import ModelRetry, Tool

from app.assistant import tools
from app.assistant.deps import DocumentAgentDeps
from app.retrieval.queries import ChunkHit
from app.retrieval.retriever import Passage

# --- helpers -----------------------------------------------------------------

DOC = uuid4()


def chunk(index: int, document_id=DOC) -> ChunkHit:
    """A fake chunk at position `index` of a document."""
    return ChunkHit(uuid4(), document_id, index, f"text {index}", "Item 7", "AAPL", "10-K", 2025,
                    "2025-10-31", "acc")


def make_ctx() -> SimpleNamespace:
    """Stand-in for PydanticAI's run context: tools only read `.deps` from it."""
    return SimpleNamespace(deps=DocumentAgentDeps(engine="engine", embedding_client="client"))


def run(coroutine):
    return asyncio.run(coroutine)


# --- search_filings ----------------------------------------------------------


def test_search_passes_the_filters_and_asks_for_no_neighbours(monkeypatch):
    """Ticker and year reach retrieve(); neighbours are off so the reply stays small."""
    seen = {}

    async def fake_retrieve(engine, client, query, **kwargs):
        seen.update(engine=engine, client=client, query=query, **kwargs)
        return []

    monkeypatch.setattr(tools, "retrieve", fake_retrieve)

    run(tools.search_filings(make_ctx(), "iPhone sales", ticker="AAPL", fiscal_year=2024))

    assert seen == {"engine": "engine", "client": "client", "query": "iPhone sales",
                    "ticker": "AAPL", "fiscal_year": 2024, "neighbor_window": 0}


def test_search_records_every_returned_chunk_and_shows_its_id(monkeypatch):
    """Returned chunks land in deps.retrieved (so they can be cited) and the reply carries their ids."""
    hits = [chunk(3), chunk(7)]

    async def fake_retrieve(*args, **kwargs):
        return [Passage(hit=h, score=0.03, neighbors=[]) for h in hits]

    monkeypatch.setattr(tools, "retrieve", fake_retrieve)
    ctx = make_ctx()

    reply = run(tools.search_filings(ctx, "anything"))

    assert set(ctx.deps.retrieved) == {h.id for h in hits}
    assert "[source_id=S1]" in reply and "[source_id=S2]" in reply
    assert not any(str(h.id) in reply for h in hits)  # the model never sees the UUIDs
    assert "AAPL 10-K fiscal 2025" in reply and "text 3" in reply


def test_search_with_no_results_says_so_and_records_nothing(monkeypatch):
    """An empty search tells the model how to retry and leaves nothing citable."""

    async def fake_retrieve(*args, **kwargs):
        return []

    monkeypatch.setattr(tools, "retrieve", fake_retrieve)
    ctx = make_ctx()

    assert "No passages found" in run(tools.search_filings(ctx, "nothing"))
    assert ctx.deps.retrieved == {}


# --- read_chunk --------------------------------------------------------------


def test_read_chunk_returns_and_records_the_chunk(monkeypatch):
    """A known chunk id returns that passage and records it."""
    target = chunk(5)

    async def fake_get(engine, chunk_id):
        return target

    monkeypatch.setattr(tools.queries, "get_chunk_by_id", fake_get)
    ctx = make_ctx()
    ctx.deps.labels[target.id] = "S4"  # the model saw this passage as S4 in an earlier search

    reply = run(tools.read_chunk(ctx, "S4"))

    assert "[source_id=S4]" in reply and "text 5" in reply
    assert ctx.deps.retrieved == {target.id: target}


@pytest.mark.parametrize("tool", [tools.read_chunk, tools.read_surrounding_chunks])
def test_an_unknown_source_id_sends_the_model_back_to_retry(monkeypatch, tool):
    """An id that matches nothing raises ModelRetry (the model is told to use an id from a search)."""

    async def fake_get(engine, chunk_id):
        raise AssertionError("the database must not be asked about an id the model made up")

    monkeypatch.setattr(tools.queries, "get_chunk_by_id", fake_get)
    ctx = make_ctx()

    with pytest.raises(ModelRetry, match="Use a source_id from a search result"):
        run(tool(ctx, "S9"))
    assert ctx.deps.retrieved == {}


# --- read_surrounding_chunks -------------------------------------------------


def test_surrounding_chunks_come_back_in_reading_order_and_are_recorded(monkeypatch):
    """The centre chunk plus `window` chunks each side, sorted by position, all recorded."""
    around = [chunk(i) for i in (4, 5, 6, 7, 8)]
    centre = around[2]  # chunk 6
    asked = {}

    async def fake_get(engine, chunk_id):
        return centre

    async def fake_get_chunks(engine, wanted):
        asked["wanted"] = wanted
        return list(reversed(around))  # deliberately out of order

    monkeypatch.setattr(tools.queries, "get_chunk_by_id", fake_get)
    monkeypatch.setattr(tools.queries, "get_chunks", fake_get_chunks)
    ctx = make_ctx()
    ctx.deps.labels[centre.id] = "S1"

    reply = run(tools.read_surrounding_chunks(ctx, "S1", window=2))

    assert {index for _, index in asked["wanted"]} == {4, 5, 6, 7, 8}
    assert reply.index("text 4") < reply.index("text 6") < reply.index("text 8")
    assert set(ctx.deps.retrieved) == {c.id for c in around}


def test_surrounding_chunks_never_ask_for_a_negative_position(monkeypatch):
    """Near the start of a document the range is clamped at chunk 0."""
    centre = chunk(1)
    asked = {}

    async def fake_get(engine, chunk_id):
        return centre

    async def fake_get_chunks(engine, wanted):
        asked["wanted"] = wanted
        return [centre]

    monkeypatch.setattr(tools.queries, "get_chunk_by_id", fake_get)
    monkeypatch.setattr(tools.queries, "get_chunks", fake_get_chunks)

    ctx = make_ctx()
    ctx.deps.labels[centre.id] = "S1"

    run(tools.read_surrounding_chunks(ctx, "S1", window=3))

    assert min(index for _, index in asked["wanted"]) == 0


# --- what the model is shown -------------------------------------------------


def test_the_model_can_only_name_the_eight_companies():
    """The schema the model sees lists exactly the 8 tickers, so any other value is rejected up front."""
    schema = Tool(tools.search_filings).function_schema.json_schema
    options = next(o for o in schema["properties"]["ticker"]["anyOf"] if "enum" in o)
    assert options["enum"] == ["AAPL", "AMZN", "GOOGL", "JPM", "META", "MSFT", "NVDA", "TSLA"]


def test_the_run_context_is_hidden_from_the_model_and_window_is_bounded():
    """Only real arguments appear in the schema, and the window is capped at 3."""
    search = Tool(tools.search_filings).function_schema.json_schema
    assert set(search["properties"]) == {"query", "ticker", "fiscal_year"}

    around = Tool(tools.read_surrounding_chunks).function_schema.json_schema
    window = around["properties"]["window"]
    assert (window["minimum"], window["maximum"]) == (1, 3)
