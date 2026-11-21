"""The trust contract, in code: an answer is only accepted if its citations are real.

No model is involved. The checks compare the agent's `GroundedAnswer` with the chunks
the search tools actually returned this turn (`DocumentAgentDeps.retrieved`), so a model
that invents or mis-numbers a source is caught regardless of how convincing it sounds.

The error message is written for the model, not the user: Step 5 hands it back to the
agent for one retry, so it says exactly what to fix.
"""

import re
from uuid import UUID

from app.assistant.outputs import Citation, GroundedAnswer, ModelAnswer, SourcePassage
from app.retrieval.queries import ChunkHit

# A citation marker in the text: [1], [12]. At most 3 digits, so a bracketed year such as
# "[2024]" is never mistaken for one.
MARKER = re.compile(r"\[(\d{1,3})\]")

# Format rules (rule 5). The answer text is for the analyst: sources are shown from `citations`,
# so ids must not leak into it, markers go next to their claim, and a figure needs a source.
LEAKED_ID = re.compile(
    r"chunk_id|source_id|\[S\d+\]|\[\d{1,3}\]\s*S\d+\b|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)
MARKER_RUN = re.compile(r"(?:\[\d{1,3}\]\s*){10,}")  # [1]...[10]: a dump of markers, not one per claim
# A number that is clearly a claim: money, a percentage, a grouped number like 201,183, or "n billion".
# What the model writes: [S3], or a group [S3, S5]. The program turns these into [1], [2]...
SOURCE_MARKER = re.compile(r"\[(S\d{1,3})\]")
SOURCE_GROUP = re.compile(r"\[(S\d{1,3}(?:\s*[,;]\s*S\d{1,3})+)\]")
# A source list the model wrote into the text anyway ("[1] S37", "1. S3 Apple 10-K", or a "Sources:"
# heading). It is removed rather than refused: the app shows the sources itself.
SOURCE_LIST_LINE = re.compile(
    r"^[ \t]*(?:\[\d{1,3}\]|\d{1,3}[.)])[ \t]*\[?S\d{1,3}\]?\b.*$|^[ \t]*(?:sources?|references?)(?: cited)?:?[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")
MAX_CITATIONS = 40  # a question across eight companies and five years needs many sources; more than this is padding
FIGURE = re.compile(r"\$\s?\d|\d\s?%|\d{1,3}(?:,\d{3})+|\d(?:\.\d+)?\s?(?:billion|million|thousand)\b", re.IGNORECASE)


class GroundingError(Exception):
    """The answer broke the grounding rules. `problems` lists every rule it broke."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("The answer is not properly grounded:\n- " + "\n- ".join(problems))


def tidy(text: str) -> str:
    """Remove what can be fixed without asking the model again: a source list written into the text."""
    return re.sub(r"\n{3,}", "\n\n", SOURCE_LIST_LINE.sub("", text)).strip()


def ground(
    answer: ModelAnswer, retrieved: dict[UUID, ChunkHit], labels: dict[UUID, str]
) -> tuple[GroundedAnswer, list[SourcePassage]]:
    """Check what the model wrote and number its markers.

    The model marks each claim with the id of its source, `[S3]`. This renumbers those
    markers `[1]`, `[2]`... in order of first use, builds the citation list itself, and then
    applies every rule in `validate`. Returns the checked answer and the cited passages in
    marker order, or raises `GroundingError`.
    """
    text = tidy(answer.answer)
    if MARKER.search(text):
        # The model numbered the markers itself; the numbering is the program's job.
        raise GroundingError(
            [("The text has numbered markers such as [1]. Write the source_id as the marker, like [S3]: "
              "the app numbers the markers itself.")]
        )
    text = SOURCE_GROUP.sub(
        lambda match: "".join(f"[{part.strip()}]" for part in re.split(r"[,;]", match.group(1))), text
    )
    order: list[str] = []  # source ids in order of first use
    for source_id in SOURCE_MARKER.findall(text):
        if source_id not in order:
            order.append(source_id)
    number = {source_id: position for position, source_id in enumerate(order, start=1)}
    text = SOURCE_MARKER.sub(lambda match: f"[{number[match.group(1)]}]", text)

    grounded = GroundedAnswer(
        answer=text,
        enough_evidence=answer.enough_evidence,
        citations=[Citation(marker=number[source_id], source_id=source_id) for source_id in order],
    )
    return grounded, validate(grounded, retrieved, labels)


def validate(
    answer: GroundedAnswer, retrieved: dict[UUID, ChunkHit], labels: dict[UUID, str]
) -> list[SourcePassage]:
    """Return the cited passages in marker order, or raise `GroundingError`.

    `labels` maps each retrieved chunk to the short id the model was shown ("S1"...).

    Rules:
    1. Every citation's source_id is one a search tool showed this turn.
    2. Each marker number is used by one citation only.
    3. Every [n] in the text has a citation, and every citation's [n] appears in the text.
    4. An answer that claims enough evidence cites at least one passage.
    5. Format: no ids in the text, no block of ten or more markers, no repeated sentence, at
       most MAX_CITATIONS citations, and no paragraph that states a figure without a marker.
    """
    problems: list[str] = []
    by_label = {label: retrieved[chunk_id] for chunk_id, label in labels.items() if chunk_id in retrieved}

    # Rule 1: no source the model did not actually see.
    for citation in answer.citations:
        if citation.source_id not in by_label:
            problems.append(
                f"Citation [{citation.marker}] uses source_id {citation.source_id}, which no search "
                "returned. Cite only source_ids that appear in search results (like S1)."
            )

    # Rule 2: one citation per marker number.
    numbers = [citation.marker for citation in answer.citations]
    for number in sorted({n for n in numbers if numbers.count(n) > 1}):
        problems.append(f"Marker [{number}] is used by more than one citation. Give each source its own number.")

    # Rule 3: the text and the citation list must agree, in both directions.
    used_in_text = {int(n) for n in MARKER.findall(answer.answer)}
    for number in sorted(used_in_text - set(numbers)):
        problems.append(f"The text uses [{number}] but there is no citation {number}.")
    for number in sorted(set(numbers) - used_in_text):
        problems.append(f"Citation {number} is listed but [{number}] never appears in the answer text.")

    # Rule 4: claiming evidence without showing any is not allowed.
    if answer.enough_evidence and not answer.citations:
        problems.append(
            "enough_evidence is true but there are no citations. Cite the passages the answer rests on, "
            "or set enough_evidence to false and say the filings do not support an answer."
        )

    # Rule 5: format.
    problems += format_problems(answer.answer)
    if len(answer.citations) > MAX_CITATIONS:
        problems.append(
            f"The answer cites {len(answer.citations)} passages. Cite at most {MAX_CITATIONS}: pick the "
            "ones that best support each claim, and cite up to three passages for one claim."
        )

    if problems:
        raise GroundingError(problems)

    ordered = sorted(answer.citations, key=lambda citation: citation.marker)
    return [SourcePassage.from_hit(by_label[citation.source_id]) for citation in ordered]


def format_problems(text: str) -> list[str]:
    """Rule 5: the ways an answer's text can be badly cited even when its citations are real."""
    problems: list[str] = []
    if LEAKED_ID.search(text):
        problems.append(
            "The answer text contains a chunk_id, source_id or [S1]-style id. Remove it: write only "
            "[1], [2]... markers; the app shows the sources from `citations`."
        )
    if MARKER_RUN.search(text):
        problems.append(
            "The answer has ten or more markers in a row. Put each marker right after the one claim "
            "it supports, not in a block."
        )
    # The same sentence written once per source is a way round "one marker per claim".
    sentences = [re.sub(r"\s+", " ", MARKER.sub("", sentence)).strip().lower() for sentence in SENTENCE_BREAK.split(text)]
    repeated = {sentence for sentence in sentences if len(sentence) > 40 and sentences.count(sentence) > 1}
    if repeated:
        problems.append(
            f'The sentence "{min(repeated)[:80]}..." is written more than once with different markers. '
            "Say each claim once and cite up to three passages for it."
        )
    # A paragraph is a run of text between blank lines (a list counts as one paragraph).
    for paragraph in re.split(r"\n\s*\n", text):
        if FIGURE.search(paragraph) and not MARKER.search(paragraph):
            problems.append(
                f'A paragraph states a figure but has no citation marker: "{paragraph.strip()[:80]}...". '
                "Cite every figure, or remove the claim."
            )
    return problems
