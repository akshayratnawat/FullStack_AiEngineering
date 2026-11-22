"""Unit tests for chunking filings into embedding-sized pieces (ingest/chunking.py)."""

import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[2] / "ingest" / "chunking.py"
spec = importlib.util.spec_from_file_location("chunking", MODULE_PATH)
chunking = importlib.util.module_from_spec(spec)
spec.loader.exec_module(chunking)

SAMPLE = """# PART I

## Item 1A. Risk Factors

Supply chain disruption could harm results. """ + ("The company depends on suppliers. " * 400) + """

## Item 7. Management's Discussion

| Product | 2025 | 2024 |
|---------|------|------|
| iPhone  | 209,586 | 201,183 |
| Mac     | 33,708  | 29,984  |
"""


def test_every_chunk_fits_the_embedding_budget():
    chunks = chunking.chunk_markdown(SAMPLE)
    assert len(chunks) > 2  # the long section had to be split
    assert all(c.token_count <= chunking.MAX_CHUNK_TOKENS for c in chunks)


def test_chunks_carry_their_section_and_heading_path():
    chunks = chunking.chunk_markdown(SAMPLE)
    risk = [c for c in chunks if c.section == "Item 1A. Risk Factors"]
    assert risk and risk[0].headings == ["PART I", "Item 1A. Risk Factors"]
    assert "Item 1A. Risk Factors" in risk[0].content  # headings are part of the embedded text


def test_chunk_indexes_run_from_zero_without_gaps():
    chunks = chunking.chunk_markdown(SAMPLE)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_tables_stay_markdown_tables_not_triplets():
    chunks = chunking.chunk_markdown(SAMPLE)
    table_chunk = next(c for c in chunks if "209,586" in c.content)
    assert "| iPhone" in table_chunk.content
    assert "iPhone, 2025" not in table_chunk.content  # no "row, column = value" triplets
    assert "2025" in table_chunk.content  # the header travels with the rows
