"""Runs one chat turn: the user asks, the agent answers from the filings, the exchange is saved.

Three outcomes:
- Answered: the validated answer is streamed and saved.
- Could not answer (the model could not produce a properly sourced answer, or the question
  needed more searching than the caps allow): a plain explanation is streamed and saved in
  place of an answer, so the question stays in the thread.
- Broke (the model service or database is down): an error event is sent and nothing is
  saved, so the user can simply send the question again.
"""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

import structlog
from pydantic_ai import Agent
from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded

from app.assistant.agent import answer_question
from app.assistant.deps import DocumentAgentDeps
from app.assistant.outputs import ModelAnswer
from app.chat.messages import (
    CITATIONS_PART_TYPE,
    citation_parts,
    demo_parts,
    failed_parts,
    progress_part,
    text_parts,
    title_from,
    to_model_history,
)
from app.chat.streaming import sse, ui_message_stream
from app.config import settings
from app.database.chats import ChatStore
from app.demo.replay import DemoAnswer, find_demo

logger = structlog.get_logger()

# A replayed recording shows its research steps at this pace, so it reads like the real thing but
# never takes long: a recording with many steps is sped up to fit REPLAY_MAX_SECONDS.
REPLAY_STEP_SECONDS = 0.8
REPLAY_MAX_SECONDS = 8.0

# The answer is complete before its text is sent (it has to pass the grounding check first), so
# this only gives the UI a typing effect. Kept tiny so it adds about a second to a long answer.
STREAM_WORD_DELAY_SECONDS = 0.01

CANNOT_ANSWER_TEXT = (
    "I couldn't produce an answer that I can fully back with sources from the filings, so I'm "
    "not giving one. Try narrowing the question (one company, one year) or rephrasing it."
)
TOO_BROAD_TEXT = (
    "That question needs more searching than I can do in one go. Try asking about one company "
    "or one year at a time."
)
ERROR_TEXT = "Something went wrong while answering. Please try again."


@dataclass
class TurnOutcome:
    """What happened this turn, filled in while the reply streams and read when saving."""

    text: str = ""
    failed: bool = False  # True when `text` explains why there is no answer
    data_parts: list[dict] = field(default_factory=list)  # the citations part, when the answer has sources
    steps: list[str] = field(default_factory=list)  # the research steps shown while answering


async def words(text: str) -> AsyncIterator[str]:
    """The text a word at a time, as the stream's chunks."""
    pieces = text.split(" ")
    for index, word in enumerate(pieces):
        await asyncio.sleep(STREAM_WORD_DELAY_SECONDS)
        yield word if index == len(pieces) - 1 else word + " "


async def run_turn(
    store: ChatStore,
    thread_id: UUID,
    user_text: str,
    agent: Agent[DocumentAgentDeps, ModelAnswer],
    deps: DocumentAgentDeps,
) -> AsyncIterator[str]:
    """The SSE events for one turn. The caller has already checked the thread is the user's."""
    asked_at = datetime.now(UTC)
    # A thread with no title yet is a new one: name it after its first question.
    title = None
    if await store.get_thread_title(thread_id) is None:
        title = title_from(user_text)
    # Read the history BEFORE this exchange is saved, so the new question is not in it twice.
    history = to_model_history(await store.list_messages(thread_id), settings.agent_history_messages)

    outcome = TurnOutcome()
    deps.progress = asyncio.Queue()
    demo = find_demo(user_text)  # a recorded example: replayed, the model is not called

    async def research() -> AsyncIterator[dict]:
        """Run the agent, sending the progress part again after every step it reports.

        The agent runs as a task so its steps can be streamed while it works. If the client goes
        away, this generator is closed and the `finally` stops the agent, so nothing keeps
        spending tokens for a reply nobody will read.
        """
        run = asyncio.create_task(answer_question(agent, deps, user_text, history))
        try:
            while not run.done():
                next_step = asyncio.ensure_future(deps.progress.get())
                await asyncio.wait({run, next_step}, return_when=asyncio.FIRST_COMPLETED)
                if not next_step.done():
                    next_step.cancel()
                    break
                outcome.steps.append(next_step.result())
                yield progress_part(list(outcome.steps), done=False)
            while not deps.progress.empty():  # steps reported in the agent's last moments
                outcome.steps.append(deps.progress.get_nowait())
            try:
                answer, passages = run.result()
                outcome.text = answer.answer
                # Filled before the text is sent; the stream reads it once the text ends.
                outcome.data_parts.extend(citation_parts(answer, passages))
            except UsageLimitExceeded:
                outcome.text, outcome.failed = TOO_BROAD_TEXT, True
            except UnexpectedModelBehavior:
                # The retries allowed by the agent did not produce a grounded answer.
                outcome.text, outcome.failed = CANNOT_ANSWER_TEXT, True
            # Any other error propagates: the stream turns it into an error event.
            yield progress_part(list(outcome.steps), done=True)
        finally:
            run.cancel()

    async def replay(demo: DemoAnswer) -> AsyncIterator[dict]:
        """Show a recorded answer the way a live one appears. No model call, no search."""
        pause = min(REPLAY_STEP_SECONDS, REPLAY_MAX_SECONDS / max(len(demo.steps), 1))
        for step in demo.steps:
            await asyncio.sleep(pause)
            outcome.steps.append(step)
            yield progress_part(list(outcome.steps), done=False)
        outcome.text = demo.answer
        outcome.data_parts.extend(demo_parts(demo.citations, demo.recorded_at, demo.model))
        yield progress_part(list(outcome.steps), done=True)

    async def reply() -> AsyncIterator[str]:
        async for piece in words(outcome.text):
            yield piece

    def saved_progress() -> list[dict]:
        return [progress_part(outcome.steps, done=True)] if outcome.steps else []

    async def save(answer_text: str) -> None:
        await store.save_turn(
            thread_id=thread_id,
            user_text=user_text,
            user_parts=text_parts(user_text),
            assistant_text=answer_text,
            assistant_parts=(
                [*saved_progress(), *failed_parts(answer_text)]
                if outcome.failed
                else [*saved_progress(), *text_parts(answer_text), *outcome.data_parts]
            ),
            asked_at=asked_at,
            set_title=title,
            citations=[
                source
                for part in outcome.data_parts
                if part["type"] == CITATIONS_PART_TYPE
                for source in part["data"]
            ],
        )

    try:
        async for event in ui_message_stream(
            message_id=str(uuid4()),
            text_chunks=reply(),
            on_complete=save,
            data_parts=outcome.data_parts,
            before_text=replay(demo) if demo else research(),
        ):
            yield event
    except Exception:
        # Not the question's fault (model service or database down): the response has
        # already started, so the failure has to travel inside the stream. Nothing is saved.
        logger.exception("chat_turn_failed", thread_id=str(thread_id))
        yield sse({"type": "error", "errorText": ERROR_TEXT})
        yield sse("[DONE]")
