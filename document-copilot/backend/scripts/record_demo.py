"""Record real answers to show as the app's "recorded example" questions.

Run from the backend folder:
    uv run python scripts/record_demo.py --out app/demo/candidates.json "Question one" "Question two"

Each question goes through the real agent (a few cents each), exactly as in the app, and what the
analyst would have seen is saved: the research steps, the checked answer text, and the sources
with their exact passages. Nothing is written to the database. Read the saved answers against
the filings before using them: the recorded answer is what visitors will be shown as-is.
Copy the chosen answers into app/demo/answers.json and restart the backend (see app/demo/replay.py).
"""

import argparse
import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from pydantic_ai.exceptions import (
    ModelHTTPError,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
)

from app.assistant.agent import answer_question, create_agent
from app.assistant.deps import DocumentAgentDeps
from app.chat.messages import citation_parts
from app.config import settings
from app.database.engine import create_search_engine
from app.embeddings import create_embedding_client

RATE_LIMIT_WAIT_SECONDS = 65


async def record(agent, engine, client, question: str, attempts: int) -> dict | None:
    for attempt in range(1, attempts + 1):
        deps = DocumentAgentDeps(engine=engine, embedding_client=client, progress=asyncio.Queue())
        started = time.monotonic()
        try:
            answer, passages = await answer_question(agent, deps, question)
        except (UnexpectedModelBehavior, UsageLimitExceeded) as error:
            print(f"  attempt {attempt}: no answer ({type(error).__name__})")
            continue
        except ModelHTTPError as error:
            if error.status_code != 429:
                raise
            # Azure's tokens-per-minute limit: a long question can use a whole minute's share.
            print(f"  attempt {attempt}: rate limited, waiting {RATE_LIMIT_WAIT_SECONDS}s")
            await asyncio.sleep(RATE_LIMIT_WAIT_SECONDS)
            continue
        steps = []
        while not deps.progress.empty():
            steps.append(deps.progress.get_nowait())
        parts = citation_parts(answer, passages)
        print(f"  attempt {attempt}: answered in {time.monotonic() - started:.0f}s, {len(steps)} steps")
        return {
            "question": question,
            "steps": steps,
            "answer": answer.answer,
            "citations": parts[0]["data"] if parts else [],
            "recorded_at": datetime.now(UTC).date().isoformat(),
            "model": settings.openai_chat_model,
        }
    return None


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("questions", nargs="+")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--attempts", type=int, default=4)
    args = parser.parse_args()

    engine, client, agent = create_search_engine(), create_embedding_client(), create_agent()
    recorded = []
    try:
        for question in args.questions:
            print(f"> {question}")
            entry = await record(agent, engine, client, question, args.attempts)
            if entry:
                recorded.append(entry)
                args.out.write_text(json.dumps(recorded, indent=2, ensure_ascii=False), encoding="utf-8")
    finally:
        await engine.dispose()
    print(f"Saved {len(recorded)} of {len(args.questions)} answers to {args.out}")


# psycopg's async mode can't use the default Windows event loop; Linux is unaffected.
asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
