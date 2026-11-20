"""The three database reads behind retrieval: meaning search, keyword search, neighbours."""

import re
import uuid
from collections.abc import Collection
from dataclasses import dataclass

from sqlalchemy import Select, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.config import settings
from app.database.models.document_chunks import DocumentChunk

_META = DocumentChunk.chunk_metadata
# Every query selects these columns, so all of them return the same ChunkHit shape.
# Filing details (ticker, year...) live in the JSONB `chunk_metadata`; .astext reads them as text.
COLUMNS = (
    DocumentChunk.id,
    DocumentChunk.document_id,
    DocumentChunk.chunk_index,
    DocumentChunk.content,
    DocumentChunk.section,
    _META["ticker"].astext.label("ticker"),
    _META["form"].astext.label("form"),
    _META["fiscal_year"].astext.label("fiscal_year"),
    _META["filing_date"].astext.label("filing_date"),
    _META["accession_number"].astext.label("accession_number"),
)


@dataclass(frozen=True)
class ChunkHit:
    """One chunk of a filing plus the filing details needed to cite it."""

    id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    content: str
    section: str | None
    ticker: str
    form: str
    fiscal_year: int
    filing_date: str
    accession_number: str


def _hit(row) -> ChunkHit:
    # fiscal_year comes out of JSONB as text; convert it back to a number.
    return ChunkHit(**{**row._mapping, "fiscal_year": int(row.fiscal_year)})


def _filtered(query: Select, ticker: str | None, fiscal_year: int | None) -> Select:
    """Optionally narrow a search to one company and/or one fiscal year."""
    if ticker:
        query = query.where(_META["ticker"].astext == ticker.upper())
    if fiscal_year:
        query = query.where(_META["fiscal_year"].astext == str(fiscal_year))
    return query


async def semantic_search(
    engine: AsyncEngine,
    query_embedding: list[float],
    limit: int,
    ticker: str | None = None,
    fiscal_year: int | None = None,
) -> list[ChunkHit]:
    """Chunks closest in meaning to the query, best first (cosine distance, HNSW index)."""
    query = (
        select(*COLUMNS)
        .where(DocumentChunk.embedding.is_not(None))  # skip chunks not embedded yet
        .order_by(DocumentChunk.embedding.cosine_distance(query_embedding))
        .limit(limit)
    )
    async with AsyncSession(engine) as session:
        return [_hit(row) for row in await session.execute(_filtered(query, ticker, fiscal_year))]


def or_tsquery(text: str, ignore: Collection[str] = ()) -> str:
    """'Apple iPhone revenue?' -> 'Apple | iPhone | revenue'.

    Words in `ignore` (lower-case, e.g. "tell", "company") are dropped first: they are
    filler that would match chunks for no good reason.

    `websearch_to_tsquery` ANDs every word, so a natural-language question with one
    unlucky word matches nothing. OR-ing the words and letting `ts_rank_cd` put chunks
    matching more of them first suits a question-shaped query. Keeping only alphanumeric
    words also means user text can never inject tsquery syntax.
    """
    skip = set(ignore)
    words = re.findall(r"[A-Za-z0-9]+", text)
    return " | ".join(word for word in words if word.lower() not in skip)


async def keyword_search(
    engine: AsyncEngine,
    text: str,
    limit: int,
    ticker: str | None = None,
    fiscal_year: int | None = None,
) -> list[ChunkHit]:
    """Chunks sharing the most query words, best first (Postgres full-text search, GIN index)."""
    tsquery_text = or_tsquery(text, settings.keyword_ignore_words)
    if not tsquery_text:  # the question had no searchable words left after dropping filler
        return []
    # to_tsquery applies English stemming and drops stopwords, matching how search_vector was built.
    tsquery = func.to_tsquery("english", tsquery_text)
    query = (
        select(*COLUMNS)
        .where(DocumentChunk.search_vector.op("@@")(tsquery))  # @@ = "this chunk matches the query"
        .order_by(func.ts_rank_cd(DocumentChunk.search_vector, tsquery).desc())
        .limit(limit)
    )
    async with AsyncSession(engine) as session:
        return [_hit(row) for row in await session.execute(_filtered(query, ticker, fiscal_year))]


async def get_chunks(engine: AsyncEngine, wanted: set[tuple[uuid.UUID, int]]) -> list[ChunkHit]:
    """Fetch specific chunks by (document id, chunk index); used to load a hit's neighbours."""
    if not wanted:
        return []
    # Matching the pair together (not each column separately) avoids pulling in extra chunks.
    query =select(*COLUMNS).where(tuple_(DocumentChunk.document_id, DocumentChunk.chunk_index).in_(wanted))
    async with AsyncSession(engine) as session:
        return [_hit(row) for row in await session.execute(query)]
