"""The shapes the agent must answer in, and the passages a citation points at.

`ModelAnswer` is the agent's output type: a list of claims, each with the sources that
support it, and the evidence flag. The model does not write the answer as free text and
never writes a citation marker: the program joins the claims and puts the marker right after
each one, so a source is always next to the statement it backs. PydanticAI makes the model
fill the type in and rejects anything that does not fit. The `description` on each field is
sent to the model as part of the schema, so it doubles as instructions.

`GroundedAnswer` is what the rest of the app gets after `grounding/validator.py` has checked
the claims against what was retrieved: the joined text with `[1]`, `[2]`... markers, numbered
in order of first use, plus the list of citations. Because the program writes both, the text
and the list cannot disagree.
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.retrieval.queries import ChunkHit


class Citation(BaseModel):
    """One source the answer relies on, tied to a [n] marker in the answer text."""

    marker: int = Field(ge=1, description="The n in the [n] marker used in the answer text. Starts at 1.")
    source_id: str = Field(
        description='The source id of a passage a tool returned this turn, such as "S3". Copy it exactly. Never invent one.'
    )


class Claim(BaseModel):
    """One statement of the answer and the passages that support it."""

    kind: Literal["fact", "calculation", "note"] = Field(
        description=(
            '"fact": a statement the passages make; it needs sources. '
            '"calculation": a figure you worked out (a difference, a share); it needs the sources of its inputs. '
            '"note": framing, a transition, a question back to the analyst, or what the filings do not say; '
            "it has no sources and no figures. A statement that the filings do not say or prove something is a note."
        )
    )
    text: str = Field(
        min_length=1,
        description=(
            "One sentence, or one clause of a sentence, in plain words. A fact quotes each figure exactly as the "
            "passage writes it, with unit and fiscal year; the app checks that every figure is in one of the "
            "passages listed in sources and places a marker right after it. Do not write source ids or [1] "
            "markers in it. It may start with a connector such as \", \" or \"and \" so that claims read as "
            "one sentence, or with a newline or \"- \" to start a paragraph or a list item."
        ),
    )
    sources: list[str] = Field(
        default_factory=list,
        max_length=8,
        description=(
            'The source_ids (such as "S3") of the passages that say this, copied exactly from a tool result. '
            "At most eight. Empty only for a note."
        ),
    )


class ModelAnswer(BaseModel):
    """An answer written only from retrieved passages, as claims that each carry their sources."""

    claims: list[Claim] = Field(
        min_length=1,
        description=(
            "The answer, in reading order. The app joins the claims into text and puts the source marker "
            "right after each claim, so every statement must be its own claim. If the passages do not support "
            "an answer, say so plainly in a note."
        ),
    )
    enough_evidence: bool = Field(
        description="True if the retrieved passages support the answer; false if the answer says they do not."
    )


class GroundedAnswer(BaseModel):
    """A checked answer: the claims joined into text with [1], [2]... markers, and what each marker stands for."""

    answer: str = Field(min_length=1)
    enough_evidence: bool
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
