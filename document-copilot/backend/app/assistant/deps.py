"""What the agent's tools are handed on every turn.

PydanticAI passes one `DocumentAgentDeps` to every tool call instead of letting tools
reach for globals, which keeps them easy to test with fakes.
"""

import asyncio
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
    # The short id the model sees for each retrieved chunk ("S1", "S2"...), by chunk id. The
    # model copies these when it cites or reads a passage; a 36-character UUID was too easy
    # to garble in a long answer. Numbered per turn, so ids mean nothing across turns.
    labels: dict[UUID, str] = field(default_factory=dict)
    # Where the tools announce what they are doing ("Searching AAPL FY2024: iPhone net sales"),
    # so the chat can show the research live. None (scripts, tests) means nobody is listening.
    progress: asyncio.Queue[str] | None = None

    def report(self, step: str) -> None:
        """Announce one research step to whoever is showing progress, if anyone."""
        if self.progress is not None:
            self.progress.put_nowait(step)

    def label_for(self, hit: ChunkHit) -> str:
        """Record a chunk as shown to the model and return its short id (new chunks get the next number)."""
        self.retrieved[hit.id] = hit
        return self.labels.setdefault(hit.id, f"S{len(self.labels) + 1}")

    def chunk_id_for(self, source_id: str) -> UUID | None:
        """The chunk a short id stands for, or None if no tool has shown that id this turn."""
        return next((chunk_id for chunk_id, label in self.labels.items() if label == source_id), None)
