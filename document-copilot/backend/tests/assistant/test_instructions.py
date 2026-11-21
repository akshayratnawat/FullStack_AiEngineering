"""Tests for assistant/instructions.md: guard against the product contract losing a key part.

These only check the file still says the important things. Whether the model follows
them is checked by the live question run in Step 9.
"""

from pathlib import Path

import pytest

INSTRUCTIONS = Path(__file__).resolve().parents[2] / "app" / "assistant" / "instructions.md"
TICKERS = ["AAPL", "AMZN", "GOOGL", "JPM", "META", "MSFT", "NVDA", "TSLA"]


@pytest.fixture(scope="module")
def text() -> str:
    """The instructions file as one string."""
    return INSTRUCTIONS.read_text(encoding="utf-8")


@pytest.mark.parametrize("ticker", TICKERS)
def test_every_company_in_the_corpus_is_listed(text, ticker):
    """The model is told all 8 tickers, since search_filings only accepts those."""
    assert ticker in text


@pytest.mark.parametrize(
    "phrase",
    [
        "enough_evidence",  # the evidence flag the validator checks
        "source_id",  # the only thing that may be cited
        "investment advice",  # the out-of-scope rule
        "Do not infer beyond the text",  # brief question 10
        "search each company",  # comparisons need per-company searches
        "Check the question first",  # a vague question is asked back, not searched
        "fiscal",  # fiscal-year guidance
    ],
)
def test_the_key_rules_are_present(text, phrase):
    """Each core rule of the contract is still in the file."""
    assert phrase in text
