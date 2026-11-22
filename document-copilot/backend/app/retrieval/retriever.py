"""Question in, ranked passages out: hybrid search, fused, each with its neighbouring chunks."""

import asyncio
from dataclasses import dataclass

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import settings
from app.embeddings import embed_texts
from app.retrieval import queries
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.queries import ChunkHit


@dataclass(frozen=True)
class Passage:
    hit: ChunkHit
    score: float  # fused RRF score; only meaningful for comparing passages from one query
    neighbors: list[ChunkHit]  # surrounding chunks in reading order, `hit` itself excluded


async def retrieve(
    engine: AsyncEngine,
    embedding_client: AsyncOpenAI,
    query: str,
    *,
    top_k: int | None = None,  # passages to return
    candidates: int | None = None,  # how deep each search looks before fusion
    neighbor_window: int | None = None,  # chunks each side of a hit (a table often spans chunks)
    ticker: str | None = None,
    fiscal_year: int | None = None,
) -> list[Passage]:
    """Any size left as None uses its `retrieval_*` default from `app.config.settings`."""
    top_k = settings.retrieval_top_k if top_k is None else top_k
    candidates = settings.retrieval_candidates if candidates is None else candidates
    neighbor_window = settings.retrieval_neighbor_window if neighbor_window is None else neighbor_window

    # 1. Turn the question into a vector (the second value, tokens billed, is not needed here).
    vectors, _ = await embed_texts(embedding_client, [query])

    # 2. Run both searches at the same time: by meaning (vector) and by words (full-text).
    semantic, keyword = await asyncio.gather(
        queries.semantic_search(engine, vectors[0], candidates, ticker, fiscal_year),
        queries.keyword_search(engine, query, candidates, ticker, fiscal_year),
    )

    # 3. Merge the two ranked lists with RRF and keep the best `top_k`.
    #    Fusion works on ids only, so look the full chunk up again by id afterwards.
    by_id = {hit.id: hit for hit in [*semantic, *keyword]}
    fused = reciprocal_rank_fusion(
        [[h.id for h in semantic], [h.id for h in keyword]], k=settings.retrieval_rrf_k
    )[:top_k]
    hits = [(by_id[chunk_id], score) for chunk_id, score in fused]

    # 4. Work out which neighbouring chunks to fetch: e.g. window 1 -> offsets [-1, +1].
    #    Index -1 doesn't exist, so skip it at the start of a document.
    offsets = [o for o in range(-neighbor_window, neighbor_window + 1) if o != 0]
    wanted = {
        (hit.document_id, hit.chunk_index + o)
        for hit, _ in hits
        for o in offsets
        if hit.chunk_index + o >= 0
    }
    # 5. One query fetches every neighbour; index them by (document, position) for lookup.
    chunks = {(c.document_id, c.chunk_index): c for c in await queries.get_chunks(engine, wanted)}

    # 6. Pair each hit with its neighbours in reading order. A neighbour that doesn't
    #    exist (document start or end) is silently left out.
    return [
        Passage(
            hit=hit,
            score=score,
            neighbors=[
                chunks[key] for o in offsets if (key := (hit.document_id, hit.chunk_index + o)) in chunks
            ],
        )
        for hit, score in hits
    ]
