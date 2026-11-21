"""The three tools the agent may call to read the filings.

PydanticAI turns each function below into a tool: the signature becomes the parameter
schema the model sees (a `Literal` becomes a fixed list of allowed values), and the
docstring becomes the description, so the wording matters. The model can only read
through these tools; it never writes SQL.

Every chunk a tool shows the model is recorded in `deps.retrieved` and given a short id (S1, S2...). That record is what
the grounding validator checks citations against, so the model cannot cite what no tool
returned.
"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field
from pydantic_ai import ModelRetry, RunContext

from app.assistant.deps import DocumentAgentDeps
from app.retrieval import queries
from app.retrieval.queries import ChunkHit
from app.retrieval.retriever import retrieve

# The companies in the corpus. A Literal means PydanticAI rejects any other value and
# asks the model to try again, before anything reaches the database.
Ticker = Literal["AAPL", "AMZN", "GOOGL", "JPM", "META", "MSFT", "NVDA", "TSLA"]

MAX_WINDOW = 3  # chunks each side that read_surrounding_chunks may return (keeps replies small)


def format_chunk(source_id: str, hit: ChunkHit) -> str:
    """One passage as the model sees it: a header with its short id and source, then the text."""
    header = (
        f"[source_id={source_id}] {hit.ticker} {hit.form} fiscal {hit.fiscal_year} "
        f"(filed {hit.filing_date}), section: {hit.section or 'n/a'}"
    )
    return f"{header}\n{hit.content}"


def present(ctx: RunContext[DocumentAgentDeps], hits: list[ChunkHit]) -> str:
    """Record the chunks as retrieved this turn (giving each a short id), then format them for the model."""
    return "\n\n---\n\n".join(format_chunk(ctx.deps.label_for(hit), hit) for hit in hits)


async def search_filings(
    ctx: RunContext[DocumentAgentDeps],
    query: str,
    ticker: Ticker | None = None,
    fiscal_year: int | None = None,
) -> str:
    """Search the 10-K filings and return the best matching passages, most relevant first.

    Each passage starts with its source_id (like S1): cite passages only by that id. Search one company
    at a time for comparisons. If nothing relevant comes back, try different words or drop
    a filter before concluding the filings do not say it.

    Args:
        query: The topic to find, in plain words (for example "iPhone net sales by product").
        ticker: Only this company. Leave out to search all companies.
        fiscal_year: Only this fiscal year (the company's own label, 2021 to 2025). Leave out for all years.
    """
    # neighbor_window=0: return only the matches. The model asks for surrounding text with
    # read_surrounding_chunks when it needs it, which keeps each search reply small.
    passages = await retrieve(
        ctx.deps.engine,
        ctx.deps.embedding_client,
        query,
        ticker=ticker,
        fiscal_year=fiscal_year,
        neighbor_window=0,
    )
    if not passages:
        return "No passages found. Try different words or remove the ticker or fiscal_year filter."
    return present(ctx, [passage.hit for passage in passages])


def resolve(ctx: RunContext[DocumentAgentDeps], source_id: str) -> UUID:
    """The chunk id behind a short id the model typed, or send the model back to try again."""
    chunk_id = ctx.deps.chunk_id_for(source_id)
    if chunk_id is None:
        # ModelRetry sends this message back to the model so it can correct itself.
        raise ModelRetry(f"No passage has source_id {source_id}. Use a source_id from a search result, like S1.")
    return chunk_id


async def read_chunk(ctx: RunContext[DocumentAgentDeps], source_id: str) -> str:
    """Read one passage again in full, by its source_id from an earlier result.

    Args:
        source_id: The source_id of a passage returned by a search (for example "S2").
    """
    hit = await queries.get_chunk_by_id(ctx.deps.engine, resolve(ctx, source_id))
    return present(ctx, [hit])


async def read_surrounding_chunks(
    ctx: RunContext[DocumentAgentDeps],
    source_id: str,
    window: Annotated[int, Field(ge=1, le=MAX_WINDOW)] = 1,
) -> str:
    """Read the passages just before and after one passage, in reading order, plus the passage itself.

    Use this when a result looks cut off, for example a table or explanation that continues.

    Args:
        source_id: The source_id of the passage to read around (for example "S2").
        window: How many passages to read on each side (1 to 3).
    """
    centre = await queries.get_chunk_by_id(ctx.deps.engine, resolve(ctx, source_id))
    wanted = {
        (centre.document_id, index)
        for index in range(max(0, centre.chunk_index - window), centre.chunk_index + window + 1)
    }
    hits = sorted(await queries.get_chunks(ctx.deps.engine, wanted), key=lambda hit: hit.chunk_index)
    return present(ctx, hits)
