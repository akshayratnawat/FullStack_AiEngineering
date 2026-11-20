"""The trust contract, in code: an answer is only accepted if its citations are real.

No model is involved. The checks compare the agent's `GroundedAnswer` with the chunks
the search tools actually returned this turn (`DocumentAgentDeps.retrieved`), so a model
that invents or mis-numbers a source is caught regardless of how convincing it sounds.

The error message is written for the model, not the user: Step 5 hands it back to the
agent for one retry, so it says exactly what to fix.
"""

import re
from uuid import UUID

from app.assistant.outputs import GroundedAnswer, SourcePassage
from app.retrieval.queries import ChunkHit

# A citation marker in the text: [1], [12]. At most 3 digits, so a bracketed year such as
# "[2024]" is never mistaken for one.
MARKER = re.compile(r"\[(\d{1,3})\]")


class GroundingError(Exception):
    """The answer broke the grounding rules. `problems` lists every rule it broke."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("The answer is not properly grounded:\n- " + "\n- ".join(problems))


def validate(answer: GroundedAnswer, retrieved: dict[UUID, ChunkHit]) -> list[SourcePassage]:
    """Return the cited passages in marker order, or raise `GroundingError`.

    Rules:
    1. Every citation points at a chunk a search tool returned this turn.
    2. Each marker number is used by one citation only.
    3. Every [n] in the text has a citation, and every citation's [n] appears in the text.
    4. An answer that claims enough evidence cites at least one passage.
    """
    problems: list[str] = []

    # Rule 1: no source the model did not actually see.
    for citation in answer.citations:
        if citation.chunk_id not in retrieved:
            problems.append(
                f"Citation [{citation.marker}] points at chunk {citation.chunk_id}, which no search "
                "returned. Cite only chunk_ids that appear in search results."
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

    if problems:
        raise GroundingError(problems)

    ordered = sorted(answer.citations, key=lambda citation: citation.marker)
    return [SourcePassage.from_hit(retrieved[citation.chunk_id]) for citation in ordered]
