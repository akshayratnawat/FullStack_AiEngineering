import pytest

from app.chat.messages import (
    TITLE_MAX_CHARS,
    UiMessage,
    message_text,
    new_user_text,
    title_from,
    to_ui_message,
)


def user(text: str) -> UiMessage:
    return UiMessage(role="user", parts=[{"type": "text", "text": text}])


def test_new_user_text_is_the_last_message_and_ignores_history():
    history = [user("old question"), UiMessage(role="assistant", parts=[]), user("  new one ")]

    assert new_user_text(history) == "new one"


@pytest.mark.parametrize(
    "messages",
    [
        [user("hi"), UiMessage(role="assistant", parts=[{"type": "text", "text": "hello"}])],
        [user("   ")],
        [UiMessage(role="user", parts=[{"type": "file", "url": "x"}])],
    ],
)
def test_new_user_text_rejects_anything_but_a_non_empty_user_message(messages):
    with pytest.raises(ValueError):
        new_user_text(messages)


def test_message_text_joins_only_text_parts():
    parts = [
        {"type": "text", "text": "a"},
        {"type": "source-url", "url": "u"},
        {"type": "text", "text": "b"},
    ]

    assert message_text(parts) == "ab"


def test_long_titles_are_cut_with_an_ellipsis_and_short_ones_kept():
    assert title_from("Short question") == "Short question"
    long_title = title_from("x" * 200)
    assert len(long_title) == TITLE_MAX_CHARS
    assert long_title.endswith("…")


def test_stored_rows_become_sdk_messages_and_fall_back_to_plain_content():
    parts = [{"type": "text", "text": "hi"}]
    with_parts = {"id": "1", "role": "user", "content": "hi", "parts": parts}
    without_parts = {"id": "2", "role": "assistant", "content": "hello", "parts": None}

    assert to_ui_message(with_parts) == {"id": "1", "role": "user", "parts": parts}
    assert to_ui_message(without_parts)["parts"] == [{"type": "text", "text": "hello"}]
