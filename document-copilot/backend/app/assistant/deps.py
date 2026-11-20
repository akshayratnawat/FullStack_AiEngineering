"""What the agent's tools are handed on every turn.

PydanticAI passes one `DocumentAgentDeps` to every tool call instead of letting tools
reach for globals, which keeps them easy to test with fakes.
"""

from dataclasses import dataclass, field
from uuid import UUID

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncEngine

from app.retrieval.queries import ChunkHit


@dataclass
class DocumentAgentDeps:
    engine: AsyncEngine  # runs the retrieval SQL
    embedding_client: AsyncOpenAI  # embeds the model's search queries
    # Every chunk any tool has returned during THIS turn, by chunk id. Tools add to it;
    # the validator later accepts a citation only if its chunk id is in here. A fresh,
    # empty dict is made for each turn, so one turn's evidence never leaks into another.
    retrieved: dict[UUID, ChunkHit] = field(default_factory=dict)
