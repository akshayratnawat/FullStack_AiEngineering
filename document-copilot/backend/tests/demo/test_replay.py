"""Recorded example answers: lookup by question, and loading the recordings file."""

import json
import re
from pathlib import Path

import pytest

from app.demo.replay import ANSWERS, DemoAnswer, find_demo, load_answers, normalize

ENTRY = {
    "question": "What was Apple's revenue?",
    "steps": ["Searching AAPL: revenue", "Checking every claim and figure against its source"],
    "answer": "Apple's revenue was $391,035 million[1].",
    "citations": [{"marker": 1, "ticker": "AAPL", "excerpt": "Total net sales 391,035"}],
    "recorded_at": "2026-11-22",
    "model": "gpt-4.1-mini",
}


@pytest.mark.parametrize(
    "asked",
    [
        "What was Apple's revenue?",
        "what was apple's revenue",  # case and the trailing question mark
        "  What was   Apple's revenue?  ",  # stray spacing
    ],
)
def test_the_same_question_in_other_spacing_or_case_finds_the_recording(tmp_path, monkeypatch, asked):
    path = tmp_path / "answers.json"
    path.write_text(json.dumps([ENTRY]), encoding="utf-8")
    monkeypatch.setattr("app.demo.replay.ANSWERS", load_answers(path))

    assert find_demo(asked) == DemoAnswer(**ENTRY)


def test_a_different_question_has_no_recording(tmp_path, monkeypatch):
    path = tmp_path / "answers.json"
    path.write_text(json.dumps([ENTRY]), encoding="utf-8")
    monkeypatch.setattr("app.demo.replay.ANSWERS", load_answers(path))

    assert find_demo("What was Apple's revenue in 2021?") is None


def test_a_missing_recordings_file_is_an_error_not_an_empty_list(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_answers(tmp_path / "nope.json")


def test_every_shipped_recording_is_complete_and_its_markers_have_sources():
    """The recordings are shown to visitors as they are, so check the shipped file itself."""
    for demo in ANSWERS.values():
        assert demo.steps and demo.answer.strip() and demo.recorded_at and demo.model
        markers = {citation["marker"] for citation in demo.citations}
        for marker in {int(m) for m in re.findall(r"\[(\d{1,3})\]", demo.answer)}:
            assert marker in markers, f"[{marker}] in the answer to {demo.question!r} has no source"
        for citation in demo.citations:
            assert citation["excerpt"].strip()


def test_normalize_ignores_case_spacing_and_the_question_mark():
    assert normalize("  Why  now?") == normalize("why now")


def frontend_example_questions() -> list[str]:
    """The questions the home screen offers, read from frontend/src/lib/examples.ts."""
    source = (Path(__file__).resolve().parents[3] / "frontend" / "src" / "lib" / "examples.ts").read_text(
        encoding="utf-8"
    )
    # question: '...' or "..." (the string may hold the other kind of quote), possibly on the next line
    return [match[1] for match in re.findall(r"""question:\s*(["'])((?:(?!\1).)*)\1""", source)]


def test_every_example_has_a_recording():
    """Picking an example never calls the model, so each one needs a stored answer; otherwise a
    visitor who picks it would be refused, or the app would spend tokens on a question it promised was free."""
    questions = frontend_example_questions()

    assert len(questions) >= 1, "could not read the example questions from the frontend"
    missing = [question for question in questions if find_demo(question) is None]
    assert not missing, f"examples with no stored answer in app/demo/answers.json: {missing}"
