"""Tests for chat/messages.py history building: which stored messages the agent gets to see."""

from app.chat.messages import FAILED_PART_TYPE, failed_parts, to_model_history

# --- helpers -----------------------------------------------------------------


def user(text: str) -> dict:
    """A stored user message row."""
    return {"role": "user", "content": text, "parts": [{"type": "text", "text": text}]}


def assistant(text: str, failed: bool = False) -> dict:
    """A stored assistant message row; `failed` marks a "could not answer" explanation."""
    parts = failed_parts(text) if failed else [{"type": "text", "text": text}]
    return {"role": "assistant", "content": text, "parts": parts}


def texts(history) -> list[tuple[str, str]]:
    """(kind, text) per history message, to compare easily."""
    return [(type(m).__name__, m.parts[0].content) for m in history]


# --- tests -------------------------------------------------------------------


def test_stored_messages_become_alternating_requests_and_responses():
    """Questions become model requests and answers become model responses, in order."""
    rows = [user("q1"), assistant("a1"), user("q2"), assistant("a2")]

    assert texts(to_model_history(rows, limit=10)) == [
        ("ModelRequest", "q1"),
        ("ModelResponse", "a1"),
        ("ModelRequest", "q2"),
        ("ModelResponse", "a2"),
    ]


def test_only_the_most_recent_messages_are_kept():
    """The limit keeps the tail of the thread."""
    rows = [user("q1"), assistant("a1"), user("q2"), assistant("a2"), user("q3"), assistant("a3")]

    assert [t for _, t in texts(to_model_history(rows, limit=2))] == ["q3", "a3"]


def test_a_cut_that_starts_on_an_answer_drops_that_orphan_answer():
    """Cutting between a question and its answer must not leave the history starting with an answer."""
    rows = [user("q1"), assistant("a1"), user("q2"), assistant("a2")]

    assert [t for _, t in texts(to_model_history(rows, limit=3))] == ["q2", "a2"]


def test_a_failed_exchange_is_left_out_as_a_pair():
    """The "could not answer" reply and the question it replied to are both dropped."""
    rows = [user("q1"), assistant("a1"), user("bad q"), assistant("sorry", failed=True), user("q3"), assistant("a3")]

    assert [t for _, t in texts(to_model_history(rows, limit=10))] == ["q1", "a1", "q3", "a3"]


def test_a_limit_of_zero_means_no_history():
    """Setting agent_history_messages to 0 turns history off."""
    assert to_model_history([user("q"), assistant("a")], limit=0) == []


def test_an_empty_thread_has_no_history():
    """A brand-new thread has nothing to remember."""
    assert to_model_history([], limit=10) == []


def test_a_message_with_no_content_falls_back_to_its_text_parts():
    """Rows saved with only `parts` still give their text."""
    rows = [{"role": "user", "content": "", "parts": [{"type": "text", "text": "from parts"}]}, assistant("a")]

    assert texts(to_model_history(rows, limit=10))[0] == ("ModelRequest", "from parts")


def test_the_failed_marker_is_a_data_part_the_ui_ignores():
    """The marker is a "data-" part, so the browser's message list does not try to render it."""
    assert FAILED_PART_TYPE.startswith("data-")
