"""The document agent: instructions + tools + a typed answer, checked for grounding.

The agent searches the filings with its tools, then must return a `ModelAnswer` (text with
`[S3]`-style source markers). Before it is accepted, the grounding validator checks it against
what the tools actually returned and numbers the markers, giving a `GroundedAnswer`. If the
check fails, the model is told what is wrong and gets `agent_output_retries` more tries; after
that it raises, and the caller shows a controlled error instead of an unsupported answer.
"""

from pathlib import Path

import structlog
from pydantic_ai import Agent, ModelRetry, RunContext, UsageLimits
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model

from app.assistant.deps import DocumentAgentDeps
from app.assistant.model import create_chat_model
from app.assistant.outputs import GroundedAnswer, ModelAnswer, SourcePassage
from app.assistant.tools import read_chunk, read_surrounding_chunks, search_filings
from app.config import settings
from app.grounding.validator import GroundingError, ground

logger = structlog.get_logger()

INSTRUCTIONS = (Path(__file__).parent / "instructions.md").read_text(encoding="utf-8")


def create_agent(model: Model | None = None) -> Agent[DocumentAgentDeps, ModelAnswer]:
    """Build the agent. Pass a `model` only in tests; otherwise the configured Azure chat model."""
    agent = Agent(
        model or create_chat_model(),
        deps_type=DocumentAgentDeps,
        output_type=ModelAnswer,
        instructions=INSTRUCTIONS,
        tools=[search_filings, read_chunk, read_surrounding_chunks],
        # Retries for a wrong answer (the grounding check below; `agent_output_retries`) and one per tool call
        # (for example an unknown source_id). A second failure raises.
        retries={"output": settings.agent_output_retries, "tools": 1},
    )

    @agent.output_validator
    def check_grounding(ctx: RunContext[DocumentAgentDeps], answer: ModelAnswer) -> ModelAnswer:
        """Reject an answer whose citations are not backed by what the tools returned."""
        try:
            ground(answer, ctx.deps.retrieved, ctx.deps.labels)
        except GroundingError as error:
            # Without this, a question that fails twice only says "could not answer" and the
            # reason is lost. Logged so the live runs show which rule the model breaks.
            logger.warning("answer_not_grounded", problems=error.problems)
            # The message lists every broken rule, worded for the model, so one retry can fix them all.
            raise ModelRetry(str(error)) from error
        return answer

    return agent


async def answer_question(
    agent: Agent[DocumentAgentDeps, ModelAnswer],
    deps: DocumentAgentDeps,
    question: str,
    history: list[ModelMessage] | None = None,
) -> tuple[GroundedAnswer, list[SourcePassage]]:
    """Run one question and return the grounded answer with the passages it cites.

    `history` is the thread's earlier messages, so follow-up questions have their context.
    It is context only: the answer must still be grounded in passages found THIS turn.

    Raises `UnexpectedModelBehavior` if the model could not produce a grounded answer even
    after its retry, and `UsageLimitExceeded` if it hit a cap in `settings.agent_*`.
    """
    result = await agent.run(
        question,
        deps=deps,
        message_history=history,
        usage_limits=UsageLimits(
            request_limit=settings.agent_max_model_requests,
            tool_calls_limit=settings.agent_max_tool_calls,
            total_tokens_limit=settings.agent_max_total_tokens,
        ),
    )
    # The output validator has already accepted this answer; grounding it again produces the
    # numbered answer and its cited passages (in marker order) for the UI and the database.
    return ground(result.output, deps.retrieved, deps.labels, log=False)
