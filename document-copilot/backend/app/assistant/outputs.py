"""The shapes the agent must answer in, and the passages a citation points at.

`ModelAnswer` is the agent's output type: the answer text, with a source marker such as
`[S3]` after each claim, and the evidence flag. PydanticAI makes the model fill it in and
rejects anything that does not fit. The `description` on each field is sent to the model
as part of the schema, so it doubles as instructions.

`GroundedAnswer` is what the rest of the app gets after `grounding/validator.py` has checked
the markers against what was retrieved and numbered them `[1]`, `[2]`... in order of first
use: the same answer plus the list of citations. The model never writes that list, so the
text and the list cannot disagree.
"""

from uuid import UUID

from pydantic import BaseModel, Field

from app.retrieval.queries import ChunkHit


class Citation(BaseModel):
    """One source the answer relies on, tied to a [n] marker in the answer text."""

    marker: int = Field(ge=1, description="The n in the [n] marker used in the answer text. Starts at 1.")
    source_id: str = Field(
        description='The source id of a passage a tool returned this turn, such as "S3". Copy it exactly. Never invent one.'
    )


class ModelAnswer(BaseModel):
    """An answer written only from retrieved passages, each claim marked with its source."""

    answer: str = Field(
        min_length=1,
        description=(
            "The answer for the analyst. Put a source marker such as [S3] right after every factual "
            "claim, using the source_id of the passage that supports it (two passages: [S3][S5]). "
            "Write only the source_ids a tool showed you. Do not write a list of sources. "
            "If the passages do not support an answer, say so plainly instead."
        ),
    )
    enough_evidence: bool = Field(
        description="True if the retrieved passages support the answer; false if the answer says they do not."
    )


class GroundedAnswer(ModelAnswer):
    """A checked answer: markers renumbered [1], [2]... in order of first use, with what each stands for."""

    citations: list[Citation] = Field(
        default_factory=list,
        description="One entry per [n] marker used in the answer. Empty only when enough_evidence is false.",
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
