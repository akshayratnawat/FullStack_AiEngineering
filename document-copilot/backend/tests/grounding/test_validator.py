"""Tests for grounding/validator.py: one test per rule, plus the passing cases.

No model, database or network. The "evidence" below stands for what the search tools showed
the model this turn: the retrieved chunks and the short id ("S1", "S2"...) each was given.
The validator accepts a citation only if its source_id is one of those.

Rules under test (numbered as in the validator's docstring):
  1. every citation uses a source_id a tool showed this turn
  2. each marker number is used by one citation only
  3. text markers and citations agree both ways (3a: marker without citation,
     3b: citation without marker)
  4. enough_evidence=True needs at least one citation
  5. format: no ids in the text, no block of four or more markers, no figure without a marker
"""

from uuid import uuid4

import pytest

from app.assistant.outputs import Citation, GroundedAnswer, ModelAnswer
from app.grounding.validator import GroundingError, ground, validate
from app.retrieval.queries import ChunkHit

# --- helpers -----------------------------------------------------------------


def chunk(text: str = "text") -> ChunkHit:
    """A fake retrieved chunk (an Apple 10-K passage) with a fresh random id."""
    # Positional fields: chunk id, document id, chunk index, text, section,
    # ticker, form, fiscal year, filing date, accession number.
    return ChunkHit(uuid4(), uuid4(), 1, text, "Item 7", "AAPL", "10-K", 2025, "2025-10-31", "acc")


def evidence(*chunks: ChunkHit) -> tuple[dict, dict]:
    """What the tools showed: the retrieved chunks, and their short ids S1, S2... in order."""
    retrieved = {c.id: c for c in chunks}
    labels = {c.id: f"S{number}" for number, c in enumerate(chunks, start=1)}
    return retrieved, labels


def answer(text: str, markers_to_sources: dict[int, str], enough: bool = True) -> GroundedAnswer:
    """Build an answer whose citations are {marker number: the source_id it cites}."""
    citations = [Citation(marker=m, source_id=s) for m, s in markers_to_sources.items()]
    return GroundedAnswer(answer=text, citations=citations, enough_evidence=enough)


def problems_of(given: GroundedAnswer, shown: tuple[dict, dict]) -> list[str]:
    """Run the validator, expect it to reject the answer, and return the listed problems."""
    with pytest.raises(GroundingError) as raised:  # the test fails if nothing is raised
        validate(given, *shown)
    return raised.value.problems


# --- passing cases -----------------------------------------------------------


def test_a_grounded_answer_returns_its_passages_in_marker_order():
    """A valid answer passes; passages come back ordered by marker, whatever order they were cited in."""
    first, second = chunk("iPhone text"), chunk("Services text")
    shown = evidence(first, second)  # S1 = first, S2 = second
    # Marker 2 is listed before marker 1 on purpose, to check the ordering.
    given = answer("Services grew [2]. iPhone fell [1].", {2: "S2", 1: "S1"})

    passages = validate(given, *shown)

    # Marker 1 (iPhone) must come first even though it was cited second.
    assert [p.excerpt for p in passages] == ["iPhone text", "Services text"]
    # The passage carries the filing details the UI needs, copied from the chunk.
    assert passages[0].ticker == "AAPL" and passages[0].chunk_id == first.id


def test_an_honest_not_enough_evidence_answer_needs_no_citations():
    """Saying "the filings do not say" with no citations is allowed (enough_evidence=False)."""
    given = GroundedAnswer(answer="The filings do not say.", enough_evidence=False)
    # Nothing was retrieved and nothing is cited: it passes and returns no passages.
    assert validate(given, {}, {}) == []


def test_a_bracketed_year_is_not_a_citation_marker():
    """A bracketed year like [2024] has four digits, so it is ordinary text, not a marker."""
    given = answer("Revenue in [2024] rose [1].", {1: "S1"})
    # If [2024] were read as a marker it would need a citation 2024 and be rejected.
    assert len(validate(given, *evidence(chunk()))) == 1


def test_one_marker_per_claim_in_a_list_passes_the_format_rules():
    """Figures that each have their own marker, in a list, are the format we want."""
    shown = evidence(chunk(), chunk(), chunk())
    text = "- iPhone: $209,586 million [1]\n- Mac: $33,708 million [2]\n- iPad: $28,023 million [3]"
    assert len(validate(answer(text, {1: "S1", 2: "S2", 3: "S3"}), *shown)) == 3


# --- one test per rejection rule ---------------------------------------------


def test_citing_a_source_no_search_showed_is_rejected():
    """Rule 1: a cited source_id that no tool showed was invented or remembered, not found."""
    given = answer("A claim [1].", {1: "S9"})  # S9 was never shown
    problems = problems_of(given, evidence(chunk()))  # only S1 exists
    # Exactly one problem, and it names the offending id.
    assert len(problems) == 1 and "S9" in problems[0]


def test_two_citations_sharing_a_marker_are_rejected():
    """Rule 2: [1] must mean one source, so two citations can't both be number 1."""
    given = GroundedAnswer(
        answer="Claim [1].",
        # Two different sources, both numbered 1. Built by hand: `answer()` uses a dict,
        # which cannot hold the same marker twice.
        citations=[Citation(marker=1, source_id="S1"), Citation(marker=1, source_id="S2")],
        enough_evidence=True,
    )
    assert "Marker [1] is used by more than one citation" in problems_of(given, evidence(chunk(), chunk()))[0]


def test_a_marker_in_the_text_without_a_citation_is_rejected():
    """Rule 3a: the text says [2] but no citation 2 exists, so that claim has no source."""
    # The text uses [1] and [2]; only citation 1 exists.
    problems = problems_of(answer("Claim [1] and another [2].", {1: "S1"}), evidence(chunk()))
    assert problems == ["The text uses [2] but there is no citation 2."]


def test_a_citation_never_used_in_the_text_is_rejected():
    """Rule 3b: citation 2 is listed but nothing in the text points at it."""
    # Two citations are listed, but the text only uses [1].
    given = answer("Claim [1].", {1: "S1", 2: "S2"})
    problems = problems_of(given, evidence(chunk(), chunk()))  # both sources are real
    assert problems == ["Citation 2 is listed but [2] never appears in the answer text."]


def test_claiming_enough_evidence_without_any_citation_is_rejected():
    """Rule 4: an answer that says it has evidence must show at least one source."""
    # A confident answer with no sources at all: the exact failure grounding exists to stop.
    problems = problems_of(GroundedAnswer(answer="Apple grew.", enough_evidence=True), ({}, {}))
    assert "enough_evidence is true but there are no citations" in problems[0]


def test_not_enough_evidence_cannot_use_markers_it_does_not_back():
    """Rule 3a still applies to a "not enough evidence" answer: a stray [1] with no citation is rejected."""
    # enough_evidence=False excuses having no citations, but not a dangling [1] in the text.
    problems = problems_of(GroundedAnswer(answer="Maybe [1].", enough_evidence=False), ({}, {}))
    assert problems == ["The text uses [1] but there is no citation 1."]


# --- rule 5: format ----------------------------------------------------------


@pytest.mark.parametrize(
    "leaked",
    [
        "see chunk_id 123",
        "from source_id S1",
        "as shown in [S1]",
        "the source is [1] S37",  # a source list written into the answer
        "chunk 5884b293-95b8-42b6-87fb-2d00da4c0a2b says",
    ],
)
def test_an_id_written_into_the_text_is_rejected(leaked):
    """Rule 5: sources are shown from `citations`; an id in the answer text is noise to the analyst."""
    given = answer(f"Apple grew [1], {leaked}.", {1: "S1"})
    problems = problems_of(given, evidence(chunk()))
    assert len(problems) == 1 and "contains a chunk_id, source_id or [S1]-style id" in problems[0]


def test_a_dump_of_ten_markers_is_rejected_but_a_five_year_trend_on_five_passages_is_fine():
    """Rule 5: a dump of markers is not a citation per claim; five passages for one trend is."""
    shown = evidence(*[chunk() for _ in range(10)])
    block = answer("Many things grew " + "".join(f"[{n}]" for n in range(1, 11)) + ".", {n: f"S{n}" for n in range(1, 11)})
    assert "ten or more markers in a row" in problems_of(block, shown)[0]

    trend = answer("Net sales rose every year [1][2][3][4][5].", {n: f"S{n}" for n in range(1, 6)})
    assert len(validate(trend, *evidence(*[chunk() for _ in range(5)]))) == 5


@pytest.mark.parametrize("claim", ["Sales were $5 billion.", "Margin rose 3%.", "Revenue was 201,183 million.", "Sales hit 5.2 billion."])
def test_a_paragraph_with_a_figure_and_no_marker_is_rejected(claim):
    """Rule 5: a figure is a factual claim, so the paragraph that states it must cite something."""
    # The first paragraph is cited; the second states a figure with no marker.
    given = answer(f"iPhone sold well [1].\n\n{claim}", {1: "S1"})
    problems = problems_of(given, evidence(chunk()))
    assert len(problems) == 1 and "states a figure but has no citation marker" in problems[0]


def test_a_paragraph_without_figures_may_go_uncited():
    """Rule 5 only targets figures: an uncited framing sentence or a clarifying question is fine."""
    given = answer("Here is what the filings say.\n\niPhone sales were $5 billion [1].", {1: "S1"})
    assert len(validate(given, *evidence(chunk()))) == 1


def test_a_year_alone_is_not_a_figure():
    """Rule 5: "fiscal 2024" is a label, not a claim, so a paragraph with only years needs no marker."""
    given = answer("Fiscal 2024 and fiscal 2025 are compared below.\n\niPhone sold well [1].", {1: "S1"})
    assert len(validate(given, *evidence(chunk()))) == 1


# --- reporting ---------------------------------------------------------------


def test_every_broken_rule_is_reported_at_once_so_the_model_can_fix_them_together():
    """All problems come back in one error, so the agent's single retry can fix them all."""
    # The text uses [1] and [3]; citations 1 (an unknown source) and 2 (a real one) are listed.
    given = answer("Claim [1] and [3].", {1: "S9", 2: "S1"})
    # Three problems at once: citation 1 uses an unknown source (rule 1),
    # [3] has no citation (rule 3a), citation 2 is never used in the text (rule 3b).
    assert len(problems_of(given, evidence(chunk()))) == 3


def test_the_same_sentence_repeated_once_per_source_is_rejected():
    """Rule 5: repeating one claim with a new marker each time is padding, not citation."""
    sentence = "Apple reports gross margin changes from product mix but does not tie them to generative AI"
    text = " ".join(f"{sentence} [{n}]." for n in range(1, 4))
    shown = evidence(*[chunk() for _ in range(3)])
    problems = problems_of(answer(text, {n: f"S{n}" for n in range(1, 4)}), shown)
    assert len(problems) == 1 and "is written more than once with different markers" in problems[0]


def test_more_than_the_maximum_number_of_citations_is_rejected():
    """Rule 5: an answer may not lean on more than MAX_CITATIONS passages."""
    from app.grounding.validator import MAX_CITATIONS

    count = MAX_CITATIONS + 1
    text = " ".join(f"Claim number {n} is made here in its own words [{n}]." for n in range(1, count + 1))
    shown = evidence(*[chunk() for _ in range(count)])
    problems = problems_of(answer(text, {n: f"S{n}" for n in range(1, count + 1)}), shown)
    assert len(problems) == 1 and f"The answer cites {count} passages. Cite at most {MAX_CITATIONS}" in problems[0]


# --- ground(): the model writes [S3], the program numbers the markers ---------


def model_answer(text: str, enough: bool = True) -> ModelAnswer:
    """What the model returns: text with [S1]-style markers and the evidence flag, no citation list."""
    return ModelAnswer(answer=text, enough_evidence=enough)


def test_markers_are_numbered_in_order_of_first_use_and_citations_are_built():
    """S2 is used first, so it becomes [1]; reusing a source keeps its number."""
    first, second = chunk("iPhone text"), chunk("Services text")
    shown = evidence(first, second)  # S1 = first, S2 = second

    grounded, passages = ground(model_answer("Services grew [S2]. iPhone fell [S1]. Services again [S2]."), *shown)

    assert grounded.answer == "Services grew [1]. iPhone fell [2]. Services again [1]."
    assert [(c.marker, c.source_id) for c in grounded.citations] == [(1, "S2"), (2, "S1")]
    assert [p.excerpt for p in passages] == ["Services text", "iPhone text"]  # marker order


def test_a_group_of_sources_in_one_bracket_becomes_separate_markers():
    """[S1, S2] and [S1][S2] mean the same: one claim on two passages."""
    shown = evidence(chunk(), chunk())

    grounded, _ = ground(model_answer("A claim on two passages [S1, S2]."), *shown)

    assert grounded.answer == "A claim on two passages [1][2]."


def test_a_source_list_written_into_the_text_is_removed_not_refused():
    """A trailing "Sources:" heading and "[1] S37"-style lines are cleaned up; the answer still passes."""
    shown = evidence(chunk())
    text = "Apple grew [S1].\n\nSources:\n[1] S1 Apple 10-K fiscal 2025\n"

    grounded, _ = ground(model_answer(text), *shown)

    assert grounded.answer == "Apple grew [1]."


def test_a_source_id_no_search_showed_is_rejected():
    """[S9] was never shown: rule 1 still applies, now to the id the model wrote in the text."""
    with pytest.raises(GroundingError) as raised:
        ground(model_answer("A claim [S9]."), *evidence(chunk()))
    assert "S9" in raised.value.problems[0]


def test_numbered_markers_written_by_the_model_are_rejected_with_the_instruction():
    """The numbering is the program's job; [1] from the model is sent back with how to cite."""
    with pytest.raises(GroundingError) as raised:
        ground(model_answer("A claim [1]."), *evidence(chunk()))
    assert "Write the source_id as the marker, like [S3]" in raised.value.problems[0]


def test_an_honest_not_enough_evidence_answer_passes_ground_with_no_markers():
    """No markers, no citations, no passages: allowed when enough_evidence is false."""
    grounded, passages = ground(model_answer("The filings do not say.", enough=False), {}, {})
    assert grounded.citations == [] and passages == []
