"""Chat with the document agent in the terminal, and see the sources behind every answer.

Run from the backend folder:
    uv run python scripts/ask.py                        # interactive; type "quit" to stop
    uv run python scripts/ask.py "Apple iPhone sales in fiscal 2025?" "and the year before?"

Questions in one run share a conversation, so follow-ups work. This uses the real chat
model and database (a few cents per question) but saves nothing: the chat lives in memory.
"""

import argparse
import asyncio

from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded

from app.assistant.agent import answer_question, create_agent
from app.assistant.deps import DocumentAgentDeps
from app.chat.messages import to_model_history
from app.config import settings
from app.database.engine import create_search_engine
from app.embeddings import create_embedding_client

EXCERPT_CHARS = 220


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("questions", nargs="*", help="questions to ask in order; none = interactive")
    questions = parser.parse_args().questions
    scripted = bool(questions)  # questions on the command line: ask them, then stop

    engine, client, agent = create_search_engine(), create_embedding_client(), create_agent()
    rows: list[dict] = []  # the conversation so far, in the shape the database stores it

    try:
        while True:
            if questions:
                question = questions.pop(0)
                print(f"\n> {question}")
            else:
                if scripted:  # every question given on the command line has been asked
                    break
                question = (await asyncio.to_thread(input, "\n> ")).strip()
                if question.lower() in {"quit", "exit", ""}:
                    break

            history = to_model_history(rows, settings.agent_history_messages)
            deps = DocumentAgentDeps(engine=engine, embedding_client=client)  # fresh evidence each turn
            try:
                answer, passages = await answer_question(agent, deps, question, history)
            except (UnexpectedModelBehavior, UsageLimitExceeded) as error:
                print(f"\nNO ANSWER ({type(error).__name__}): {error}")
                continue  # like the app: a failed exchange does not enter the history

            print(f"\n{answer.answer}")
            print(f"\n[enough_evidence={answer.enough_evidence}, searched {len(deps.retrieved)} passages]")
            by_marker = dict(zip(sorted(c.marker for c in answer.citations), passages, strict=True))
            for marker, passage in by_marker.items():
                excerpt = passage.excerpt[:EXCERPT_CHARS].replace("\n", " ")
                print(f"  [{marker}] {passage.ticker} {passage.form} fiscal {passage.fiscal_year}, "
                      f"{passage.section or 'n/a'}\n      {excerpt}...")
            rows += [
                {"role": "user", "content": question, "parts": None},
                {"role": "assistant", "content": answer.answer, "parts": None},
            ]
    finally:
        await engine.dispose()


# psycopg's async mode can't use the default Windows event loop; Linux is unaffected.
asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
