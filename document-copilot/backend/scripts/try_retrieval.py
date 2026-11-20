"""Ask a question and print the passages retrieval finds. For manual checks, not production.

Run from the backend folder:
    uv run python scripts/try_retrieval.py "How much revenue came from data center?" --ticker NVDA
    uv run python scripts/try_retrieval.py "iPhone net sales" --ticker AAPL --year 2024 --top-k 3 --full

Embeds the question (one small Azure call) and reads the database; nothing is written.
"""

import argparse
import asyncio

from app.database.engine import create_search_engine
from app.embeddings import create_embedding_client
from app.retrieval.retriever import retrieve

PREVIEW_CHARS = 200


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question")
    parser.add_argument("--ticker", help="only this company, e.g. AAPL")
    parser.add_argument("--year", type=int, help="only this fiscal year")
    parser.add_argument("--top-k", type=int, help="passages to return (default: RETRIEVAL_TOP_K from config)")
    parser.add_argument("--full", action="store_true", help="print each passage in full, not a preview")
    args = parser.parse_args()

    engine = create_search_engine()
    try:
        passages = await retrieve(
            engine,
            create_embedding_client(),
            args.question,
            top_k=args.top_k,
            ticker=args.ticker,
            fiscal_year=args.year,
        )
    finally:
        await engine.dispose()

    if not passages:
        print("No passages found.")
    for rank, passage in enumerate(passages, start=1):
        hit = passage.hit
        neighbors = [n.chunk_index for n in passage.neighbors]
        print(f"#{rank}  score {passage.score:.4f}  {hit.ticker} FY{hit.fiscal_year} {hit.form}  "
              f"chunk {hit.chunk_index} (neighbors {neighbors})")
        print(f"    section: {hit.section}")
        text = hit.content if args.full else hit.content[:PREVIEW_CHARS].replace("\n", " ")
        print(f"    {text}\n")


# psycopg's async mode can't use the default Windows event loop (Proactor); Linux is unaffected.
asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
