"""Tests for grounding/validator.py: the claim checks, the figure check, and where markers go.

No model, database or network. The "evidence" is what the search tools showed the model this
turn: the retrieved chunks and the short id ("S1", "S2"...) each was given. The model returns
claims; `ground` checks each one against its cited passages and writes the answer text, with the
marker right after each claim.
"""

from uuid import uuid4

import pytest

from app.assistant.outputs import Claim, ModelAnswer
from app.grounding.validator import (
    MAX_CITATIONS,
    MAX_NOTES,
    Figure,
    GroundingError,
    figure_in_passage,
    figures_in,
    ground,
    numbers_in,
    sentence_count,
)
from app.retrieval.queries import ChunkHit

# --- helpers -----------------------------------------------------------------

APPLE_TABLE = (
    "| Net sales by category | 2021 | Change | 2020 | Change | 2019 |\n"
    "| iPhone (1) | 191,973 | 39% | 137,781 | (3)% | 142,381 |\n"
    "| Services (3) | 68,425 | 27% | 53,768 | 16% | 46,291 |"
)


def chunk(text: str = APPLE_TABLE, fiscal_year: int = 2025) -> ChunkHit:
    """A fake retrieved chunk (an Apple 10-K passage) with a fresh random id."""
    # Positional fields: chunk id, document id, chunk index, text, section,
    # ticker, form, fiscal year, filing date, accession number.
    return ChunkHit(uuid4(), uuid4(), 1, text, "Item 7", "AAPL", "10-K", fiscal_year, "2025-10-31", "acc")


def evidence(*chunks: ChunkHit) -> tuple[dict, dict]:
    """What the tools showed: the retrieved chunks, and their short ids S1, S2... in order."""
    return {c.id: c for c in chunks}, {c.id: f"S{n}" for n, c in enumerate(chunks, start=1)}


def fact(text: str, *sources: str) -> Claim:
    return Claim(kind="fact", text=text, sources=list(sources))


def note(text: str) -> Claim:
    return Claim(kind="note", text=text)


def answer(*claims: Claim, enough: bool = True) -> ModelAnswer:
    return ModelAnswer(claims=list(claims), enough_evidence=enough)


def problems_of(given: ModelAnswer, shown: tuple[dict, dict]) -> list[str]:
    """Run `ground`, expect it to reject the answer, and return the listed problems."""
    with pytest.raises(GroundingError) as raised:  # the test fails if nothing is raised
        ground(given, *shown)
    return raised.value.problems


# --- where the markers go ----------------------------------------------------


def test_each_marker_sits_right_after_its_own_figure():
    """The point of the design: a marker follows the figure it backs, never a block at the end."""
    shown = evidence(chunk("Net sales were $209,586 million."), chunk("Net sales were $201,183 million."))
    given = answer(
        fact("Apple's iPhone net sales were $209,586 million in fiscal 2025", "S1"),
        fact(", up from $201,183 million in fiscal 2024.", "S2"),
    )

    grounded, _ = ground(given, *shown)

    assert grounded.answer == (
        "Apple's iPhone net sales were $209,586 million[1] in fiscal 2025, up from $201,183 million[2] in fiscal 2024."
    )


def test_markers_are_numbered_in_order_of_first_use_and_the_citations_match():
    """S2 is used first, so it becomes [1]; passages come back in marker order."""
    first, second = chunk("iPhone text 191,973"), chunk("Services text 68,425")
    shown = evidence(first, second)  # S1 = first, S2 = second
    given = answer(
        fact("Services grew to $68,425 million.", "S2"),
        fact("iPhone was $191,973 million.", "S1"),
    )

    grounded, passages = ground(given, *shown)

    assert grounded.answer == "Services grew to $68,425 million[1]. iPhone was $191,973 million[2]."
    assert [(c.marker, c.source_id) for c in grounded.citations] == [(1, "S2"), (2, "S1")]
    assert [p.excerpt for p in passages] == ["Services text 68,425", "iPhone text 191,973"]
    assert passages[0].chunk_id == second.id  # the UI opens the exact passage


def test_a_source_used_twice_keeps_one_number():
    shown = evidence(chunk())
    given = answer(
        fact("iPhone net sales were $191,973 million.", "S1"),
        fact("Services net sales were $68,425 million.", "S1"),
    )

    grounded, passages = ground(given, *shown)

    assert grounded.answer == "iPhone net sales were $191,973 million[1]. Services net sales were $68,425 million[1]."
    assert len(passages) == 1


def test_a_claim_on_two_passages_gets_both_markers_before_its_full_stop():
    shown = evidence(chunk("Customers include cloud providers."), chunk("Customer A was 13% of revenue."))
    given = answer(fact("Large cloud providers are the main customers.", "S1", "S2"))

    grounded, _ = ground(given, *shown)

    assert grounded.answer == "Large cloud providers are the main customers[1][2]."


def test_notes_carry_no_marker_and_list_items_keep_their_lines():
    """Framing text has no marker; a bullet list stays a list, with a marker on each line."""
    shown = evidence(chunk())
    given = answer(
        note("Here is what the filings say:"),
        fact("\n- iPhone: $191,973 million", "S1"),
        fact("\n- Services: $68,425 million", "S1"),
    )

    grounded, _ = ground(given, *shown)

    assert grounded.answer == "Here is what the filings say:\n- iPhone: $191,973 million[1]\n- Services: $68,425 million[1]"


def test_an_honest_not_enough_evidence_answer_needs_no_sources():
    given = answer(note("The filings do not say."), enough=False)
    grounded, passages = ground(given, {}, {})
    assert grounded.answer == "The filings do not say." and grounded.citations == [] and passages == []


# --- sources -----------------------------------------------------------------


def test_citing_a_source_no_search_showed_is_rejected():
    problems = problems_of(answer(fact("iPhone was $191,973 million.", "S9")), evidence(chunk()))
    assert len(problems) == 1 and "S9" in problems[0] and "no search returned" in problems[0]


def test_a_fact_without_sources_is_rejected():
    problems = problems_of(answer(fact("iPhone sales are large.")), evidence(chunk()))
    assert "has no sources" in problems[0]


def test_more_than_eight_sources_on_one_claim_is_rejected_by_the_schema():
    """The model cannot even return a claim with nine sources."""
    with pytest.raises(ValueError):
        Claim(kind="fact", text="x", sources=[f"S{n}" for n in range(1, 10)])


# --- figures -----------------------------------------------------------------


def test_a_figure_the_cited_passage_does_not_contain_is_rejected():
    """The correctness check: 191,974 is not in the passage, so the claim was mis-copied or invented."""
    problems = problems_of(answer(fact("iPhone net sales were $191,974 million.", "S1")), evidence(chunk()))
    assert len(problems) == 1 and "$191,974 million" in problems[0] and "none of its cited passages" in problems[0]


def test_a_figure_that_is_in_another_passage_is_rejected_for_the_wrong_citation():
    """The figure exists in S2 but the claim cites S1: the marker would point at the wrong filing."""
    shown = evidence(chunk("Revenue was 100 million"), chunk("iPhone was 191,973"))
    problems = problems_of(answer(fact("iPhone net sales were $191,973 million.", "S1")), shown)
    assert "none of its cited passages" in problems[0]


@pytest.mark.parametrize(
    ("claim", "accepted"),
    [
        ("iPhone net sales were $191,973 million.", True),  # exact
        ("iPhone net sales were about $192.0 billion.", True),  # 191,973 million to billions, one decimal
        ("iPhone net sales were about $191.9 billion.", False),  # does not round from 191,973
        ("iPhone net sales grew 39%.", True),  # a percentage in the table
        ("iPhone net sales grew 40%.", False),
        ("In fiscal 2021 iPhone net sales fell 3%.", True),  # "(3)%" in the table; the year is not a figure
    ],
)
def test_figures_are_matched_exactly_or_by_unit_conversion_only(claim, accepted):
    shown = evidence(chunk())
    if accepted:
        ground(answer(fact(claim, "S1")), *shown)
    else:
        assert "none of its cited passages" in problems_of(answer(fact(claim, "S1")), shown)[0]


def test_years_and_item_numbers_are_not_figures():
    """"fiscal 2024", "Item 7" and "10-K" are labels, so a claim with no real figure passes."""
    given = answer(fact("In fiscal 2024 the Item 7 discussion of the 10-K covers net sales.", "S1"))
    grounded, _ = ground(given, *evidence(chunk()))
    assert grounded.citations[0].source_id == "S1"


def test_each_figure_gets_its_own_marker_from_the_passage_that_contains_it():
    """Two figures from two passages in one sentence: the program puts each marker right after its figure."""
    shown = evidence(chunk("iPhone net sales were 191,973 in 2021."), chunk("Services net sales were 68,425 in 2021."))
    given = answer(fact("iPhone net sales were $191,973 million and Services net sales were $68,425 million.", "S1", "S2"))

    grounded, _ = ground(given, *shown)

    assert grounded.answer == (
        "iPhone net sales were $191,973 million[1] and Services net sales were $68,425 million[2]."
    )


def test_the_model_listing_sources_in_a_different_order_does_not_move_the_markers():
    """S2 is listed first but its figure comes second: the marker follows the figure, and numbers follow the text."""
    shown = evidence(chunk("iPhone net sales were 191,973."), chunk("Services net sales were 68,425."))
    given = answer(fact("iPhone net sales were $191,973 million and Services were $68,425 million.", "S2", "S1"))

    grounded, _ = ground(given, *shown)

    assert grounded.answer == "iPhone net sales were $191,973 million[1] and Services were $68,425 million[2]."
    assert [(c.marker, c.source_id) for c in grounded.citations] == [(1, "S1"), (2, "S2")]


def test_figures_from_one_passage_that_are_far_apart_each_get_a_marker():
    """"$191,973 million in fiscal 2021 and ... $68,425 million": too far apart to share, so both are marked."""
    given = answer(fact("iPhone net sales were $191,973 million in fiscal 2021 and Services net sales were $68,425 million.", "S1"))
    grounded, _ = ground(given, *evidence(chunk()))
    assert grounded.answer == (
        "iPhone net sales were $191,973 million[1] in fiscal 2021 and Services net sales were $68,425 million[1]."
    )


def test_a_range_from_one_passage_shares_a_single_marker():
    shown = evidence(chunk("Capital investments of $1.10 billion to $1.30 billion are expected."))
    grounded, _ = ground(answer(fact("NVIDIA expects $1.10 billion to $1.30 billion of capital investment.", "S1")), *shown)
    assert grounded.answer == "NVIDIA expects $1.10 billion to $1.30 billion[1] of capital investment."


def test_consecutive_figures_from_one_passage_share_one_marker_after_the_last():
    given = answer(fact("iPhone net sales were $191,973 million, up 39%.", "S1"))
    grounded, _ = ground(given, *evidence(chunk()))
    assert grounded.answer == "iPhone net sales were $191,973 million, up 39%[1]."


def test_a_cited_passage_with_no_figure_in_the_claim_gets_its_marker_at_the_end():
    """The second source backs the non-numeric part, so its marker goes at the end of the claim."""
    shown = evidence(chunk(), chunk("Apple designs its products in California."))
    given = answer(fact("iPhone net sales were $191,973 million and Apple designs its products itself.", "S1", "S2"))

    grounded, _ = ground(given, *shown)

    assert grounded.answer == "iPhone net sales were $191,973 million[1] and Apple designs its products itself[2]."


def test_when_two_cited_filings_contain_a_figure_the_year_next_to_it_picks_the_filing():
    """191,973 is in both the fiscal 2021 filing and the 2022 one (a prior-year column): the year decides."""
    fy2022 = chunk("2022: iPhone 205,489. 2021: iPhone 191,973.", fiscal_year=2022)
    fy2021 = chunk("2021: iPhone 191,973.", fiscal_year=2021)
    shown = evidence(fy2022, fy2021)  # S1 = fiscal 2022 filing, S2 = fiscal 2021 filing
    given = answer(fact("iPhone net sales were $191,973 million in fiscal 2021.", "S1", "S2"))

    grounded, passages = ground(given, *shown)

    assert grounded.answer == "iPhone net sales were $191,973 million[1] in fiscal 2021."
    assert grounded.citations[0].source_id == "S2" and passages[0].fiscal_year == 2021


def test_a_figure_none_of_the_cited_passages_contain_is_rejected_even_if_another_passage_has_it():
    shown = evidence(chunk("Revenue was 100."), chunk("Services were 200."), chunk("iPhone was 191,973."))
    given = answer(fact("iPhone net sales were $191,973 million.", "S1", "S2"))  # S3 has it but is not cited
    assert "none of its cited passages" in problems_of(given, shown)[0]


def test_a_claim_with_too_many_figures_is_rejected():
    figures = ", ".join(f"${n},000 million" for n in range(1, 8))
    problems = problems_of(answer(fact(f"Sales were {figures}.", "S1")), evidence(chunk(" ".join(f"{n},000" for n in range(1, 8)))))
    assert "Use at most 6 per claim" in problems[0]


def test_a_calculation_must_show_an_input_from_its_sources():
    shown = evidence(chunk())
    ok = answer(Claim(kind="calculation", text="Services were 68,425 of 260,174, or 26%.", sources=["S1"]))
    assert ground(ok, *shown)[0].answer == "Services were 68,425 of 260,174, or 26%[1]."  # 68,425 is in S1

    bad = answer(Claim(kind="calculation", text="The share was 26% (1,000 / 3,846).", sources=["S1"]))
    assert "none of its figures is in its sources" in problems_of(bad, shown)[0]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Sales were $201,183 million in fiscal 2024", [201183.0]),
        ("Margin was 28.5% and sales $5.2 billion", [28.5, 5.2]),
        ("Item 7 of the 10-K for fiscal 2024", []),
        ("A drop of (3)%", [3.0]),
    ],
)
def test_figures_in_a_claim(text, expected):
    assert [figure.value for figure in figures_in(text)] == expected


def test_numbers_in_a_passage_include_table_cells():
    assert {191973.0, 39.0, 137781.0, 3.0}.issubset(numbers_in(APPLE_TABLE))


def test_unit_conversion_is_limited_to_million_and_billion():
    assert figure_in_passage(Figure(201.2, 1, "billion", "$201.2 billion"), {201183.0})
    assert not figure_in_passage(Figure(201.3, 1, "billion", "$201.3 billion"), {201183.0})
    assert not figure_in_passage(Figure(201.2, 1, "%", "201.2%"), {201183.0})


# --- one claim, one sentence -------------------------------------------------


def test_a_claim_with_two_sentences_is_rejected():
    given = answer(fact("iPhone net sales rose. Services net sales also rose.", "S1"))
    assert "more than one sentence" in problems_of(given, evidence(chunk()))[0]


@pytest.mark.parametrize(
    ("text", "count"),
    [
        ("Sales rose 7%.", 1),
        ("U.S. net sales rose, and Apple Inc. said so.", 1),  # abbreviations do not end a sentence
        ("Sales rose. Costs fell.", 2),
        ("- iPhone\n- Mac", 2),
    ],
)
def test_sentence_count(text, count):
    assert sentence_count(text) == count


# --- notes -------------------------------------------------------------------


def test_a_note_cannot_have_sources_or_figures_or_be_long():
    shown = evidence(chunk())
    backed = fact("iPhone was $191,973 million.", "S1")
    with_sources = Claim(kind="note", text="A framing sentence.", sources=["S1"])
    assert "lists sources" in problems_of(answer(with_sources, backed), shown)[0]
    assert "states a figure" in problems_of(answer(note("Sales were $5 billion."), backed), shown)[0]
    assert "over 400 characters" in problems_of(answer(note("a" * 401), backed), shown)[0]


def test_too_many_notes_in_an_answer_that_claims_evidence_are_rejected():
    claims = [note(f"Framing sentence number {n} goes here.") for n in range(MAX_NOTES + 1)]
    given = answer(*claims, fact("iPhone was $191,973 million.", "S1"))
    assert f"at most {MAX_NOTES}" in problems_of(given, evidence(chunk()))[0]


# --- ids and markers belong to the program -----------------------------------


@pytest.mark.parametrize(
    "leaked", ["see [1]", "from S1 [S1]", "chunk_id 5", "5884b293-95b8-42b6-87fb-2d00da4c0a2b says"]
)
def test_an_id_or_marker_written_into_a_claim_is_rejected(leaked):
    problems = problems_of(answer(fact(f"iPhone sales rose, {leaked}.", "S1")), evidence(chunk()))
    assert "contains an id or a [1]-style marker" in problems[0]


# --- across the answer -------------------------------------------------------


def test_claiming_enough_evidence_with_only_notes_is_rejected():
    problems = problems_of(answer(note("Apple grew.")), ({}, {}))
    assert "enough_evidence is true but no claim is a fact" in problems[0]


def test_the_same_claim_written_twice_is_rejected():
    text = "Apple's iPhone net sales were $191,973 million in fiscal 2021."
    given = answer(fact(text, "S1"), fact(text, "S1"))
    assert "written more than once" in problems_of(given, evidence(chunk()))[0]


def test_more_than_the_maximum_number_of_sources_is_rejected():
    count = MAX_CITATIONS + 1
    chunks = [chunk(f"Fact number {n} is {n},000 here.") for n in range(1, count + 1)]
    claims = [fact(f"Item {n} says {n},000.", f"S{n}") for n in range(1, count + 1)]
    problems = problems_of(answer(*claims), evidence(*chunks))
    assert any(f"cites {count} passages" in problem for problem in problems)


def test_every_broken_rule_is_reported_at_once_so_the_model_can_fix_them_together():
    given = answer(
        fact("iPhone was $191,974 million.", "S1"),  # figure not in passage
        fact("Services grew.", "S9"),  # unknown source
        fact("Mac grew."),  # no sources
    )
    assert len(problems_of(given, evidence(chunk()))) == 3
