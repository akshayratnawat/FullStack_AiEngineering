"""Tests for assistant/outputs.py and deps.py: the answer shape the agent must produce."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.assistant.deps import DocumentAgentDeps
from app.assistant.outputs import Citation, GroundedAnswer, SourcePassage
from app.retrieval.queries import ChunkHit


def hit() -> ChunkHit:
    """A fake retrieved chunk (an Apple 10-K passage)."""
    return ChunkHit(uuid4(), uuid4(), 49, "iPhone net sales were $201,183 million.", "Item 7", "AAPL",
                    "10-K", 2025, "2025-10-31", "0000320193-25-000079")


def test_grounded_answer_parses_what_a_model_would_send():
    """A well-formed answer parses, and the chunk id string becomes a real UUID."""
    chunk_id = uuid4()
    raw = {"answer": "iPhone sales rose [1].", "citations": [{"marker": 1, "chunk_id": str(chunk_id)}],
           "enough_evidence": True}
    answer = GroundedAnswer.model_validate(raw)
    assert answer.citations[0].chunk_id == chunk_id  # the string became a real UUID


def test_citations_default_to_empty_for_a_not_enough_evidence_answer():
    """An answer with no citations is structurally fine (the validator decides if it is allowed)."""
    answer = GroundedAnswer(answer="The filings do not say.", enough_evidence=False)
    assert answer.citations == []


@pytest.mark.parametrize(
    "raw",
    [
        {"answer": "", "enough_evidence": True},  # empty answer
        {"answer": "x"},  # enough_evidence missing: the model must state it
        {"answer": "x", "enough_evidence": True, "citations": [{"marker": 0, "chunk_id": str(uuid4())}]},
        {"answer": "x", "enough_evidence": True, "citations": [{"marker": 1, "chunk_id": "not-a-uuid"}]},
    ],
)
def test_malformed_answers_are_rejected(raw):
    """Empty answer, missing enough_evidence, marker 0 and a bad chunk id are all rejected."""
    with pytest.raises(ValidationError):
        GroundedAnswer.model_validate(raw)


def test_schema_sent_to_the_model_carries_the_field_descriptions():
    """The field descriptions reach the schema the model sees, so they act as instructions."""
    schema = json.dumps(GroundedAnswer.model_json_schema())
    assert "[n] marker" in schema and "Never invent one" in schema


def test_source_passage_copies_the_hit_and_keeps_the_text_as_excerpt():
    """from_hit copies the filing details and snapshots the chunk text as the excerpt."""
    chunk = hit()
    passage = SourcePassage.from_hit(chunk)
    assert passage.chunk_id == chunk.id
    assert (passage.ticker, passage.fiscal_year, passage.section) == ("AAPL", 2025, "Item 7")
    assert passage.excerpt == chunk.content


def test_each_turn_gets_its_own_retrieved_record():
    """Two turns never share one `retrieved` dict, so evidence can't leak between turns."""
    first = DocumentAgentDeps(engine=None, embedding_client=None)
    second = DocumentAgentDeps(engine=None, embedding_client=None)
    chunk = hit()
    first.retrieved[chunk.id] = chunk
    assert second.retrieved == {}


def test_citation_is_the_pair_the_validator_will_look_up():
    """A citation carries the chunk id the validator will look up in `retrieved`."""
    chunk = hit()
    assert Citation(marker=1, chunk_id=chunk.id).chunk_id == chunk.id
