import asyncio
import uuid

from app.retrieval import queries, retriever
from app.retrieval.queries import ChunkHit, or_tsquery

DOC = uuid.uuid4()


def chunk(index: int) -> ChunkHit:
    return ChunkHit(uuid.uuid4(), DOC, index, f"text {index}", "Item 7", "AAPL", "10-K", 2025, "2025-10-31", "acc")


def test_or_tsquery_keeps_only_words():
    assert or_tsquery("iPhone revenue?") == "iPhone | revenue"
    assert or_tsquery("a & b | !c ') ; drop") == "a | b | c | drop"  # no tsquery syntax gets through
    assert or_tsquery("?!") == ""


def test_or_tsquery_drops_ignored_words_in_any_case():
    ignore = ["tell", "company"]
    assert or_tsquery("Tell me about the Company revenue", ignore) == "me | about | the | revenue"
    assert or_tsquery("tell company", ignore) == ""  # nothing searchable left


def test_default_ignore_list_removes_filler_but_keeps_finance_terms():
    from app.config import settings

    query = or_tsquery("Please describe the company's iPhone revenue in the 10-K", settings.keyword_ignore_words)
    assert query == "the | iPhone | revenue | in | the"


def test_retrieve_fuses_and_attaches_neighbors(monkeypatch):
    chunks = [chunk(i) for i in range(5)]
    seen = {}

    async def fake_embed(client, texts):
        return [[0.0]], 1

    async def fake_semantic(engine, embedding, limit, ticker, fiscal_year):
        seen["filters"] = (ticker, fiscal_year)
        return [chunks[2], chunks[0]]

    async def fake_keyword(engine, text, limit, ticker, fiscal_year):
        return [chunks[2]]

    async def fake_get_chunks(engine, wanted):
        return [c for c in chunks if (c.document_id, c.chunk_index) in wanted]

    monkeypatch.setattr(retriever, "embed_texts", fake_embed)
    monkeypatch.setattr(queries, "semantic_search", fake_semantic)
    monkeypatch.setattr(queries, "keyword_search", fake_keyword)
    monkeypatch.setattr(queries, "get_chunks", fake_get_chunks)

    passages = asyncio.run(
        retriever.retrieve(None, None, "revenue", top_k=2, ticker="AAPL", fiscal_year=2025)
    )

    assert seen["filters"] == ("AAPL", 2025)
    assert [p.hit.chunk_index for p in passages] == [2, 0]  # in both lists first
    assert [n.chunk_index for n in passages[0].neighbors] == [1, 3]
    assert [n.chunk_index for n in passages[1].neighbors] == [1]  # there is no chunk -1
