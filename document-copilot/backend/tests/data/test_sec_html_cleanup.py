"""Unit tests for the SEC HTML cleanup that runs before Docling (data/sec_html_cleanup.py)."""

import importlib.util
from pathlib import Path

from bs4 import BeautifulSoup

# The module lives next to the converter script in data/, which is not a package.
MODULE_PATH = Path(__file__).resolve().parents[3] / "data" / "sec_html_cleanup.py"
spec = importlib.util.spec_from_file_location("sec_html_cleanup", MODULE_PATH)
cleanup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleanup)

BOLD = "font-weight:700"


def headings(html: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    return [(h.name, h.get_text()) for h in soup.find_all(["h1", "h2", "h3"])]


def test_toc_link_promotes_the_matching_title_to_a_heading():
    html = """
    <table><tr><td><a href="#risk">Item 1A.</a></td></tr></table>
    <div id="risk"></div>
    <div><span>Item 1A. Risk Factors</span></div>
    <div>Body text that mentions Item 1A. Risk Factors only in passing, and is long.</div>
    """
    cleaned, stats = cleanup.clean_sec_html(html)
    assert headings(cleaned) == [("h2", "Item 1A. Risk Factors")]
    assert stats["headings"] == 1


def test_title_split_across_a_layout_table_becomes_one_heading():
    html = """
    <a href="#x">Risk Factors</a>
    <div id="x"></div>
    <div><table><tr><td>Item&#160;1A.</td><td>Risk Factors</td></tr></table></div>
    """
    cleaned, _ = cleanup.clean_sec_html(html)
    assert headings(cleaned) == [("h2", "Item 1A. Risk Factors")]


def test_footnote_that_only_mentions_a_section_is_not_a_heading():
    html = """
    <a href="#x">Properties</a>
    <div id="x"></div>
    <div>(1) For leased properties, represents the total leased space excluding space.</div>
    """
    cleaned, _ = cleanup.clean_sec_html(html)
    assert headings(cleaned) == []


def test_bold_part_line_is_promoted_without_a_toc_link():
    html = f'<div><span style="{BOLD}">PART II</span></div><div>Some text.</div>'
    cleaned, _ = cleanup.clean_sec_html(html)
    assert headings(cleaned) == [("h1", "PART II")]


def test_small_caps_title_split_over_spans_keeps_its_words_whole():
    html = """
    <a href="#x">Business</a>
    <p id="x"><span>ITEM 1. B</span><span>USINESS</span></p>
    """
    cleaned, _ = cleanup.clean_sec_html(html)
    assert headings(cleaned) == [("h2", "ITEM 1. BUSINESS")]


def test_repeated_page_headers_are_removed_but_a_single_title_stays():
    page_header = "<p>PART I</p>"
    html = page_header * 3 + "<p>Table of Contents</p><p>Real paragraph.</p>"
    cleaned, stats = cleanup.clean_sec_html(html)
    assert "PART I" not in cleaned and "Table of Contents" not in cleaned
    assert "Real paragraph." in cleaned
    assert stats["page_headers_removed"] == 4


def test_hidden_xbrl_is_dropped_and_inline_xbrl_text_is_kept():
    html = (
        '<ix:header><ix:hidden>secret</ix:hidden></ix:header>'
        '<div>Revenue was <ix:nonfraction>416,161</ix:nonfraction> million.</div>'
    )
    cleaned, _ = cleanup.clean_sec_html(html)
    assert "secret" not in cleaned
    assert "Revenue was 416,161 million." in " ".join(BeautifulSoup(cleaned, "lxml").get_text().split())


def test_table_filler_columns_are_folded_and_headers_stay_aligned():
    html = """
    <table>
      <tr><td></td><td colspan="3">2025</td><td colspan="3">Change</td></tr>
      <tr><td colspan="2">iPhone</td><td>$</td><td>209,586</td><td></td><td>4</td><td>%</td></tr>
    </table>
    """
    cleaned, _ = cleanup.clean_sec_html(html)
    rows = [[td.get_text() for td in tr.find_all("td")] for tr in BeautifulSoup(cleaned, "lxml").find_all("tr")]
    assert rows == [["", "2025", "Change"], ["iPhone", "209,586", "4%"]]


def test_table_with_no_text_is_dropped():
    cleaned, stats = cleanup.clean_sec_html("<table><tr><td></td><td> </td></tr></table><p>after</p>")
    assert "<table" not in cleaned
    assert stats["empty_tables_dropped"] == 1
