"""Tests for grounding/validator.py: one test per rule, plus the passing cases.

No model, database or network. "retrieved" below stands for the chunks the search tools
returned this turn; the validator accepts a citation only if its chunk is in there.

Rules under test (numbered as in the validator's docstring):
  1. every citation points at a retrieved chunk
  2. each marker number is used by one citation only
  3. text markers and citations agree both ways (3a: marker without citation,
     3b: citation without marker)
  4. enough_evidence=True needs at least one citation
"""

from uuid import uuid4

import pytest

from app.assistant.outputs import Citation, GroundedAnswer
from app.grounding.validator import GroundingError, validate
from app.retrieval.queries import ChunkHit

# --- helpers -----------------------------------------------------------------


def chunk(text: str = "text") -> ChunkHit:
    """A fake retrieved chunk (an Apple 10-K passage) with a fresh random id."""
    # Positional fields: chunk id, document id, chunk index, text, section,
    # ticker, form, fiscal year, filing date, accession number.
    return ChunkHit(uuid4(), uuid4(), 1, text, "Item 7", "AAPL", "10-K", 2025, "2025-10-31", "acc")


def answer(text: str, markers_to_chunks: dict[int, ChunkHit], enough: bool = True) -> GroundedAnswer:
    """Build an answer whose citations are {marker number: the chunk it cites}."""
    citations = [Citation(marker=m, chunk_id=c.id) for m, c in markers_to_chunks.items()]
    return GroundedAnswer(answer=text, citations=citations, enough_evidence=enough)


def problems_of(given: GroundedAnswer, retrieved: dict) -> list[str]:
    """Run the validator, expect it to reject the answer, and return the listed problems."""
    with pytest.raises(GroundingError) as raised:  # the test fails if nothing is raised
        validate(given, retrieved)
    return raised.value.problems


# --- passing cases -----------------------------------------------------------


def test_a_grounded_answer_returns_its_passages_in_marker_order():
    """A valid answer passes; passages come back ordered by marker, whatever order they were cited in."""
    first, second = chunk("iPhone text"), chunk("Services text")
    # `retrieved` is what the search tools returned: both chunks are known.
    retrieved = {first.id: first, second.id: second}
    # Marker 2 is listed before marker 1 on purpose, to check the ordering.
    given = answer("Services grew [2]. iPhone fell [1].", {2: second, 1: first})

    passages = validate(given, retrieved)

    # Marker 1 (iPhone) must come first even though it was cited second.
    assert [p.excerpt for p in passages] == ["iPhone text", "Services text"]
    # The passage carries the filing details the UI needs, copied from the chunk.
    assert passages[0].ticker == "AAPL"


def test_an_honest_not_enough_evidence_answer_needs_no_citations():
    """Saying "the filings do not say" with no citations is allowed (enough_evidence=False)."""
    given = GroundedAnswer(answer="The filings do not say.", enough_evidence=False)
    # Nothing was retrieved and nothing is cited: it passes and returns no passages.
    assert validate(given, {}) == []


def test_a_bracketed_year_is_not_a_citation_marker():
    """A bracketed year like [2024] has four digits, so it is ordinary text, not a marker."""
    seen = chunk()
    given = answer("Revenue in [2024] rose [1].", {1: seen})
    # If [2024] were read as a marker it would need a citation 2024 and be rejected.
    assert len(validate(given, {seen.id: seen})) == 1


# --- one test per rejection rule ---------------------------------------------


def test_citing_a_chunk_no_search_returned_is_rejected():
    """Rule 1: a cited chunk that is not in `retrieved` was invented or remembered, not found."""
    seen, invented = chunk(), chunk()
    given = answer("A claim [1].", {1: invented})  # cites a chunk no tool ever returned
    problems = problems_of(given, {seen.id: seen})  # only `seen` was retrieved
    # Exactly one problem, and it names the offending chunk id.
    assert len(problems) == 1 and str(invented.id) in problems[0]


def test_two_citations_sharing_a_marker_are_rejected():
    """Rule 2: [1] must mean one source, so two citations can't both be number 1."""
    a, b = chunk(), chunk()
    given = GroundedAnswer(
        answer="Claim [1].",
        # Two different sources, both numbered 1. Built by hand: `answer()` uses a dict,
        # which cannot hold the same marker twice.
        citations=[Citation(marker=1, chunk_id=a.id), Citation(marker=1, chunk_id=b.id)],
        enough_evidence=True,
    )
    assert "Marker [1] is used by more than one citation" in problems_of(given, {a.id: a, b.id: b})[0]


def test_a_marker_in_the_text_without_a_citation_is_rejected():
    """Rule 3a: the text says [2] but no citation 2 exists, so that claim has no source."""
    seen = chunk()
    # The text uses [1] and [2]; only citation 1 exists.
    problems = problems_of(answer("Claim [1] and another [2].", {1: seen}), {seen.id: seen})
    assert problems == ["The text uses [2] but there is no citation 2."]


def test_a_citation_never_used_in_the_text_is_rejected():
    """Rule 3b: citation 2 is listed but nothing in the text points at it."""
    seen, extra = chunk(), chunk()
    # Two citations are listed, but the text only uses [1].
    given = answer("Claim [1].", {1: seen, 2: extra})
    problems = problems_of(given, {seen.id: seen, extra.id: extra})  # both chunks are real
    assert problems == ["Citation 2 is listed but [2] never appears in the answer text."]


def test_claiming_enough_evidence_without_any_citation_is_rejected():
    """Rule 4: an answer that says it has evidence must show at least one source."""
    # A confident answer with no sources at all: the exact failure grounding exists to stop.
    problems = problems_of(GroundedAnswer(answer="Apple grew.", enough_evidence=True), {})
    assert "enough_evidence is true but there are no citations" in problems[0]


def test_not_enough_evidence_cannot_use_markers_it_does_not_back():
    """Rule 3a still applies to a "not enough evidence" answer: a stray [1] with no citation is rejected."""
    # enough_evidence=False excuses having no citations, but not a dangling [1] in the text.
    problems = problems_of(GroundedAnswer(answer="Maybe [1].", enough_evidence=False), {})
    assert problems == ["The text uses [1] but there is no citation 1."]


# --- reporting ---------------------------------------------------------------


def test_every_broken_rule_is_reported_at_once_so_the_model_can_fix_them_together():
    """All problems come back in one error, so the agent's single retry can fix them all."""
    seen, invented = chunk(), chunk()
    # The text uses [1] and [3]; citations 1 (an invented chunk) and 2 (a real one) are listed.
    given = answer("Claim [1] and [3].", {1: invented, 2: seen})
    # Three problems at once: citation 1 points at an unretrieved chunk (rule 1),
    # [3] has no citation (rule 3a), citation 2 is never used in the text (rule 3b).
    assert len(problems_of(given, {seen.id: seen})) == 3
