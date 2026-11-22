"""The trust contract, in code: an answer is only accepted if every statement is backed.

No model is involved. The model returns claims, each with the sources it says support it.
`ground` checks every claim against the chunks the search tools actually returned this turn
(`DocumentAgentDeps.retrieved`), then joins the claims into the answer text and places the
citation markers itself, so a marker always sits next to the thing it backs:
- a figure gets its marker right after it: the program finds which cited passage contains that
  number (if the year next to it names a filing, that filing wins) and attaches that passage;
- a claim with no figure gets its markers at the end of its sentence.

What is checked, per claim:
- a `fact` or `calculation` has sources, every source is one a tool showed this turn, and at
  most three;
- every figure in a `fact` appears in the text of at least one passage the claim cites. A figure
  that none of them contain was invented, mis-copied or taken from a passage that was not cited,
  and the answer is rejected;
- a claim is one sentence;
- a `note` has no sources and no figures, and is short, so a fact cannot hide in one.
Across the answer: no repeated claim, at most MAX_CITATIONS sources, no ids or `[1]` markers
written into the text, and `enough_evidence` needs at least one backed claim.

Two weaker checks only log: a name or distinctive term in a claim that its sources do not
contain. They cannot prove a claim is supported, so they do not reject.

The error message is written for the model, not the user: the agent hands it back for another
try, so it says exactly what to fix.
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from uuid import UUID

import structlog

from app.assistant.outputs import (
    Citation,
    Claim,
    GroundedAnswer,
    ModelAnswer,
    SourcePassage,
)
from app.retrieval.queries import ChunkHit

logger = structlog.get_logger()

MAX_CITATIONS = 40  # distinct sources in one answer; a question across 8 companies needs many
MAX_NOTES = 4  # framing sentences in one answer that say "no source needed"
MAX_NOTE_CHARS = 400  # long enough for "none of the filings state X, and here is what they say instead"
MARKER_GAP = 12  # characters: figures this close from one passage share a marker ("$1.1 billion to $1.3 billion")
MAX_FIGURES = 6  # figures in one claim; more than this is a table, not a sentence

# Ids and markers belong to the program: none may appear in a claim's text.
LEAKED_ID = re.compile(
    r"chunk_id|source_id|\[S\d+\]|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)
WRITTEN_MARKER = re.compile(r"\[\d{1,3}\]")

# A figure in a claim: money, a percentage, a grouped or decimal number, or "n million/billion".
# A bare integer ("Item 7", "fiscal 2024", "3 customers") is not treated as a figure.
FIGURE = re.compile(
    r"(?P<dollar>\$\s?)?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?P<unit>\)?\s?(?:%|(?:billion|million|thousand)\b))?",
    re.IGNORECASE,
)
ANY_NUMBER = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")
YEAR = re.compile(r"\b(?:19|20)\d{2}\b")

# Full stops that do not end a sentence, hidden before counting sentences.
ABBREVIATIONS = re.compile(r"\b(?:U\.S|U\.K|Inc|Corp|Co|Ltd|No|vs|e\.g|i\.e|approx|etc|Mr|Ms|Dr)\.", re.IGNORECASE)
SENTENCE_END = re.compile(r"""[.!?]["')\]]*\s+(?=["'(\[]?[A-Z0-9])""")
CAPITALIZED_TERM = re.compile(r"\b[A-Z][A-Za-z0-9&\-]{2,}\b")


class GroundingError(Exception):
    """The answer broke the grounding rules. `problems` lists every rule it broke."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("The answer is not properly grounded:\n- " + "\n- ".join(problems))


@dataclass(frozen=True)
class Figure:
    value: float
    decimals: int
    unit: str  # "", "%", "million", "billion" or "thousand"
    text: str
    start: int = 0  # where it is in the claim text, so a marker can go right after it
    end: int = 0


def figures_in(text: str) -> list[Figure]:
    """The distinct figures a claim states, in order (the first place each appears)."""
    found: dict[float, Figure] = {}
    for match in FIGURE.finditer(text):
        number, unit = match.group("num"), (match.group("unit") or "").lower().lstrip(") ").strip()
        # A plain integer with no dollar sign, unit, comma or decimal is a label, not a figure.
        if not (match.group("dollar") or unit or "," in number or "." in number):
            continue
        value = float(number.replace(",", ""))
        decimals = len(number.split(".")[1]) if "." in number else 0
        found.setdefault(value, Figure(value, decimals, unit, match.group(0).strip(), match.start(), match.end()))
    return list(found.values())


@lru_cache(maxsize=1024)
def numbers_in(text: str) -> frozenset[float]:
    """Every number written in a passage (table cells included), as plain values."""
    return frozenset(float(match.replace(",", "")) for match in ANY_NUMBER.findall(text))


def figure_in_passage(figure: Figure, passage_numbers: frozenset[float] | set[float]) -> bool:
    """True if the passage contains this figure, allowing the usual unit conversion.

    Filings write tables in millions, so a claim may say "$201.2 billion" for 201,183: a figure
    in billions or millions is also accepted when it equals a passage number divided by 1,000 to
    the precision the claim uses. Anything else (another number, another year's value) is a mismatch.
    """
    if figure.value in passage_numbers:
        return True
    if figure.unit in ("billion", "million"):
        tolerance = 0.5 * 10**-figure.decimals + 1e-9
        return any(abs(number / 1000 - figure.value) <= tolerance for number in passage_numbers)
    return False


def sentence_count(text: str) -> int:
    """How many sentences (or list lines) a claim holds."""
    hidden = ABBREVIATIONS.sub(lambda match: match.group(0).replace(".", ""), text.strip())
    return 1 + len(SENTENCE_END.findall(hidden)) + hidden.count("\n")


def supporting_source(text: str, figure: Figure, sources: list[str], by_label: dict[str, ChunkHit]) -> str | None:
    """Which of a claim's cited passages this figure comes from, or None if none contains it.

    The same number can appear in several filings (a prior-year column), so when more than one
    cited passage contains it, a year written next to the figure ("in fiscal 2021") picks the
    passage of that fiscal year; otherwise the first one the model listed.
    """
    candidates = [s for s in sources if figure_in_passage(figure, numbers_in(by_label[s].content))]
    if len(candidates) > 1:
        year = YEAR.search(text, figure.end, figure.end + 40) or YEAR.search(text[max(0, figure.start - 30) : figure.start])
        if year:
            for source in candidates:
                if by_label[source].fiscal_year == int(year.group(0)):
                    return source
    return candidates[0] if candidates else None


def plan_markers(claim: Claim, by_label: dict[str, ChunkHit]) -> tuple[list[tuple[int, str]], list[str]]:
    """Where a claim's markers go: (position in the text, source) after figures, and sources left for the end.

    Each fact figure gets its marker right after it; a figure immediately followed by another from the same
    passage (a range, or "$5 billion, up 7%") shares the marker of the one after it. Sources that no figure was matched to (the claim's non-numeric
    support) are returned to go at the end of the claim, unless they only repeat a figure already attached. A calculation or a claim with no figure has
    all its markers at the end.
    """
    sources = list(dict.fromkeys(claim.sources))
    figures = figures_in(claim.text) if claim.kind == "fact" else []
    assigned = [(figure, supporting_source(claim.text, figure, sources, by_label)) for figure in figures]
    inline: list[tuple[int, str]] = []
    for index, (figure, source) in enumerate(assigned):
        if source is None:
            continue
        following = assigned[index + 1] if index + 1 < len(assigned) else None
        # Each figure gets its own marker, so the analyst can see which passage a number came from.
        # Only a figure that is immediately followed by another from the same passage (a range, or
        # "$5 billion, up 7%") shares the marker of the one after it.
        if following and following[1] == source and following[0].start - figure.end <= MARKER_GAP:
            continue
        inline.append((figure.end, source))
    placed = {source for _, source in inline}
    # A cited passage that only repeats a figure already attached to another passage (a prior-year
    # column of a later filing) adds nothing next to it, so it is not shown again at the end.
    repeats = {
        source
        for source in sources
        if source not in placed
        and any(figure_in_passage(figure, numbers_in(by_label[source].content)) for figure in figures)
    }
    return inline, [source for source in sources if source not in placed and source not in repeats]


def _preview(claim: Claim) -> str:
    return claim.text.strip().replace("\n", " ")[:70]


def check_claim(position: int, claim: Claim, by_label: dict[str, ChunkHit], *, log: bool) -> list[str]:
    """Every rule one claim can break, worded for the model."""
    where = f'Claim {position} ("{_preview(claim)}...")'
    problems: list[str] = []
    text = claim.text.strip()
    figures = figures_in(text)
    sources = list(dict.fromkeys(claim.sources))

    if LEAKED_ID.search(text) or WRITTEN_MARKER.search(text):
        problems.append(
            f"{where} contains an id or a [1]-style marker. Remove it: the app adds the markers itself."
        )

    if claim.kind == "note":
        if sources:
            problems.append(f"{where} is a note but lists sources. A note has none: make it a fact, or drop the sources.")
        if figures:
            problems.append(f"{where} is a note but states a figure. Make it a fact with its source.")
        if len(text) > MAX_NOTE_CHARS:
            problems.append(f"{where} is a note over {MAX_NOTE_CHARS} characters. Notes are short framing only.")
        return problems

    if not sources:
        problems.append(f"{where} is a {claim.kind} but has no sources. Add the source_id of the passage that says it.")
        return problems
    unknown = [source for source in sources if source not in by_label]
    if unknown:
        problems.append(
            f"{where} cites {', '.join(unknown)}, which no search returned. "
            "Cite only source_ids that appear in search results (like S1)."
        )
        return problems

    if sentence_count(text) > 1:
        problems.append(f"{where} is more than one sentence. Split it so each statement has its own sources.")
    if len(figures) > MAX_FIGURES:
        problems.append(f"{where} states {len(figures)} figures. Use at most {MAX_FIGURES} per claim: split it.")

    # Every figure must be in a passage this claim cites.
    passages = [numbers_in(by_label[source].content) for source in sources]
    missing = [figure for figure in figures if not any(figure_in_passage(figure, numbers) for numbers in passages)]
    if claim.kind == "fact" and missing:
        problems.append(
            f"{where} states {', '.join(figure.text for figure in missing)}, which none of its cited passages "
            f"({', '.join(sources)}) contain. Quote the figure exactly as the passage writes it, cite the "
            "passage that has it, or leave it out."
        )
    if claim.kind == "calculation" and figures and len(missing) == len(figures):
        problems.append(
            f"{where} is a calculation but none of its figures is in its sources. Show at least one input "
            "from the cited passages and cite it."
        )

    if log and claim.kind == "fact":
        source_text = " ".join(by_label[source].content for source in sources).lower()
        unmatched = [term for term in CAPITALIZED_TERM.findall(text)[1:] if term.lower() not in source_text]
        if unmatched:
            logger.warning("claim_terms_not_in_source", claim=text[:120], terms=unmatched[:6], sources=sources)
    return problems


def render(claim: Claim, plan: tuple[list[tuple[int, str]], list[str]], numbers: dict[str, int]) -> str:
    """One claim's text with its markers in place: after its figures, and the rest before its closing punctuation."""
    inline, tail = plan
    text = claim.text
    for position, source in sorted(inline, reverse=True):  # right to left so earlier positions stay valid
        text = text[:position] + f"[{numbers[source]}]" + text[position:]
    body = text.rstrip()
    trailing_space = text[len(body) :]
    closing = re.search(r"[.,;:!?)]+$", body)
    closing_text = closing.group(0) if closing else ""
    body = body[: len(body) - len(closing_text)]
    return body + "".join(f"[{numbers[source]}]" for source in tail) + closing_text + trailing_space


def join(pieces: list[str]) -> str:
    """Join claim texts; a fragment that begins with punctuation or whitespace attaches directly."""
    joined = ""
    for piece in pieces:
        needs_space = joined and not joined[-1].isspace() and not (piece[:1].isspace() or piece[:1] in ",;:.)")
        joined += (" " if needs_space else "") + piece
    return joined.strip()


def ground(
    answer: ModelAnswer, retrieved: dict[UUID, ChunkHit], labels: dict[UUID, str], *, log: bool = True
) -> tuple[GroundedAnswer, list[SourcePassage]]:
    """Check every claim, number the sources, and join the claims into the answer.

    Returns the checked answer and the cited passages in marker order, or raises
    `GroundingError` listing every problem. `log` turns the weak, log-only checks on or off
    (the agent grounds an accepted answer a second time and does not need them twice).
    """
    by_label = {label: retrieved[chunk_id] for chunk_id, label in labels.items() if chunk_id in retrieved}
    problems: list[str] = []
    for position, claim in enumerate(answer.claims, start=1):
        problems += check_claim(position, claim, by_label, log=log)

    # Across the answer.
    notes = [claim for claim in answer.claims if claim.kind == "note"]
    backed = [claim for claim in answer.claims if claim.kind != "note"]
    if answer.enough_evidence and not backed:
        problems.append(
            "enough_evidence is true but no claim is a fact or calculation with sources. Back the answer with "
            "claims from the passages, or set enough_evidence to false and say the filings do not support one."
        )
    if answer.enough_evidence and len(notes) > MAX_NOTES:
        problems.append(f"The answer has {len(notes)} notes. Use at most {MAX_NOTES}; every statement of fact needs sources.")
    normalized = [re.sub(r"\s+", " ", claim.text).strip().lower() for claim in answer.claims]
    repeated = {text for text in normalized if len(text) > 40 and normalized.count(text) > 1}
    if repeated:
        problems.append(f'The claim "{min(repeated)[:80]}..." is written more than once. Say each claim once.')
    if problems:
        raise GroundingError(problems)

    # Numbers follow the order the markers appear in the finished text.
    plans = {id(claim): plan_markers(claim, by_label) for claim in backed}
    order: list[str] = []
    for claim in backed:
        inline, tail = plans[id(claim)]
        for source in [source for _, source in sorted(inline)] + tail:
            if source not in order:
                order.append(source)
    if len(order) > MAX_CITATIONS:
        raise GroundingError(
            [f"The answer cites {len(order)} passages. Cite at most {MAX_CITATIONS}: the ones that matter most."]
        )

    numbers = {source: position for position, source in enumerate(order, start=1)}
    pieces = [render(claim, plans[id(claim)], numbers) if claim.kind != "note" else claim.text for claim in answer.claims]
    grounded = GroundedAnswer(
        answer=join(pieces),
        enough_evidence=answer.enough_evidence,
        citations=[Citation(marker=numbers[source], source_id=source) for source in order],
    )
    return grounded, [SourcePassage.from_hit(by_label[source]) for source in order]
