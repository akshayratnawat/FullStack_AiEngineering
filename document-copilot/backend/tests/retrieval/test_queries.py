"""Query assembly: check the SQL each search builds, without a database.

A fake session records the statement it is asked to run; we compile it to PostgreSQL
text and look for the parts that make the search correct.
"""

import asyncio
import uuid
from typing import ClassVar

import pytest
from sqlalchemy.dialects import postgresql

from app.retrieval import queries


class FakeSession:
    """Stands in for a database session: records each statement it is asked to run and returns no rows."""

    executed: ClassVar[list] = []  # shared on purpose: the code under test creates its own session

    def __init__(self, engine):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, statement):
        FakeSession.executed.append(statement)
        return []  # no rows


@pytest.fixture
def sql(monkeypatch):
    """Run `await search(...)`; return the SQL text it built and its bound values."""
    monkeypatch.setattr(queries, "AsyncSession", FakeSession)

    def run(coroutine) -> tuple[str, list]:
        FakeSession.executed = []
        asyncio.run(coroutine)
        (statement,) = FakeSession.executed
        compiled = statement.compile(dialect=postgresql.dialect())
        return str(compiled), list(compiled.params.values())

    return run


def test_semantic_search_orders_by_cosine_distance(sql):
    """Semantic search: nearest-first by cosine distance (<=>), limited, skipping unembedded chunks."""
    text, values = sql(queries.semantic_search(None, [0.1, 0.2], limit=7))
    assert "<=>" in text  # pgvector cosine distance
    assert "ORDER BY" in text and "LIMIT" in text
    assert "embedding IS NOT NULL" in text
    assert 7 in values


def test_filters_apply_only_when_given(sql):
    """Ticker and year add a condition only when given; the ticker is upper-cased, the year compared as text."""
    plain, plain_values = sql(queries.semantic_search(None, [0.1], limit=5))
    assert "AAPL" not in plain_values and "2024" not in plain_values

    filtered, values = sql(queries.semantic_search(None, [0.1], limit=5, ticker="aapl", fiscal_year=2024))
    assert "AAPL" in values  # tickers are stored upper-case, so the filter is upper-cased
    assert "2024" in values  # the year is stored as JSON text, so it is compared as text
    assert filtered.count("->>") == plain.count("->>") + 2  # one extra condition per filter


def test_keyword_search_ors_the_words_and_ranks(sql):
    """Keyword search: words OR-ed into one to_tsquery, matched with @@, best ts_rank_cd first."""
    text, values = sql(queries.keyword_search(None, "iPhone revenue?", limit=9))
    assert "@@" in text  # text-search match
    assert "to_tsquery" in text and "iPhone | revenue" in values
    assert "ts_rank_cd" in text and "DESC" in text and 9 in values


def test_keyword_search_without_words_skips_the_database(monkeypatch):
    """A question with no searchable words builds no query at all."""
    monkeypatch.setattr(queries, "AsyncSession", FakeSession)
    FakeSession.executed = []
    assert asyncio.run(queries.keyword_search(None, "?!", limit=5)) == []
    assert FakeSession.executed == []  # no query was even built


def test_get_chunks_matches_document_and_index_together(sql):
    """Neighbour fetch matches the (document, chunk index) pair together, not each column alone."""
    doc = uuid.uuid4()
    text, values = sql(queries.get_chunks(None, {(doc, 3), (doc, 5)}))
    assert "(document_chunks.document_id, document_chunks.chunk_index) IN" in text
    pairs = values[-1]  # the IN list is the last bound value
    assert sorted(index for _, index in pairs) == [3, 5]


def test_get_chunk_by_id_filters_on_the_chunk_id(sql):
    """Lookup by id: a single equality condition on the chunk's own id."""
    wanted = uuid.uuid4()
    text, values = sql(queries.get_chunk_by_id(None, wanted))
    assert "document_chunks.id =" in text and wanted in values


def test_get_chunks_with_nothing_wanted_skips_the_database(monkeypatch):
    """Asking for no chunks builds no query at all."""
    monkeypatch.setattr(queries, "AsyncSession", FakeSession)
    FakeSession.executed = []
    assert asyncio.run(queries.get_chunks(None, set())) == []
    assert FakeSession.executed == []
