"""The shapes the agent must answer in, and the passages a citation points at.

`GroundedAnswer` is the agent's output type: PydanticAI makes the model fill it in and
rejects anything that does not fit. The `description` on each field is sent to the model
as part of the schema, so it doubles as instructions. Whether the citations are actually
true is NOT checked here; `grounding/validator.py` does that against what was retrieved.
"""

from uuid import UUID

from pydantic import BaseModel, Field

from app.retrieval.queries import ChunkHit


class Citation(BaseModel):
    """One source the answer relies on, tied to a [n] marker in the answer text."""

    marker: int = Field(ge=1, description="The n in the [n] marker used in the answer text. Starts at 1.")
    chunk_id: UUID = Field(description="The chunk_id of a passage returned by a search tool. Never invent one.")


class GroundedAnswer(BaseModel):
    """An answer written only from retrieved passages, with its citations."""

    answer: str = Field(
        min_length=1,
        description=(
            "The answer for the analyst. Put a [n] marker after every factual claim. "
            "If the passages do not support an answer, say so plainly instead."
        ),
    )
    citations: list[Citation] = Field(
        default_factory=list,
        description="One entry per [n] marker used in the answer. Empty only when enough_evidence is false.",
    )
    enough_evidence: bool = Field(
        description="True if the retrieved passages support the answer; false if the answer says they do not."
    )


class SourcePassage(BaseModel):
    """A cited passage with what the UI needs to show it: which filing, where, and the exact text."""

    chunk_id: UUID
    ticker: str
    form: str
    fiscal_year: int
    filing_date: str
    accession_number: str
    section: str | None
    excerpt: str  # the chunk text as it was when cited; kept even if the filing is re-ingested later

    @classmethod
    def from_hit(cls, hit: ChunkHit) -> "SourcePassage":
        return cls(
            chunk_id=hit.id,
            ticker=hit.ticker,
            form=hit.form,
            fiscal_year=hit.fiscal_year,
            filing_date=hit.filing_date,
            accession_number=hit.accession_number,
            section=hit.section,
            excerpt=hit.content,
        )
