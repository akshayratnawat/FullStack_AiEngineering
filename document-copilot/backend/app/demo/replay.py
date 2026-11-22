"""Recorded example answers, shown to visitors without calling the model.

A few questions have an answer that was recorded from a real run of the assistant (see
`scripts/record_demo.py`): the research steps, the checked answer text and the sources with
their exact passages. When someone asks one of these questions the app replays the recording,
so a visitor can see how it works, and click through to the filing passages, without anyone
spending model tokens. The reply carries a `data-demo` part so the UI says plainly that it is a
recorded example and not a new answer.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

ANSWERS_FILE = Path(__file__).with_name("answers.json")


@dataclass(frozen=True)
class DemoAnswer:
    question: str
    steps: list[str]  # the research steps the assistant reported while it worked
    answer: str  # the checked answer text, with its [n] markers
    citations: list[dict]  # the `data-citations` payload: each marker's source and exact passage
    recorded_at: str  # ISO date of the real run
    model: str  # the chat model that produced it


def normalize(question: str) -> str:
    """Case, spacing and a trailing question mark do not make a different question."""
    return re.sub(r"\s+", " ", question).strip().rstrip("?").strip().casefold()


def load_answers(path: Path = ANSWERS_FILE) -> dict[str, DemoAnswer]:
    """The recordings by normalized question. A missing or broken file is an error, not 'no demos'."""
    entries = json.loads(path.read_text(encoding="utf-8"))
    return {normalize(entry["question"]): DemoAnswer(**entry) for entry in entries}


# Read once when the app starts. After changing answers.json, RESTART the backend: uvicorn's
# --reload only watches .py files, so a changed JSON file is not picked up until a restart.
ANSWERS = load_answers()


def find_demo(question: str) -> DemoAnswer | None:
    return ANSWERS.get(normalize(question))
