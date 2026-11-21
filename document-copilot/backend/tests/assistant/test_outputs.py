"""Tests for assistant/outputs.py and deps.py: the answer shape the agent must produce."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.assistant.deps import DocumentAgentDeps
from app.assistant.outputs import Citation, GroundedAnswer, ModelAnswer, SourcePassage
from app.retrieval.queries import ChunkHit


def hit() -> ChunkHit:
    """A fake retrieved chunk (an Apple 10-K passage)."""
    return ChunkHit(uuid4(), uuid4(), 49, "iPhone net sales were $201,183 million.", "Item 7", "AAPL",
                    "10-K", 2025, "2025-10-31", "0000320193-25-000079")


def test_grounded_answer_parses_what_a_model_would_send():
    """A well-formed answer parses, and a citation carries the short source id the model copied."""
    raw = {"answer": "iPhone sales rose [1].", "citations": [{"marker": 1, "source_id": "S1"}],
           "enough_evidence": True}
    answer = GroundedAnswer.model_validate(raw)
    assert answer.citations[0].source_id == "S1"


def test_citations_default_to_empty_for_a_not_enough_evidence_answer():
    """An answer with no citations is structurally fine (the validator decides if it is allowed)."""
    answer = GroundedAnswer(answer="The filings do not say.", enough_evidence=False)
    assert answer.citations == []


@pytest.mark.parametrize(
    "raw",
    [
        {"answer": "", "enough_evidence": True},  # empty answer
        {"answer": "x"},  # enough_evidence missing: the model must state it
        {"answer": "x", "enough_evidence": True, "citations": [{"marker": 0, "source_id": "S1"}]},
        {"answer": "x", "enough_evidence": True, "citations": [{"marker": 1}]},  # no source_id
    ],
)
def test_malformed_answers_are_rejected(raw):
    """Empty answer, missing enough_evidence, marker 0 and a citation with no source id are all rejected."""
    with pytest.raises(ValidationError):
        GroundedAnswer.model_validate(raw)


def test_schema_sent_to_the_model_carries_the_field_descriptions():
    """The field descriptions reach the schema the model sees, so they act as instructions."""
    schema = json.dumps(ModelAnswer.model_json_schema())
    assert "[S3]" in schema and "Do not write a list of sources" in schema


def test_the_model_is_not_asked_for_a_citation_list():
    """The model writes only the text and the evidence flag; the citation list is built by the program."""
    assert set(ModelAnswer.model_json_schema()["properties"]) == {"answer", "enough_evidence"}


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
    """A citation carries the short id the validator will look up among the turn's sources."""
    assert Citation(marker=1, source_id="S3").source_id == "S3"


def test_chunks_get_short_ids_in_the_order_they_are_first_shown():
    """The first chunk shown is S1, the next S2; showing a chunk again keeps its id."""
    deps = DocumentAgentDeps(engine=None, embedding_client=None)
    first, second = hit(), hit()

    assert [deps.label_for(first), deps.label_for(second), deps.label_for(first)] == ["S1", "S2", "S1"]
    assert deps.retrieved == {first.id: first, second.id: second}
    assert deps.chunk_id_for("S2") == second.id and deps.chunk_id_for("S3") is None


def test_each_turn_numbers_its_sources_from_one():
    """Short ids are per turn: a new turn's first source is S1 again."""
    one = DocumentAgentDeps(engine=None, embedding_client=None)
    two = DocumentAgentDeps(engine=None, embedding_client=None)
    one.label_for(hit())
    assert two.label_for(hit()) == "S1"
