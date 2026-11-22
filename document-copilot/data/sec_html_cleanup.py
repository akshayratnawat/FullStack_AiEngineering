"""Make SEC inline-XBRL filings friendly to Docling before it converts them.

EDGAR filings are built for browsers, not for structure-aware parsers:
- they contain no <h1>-<h6> tags (section titles are just bold text), so Docling
  finds no headings and later chunks get no section labels;
- they carry thousands of hidden <ix:...> XBRL tags and empty layout tables;
- financial tables are split into filler columns ("$", ")", "%") with merged
  cells that Docling repeats once per column.

`clean_sec_html` fixes all three and returns plain, well-formed HTML.
"""
from __future__ import annotations

import re
import warnings

from bs4 import BeautifulSoup, Tag, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

PART = re.compile(r"^PART\s+[IV]+\b", re.I)
ITEM = re.compile(r"^ITEM\s+\d+[A-C]?\b", re.I)
BARE_SECTION = re.compile(r"^(PART\s+[IV]+|ITEM\s+\d+[A-C]?)\.?$", re.I)
SECTION_LINE = re.compile(r"^(PART\s+[IV]+|ITEM\s+\d+[A-C]?)\b", re.I)
MAX_HEADING_CHARS = 160
CANDIDATES_AFTER_ANCHOR = 6  # how many text blocks after a TOC target we search
REPEATED_HEADER_MIN = 3  # a bare "PART I" line seen this often is a page header
TABLE_FILLER = {"$", ")", "%", "%)", ")%"}


def clean_sec_html(html: str) -> tuple[str, dict]:
    """Return (cleaned HTML, stats) for one SEC filing."""
    soup = BeautifulSoup(html, "lxml")
    _strip_xbrl(soup)
    headings = _promote_toc_headings(soup)
    headings += _promote_bold_section_lines(soup)
    removed = _remove_page_headers(soup)
    dropped = _rebuild_tables(soup)
    return str(soup), {"headings": headings, "page_headers_removed": removed, "empty_tables_dropped": dropped}


def _text(tag: Tag) -> str:
    # Spans inside one text block can split a word ("B" + "USINESS" in small caps), so
    # join them as-is there; only blocks that contain other blocks need a separator.
    if tag.name in ("div", "p") and tag.find(["div", "p", "table"]) is None:
        return " ".join(tag.get_text().split())
    return " ".join(tag.get_text(" ", strip=True).split())


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _strip_xbrl(soup: BeautifulSoup) -> None:
    for tag in soup.find_all("ix:header"):  # hidden metadata block
        tag.decompose()
    for tag in soup.find_all(style=re.compile(r"display:\s*none")):
        tag.decompose()
    for tag in soup.find_all(re.compile(r"^ix:")):  # keep the text, drop the tag
        tag.unwrap()


def _is_leaf_block(tag: Tag) -> bool:
    return tag.name in ("div", "p") and tag.find(["div", "p", "table"]) is None


def _is_title_wrapper(tag: Tag) -> bool:
    """A block whose only content is a one-row layout table (AMZN: "Item 1A." | "Risk Factors")."""
    if tag.name not in ("div", "p") or tag.find_parent("table"):
        return False
    tables = tag.find_all("table")
    if len(tables) != 1:
        return False
    return sum(1 for tr in tables[0].find_all("tr") if tr.get_text(strip=True)) == 1


def _make_heading(block: Tag, text: str) -> None:
    level = 1 if PART.match(text) else 2 if ITEM.match(text) else 3
    block.name = f"h{level}"
    block.attrs = {}
    block.string = text


def _promote_toc_headings(soup: BeautifulSoup) -> int:
    """Use the table of contents: its links point at the real section headings."""
    ids = {tag["id"]: tag for tag in soup.find_all(id=True)}
    promoted, seen_targets = 0, set()
    for link in soup.find_all("a", href=re.compile(r"^#.")):
        target_id, label = link["href"][1:], _text(link)
        if target_id in seen_targets or target_id not in ids or _normalize(label) in ("", "tableofcontents"):
            continue
        seen_targets.add(target_id)
        anchor = ids[target_id]
        candidates = ([anchor] if _is_leaf_block(anchor) else []) + [
            block for block in anchor.find_all_next(["div", "p"])
            if _is_leaf_block(block) or _is_title_wrapper(block)
        ]
        candidates = [b for b in candidates if _text(b) and _normalize(_text(b)) != "tableofcontents"]
        promoted += _promote_first_match(candidates[:CANDIDATES_AFTER_ANCHOR], label)
    return promoted


def _promote_first_match(candidates: list[Tag], label: str) -> int:
    wanted = _normalize(label)
    for index, block in enumerate(candidates):
        text = _text(block)
        if block.find_parent("table") or len(text) > MAX_HEADING_CHARS or block.name.startswith("h"):
            continue
        normalized = _normalize(text)
        # The title may add a short "Item 1A." prefix to the TOC label; a longer text that
        # merely mentions the label (a footnote, a cross-reference) is not a heading.
        if not (normalized.startswith(wanted) or (len(wanted) >= 8 and wanted in normalized and len(normalized) <= len(wanted) + 12)):
            continue
        # Some filings put "Item 1." and "Business" in two separate blocks: join them.
        previous = candidates[index - 1] if index else None
        if previous is not None and BARE_SECTION.match(_text(previous)) and not SECTION_LINE.match(text):
            text = f"{_text(previous)} {text}"
            previous.decompose()
        _make_heading(block, text)
        return 1
    return 0


def _promote_bold_section_lines(soup: BeautifulSoup) -> int:
    """Fallback for lines the table of contents did not cover (e.g. 'PART II')."""
    promoted = 0
    for block in soup.find_all(["div", "p"]):
        text = _text(block) if _is_leaf_block(block) else ""
        if not text or len(text) > MAX_HEADING_CHARS or not SECTION_LINE.match(text):
            continue
        if block.find_parent("table") or not _is_bold(block):
            continue
        _make_heading(block, text)
        promoted += 1
    return promoted


def _is_bold(block: Tag) -> bool:
    styles = [(s.get("style") or "").replace(" ", "") for s in block.find_all("span") if s.get_text(strip=True)]
    return bool(styles) and all("font-weight:700" in s or "font-weight:bold" in s for s in styles)


def _remove_page_headers(soup: BeautifulSoup) -> int:
    """Drop 'Table of Contents' and repeated bare 'PART I' / 'Item 1A' running page headers."""
    leaves = [b for b in soup.find_all(["div", "p"]) if _is_leaf_block(b) and not b.find_parent("table")]
    counts: dict[str, int] = {}
    for block in leaves:
        counts[_text(block).lower()] = counts.get(_text(block).lower(), 0) + 1
    removed = 0
    for block in leaves:
        text = _text(block)
        is_toc_label = _normalize(text) == "tableofcontents"
        is_repeated_header = BARE_SECTION.match(text) and counts[text.lower()] >= REPEATED_HEADER_MIN
        if is_toc_label or is_repeated_header:
            block.decompose()
            removed += 1
    return removed


def _rebuild_tables(soup: BeautifulSoup) -> int:
    dropped = 0
    for table in soup.find_all("table"):
        if table.find_parent("table"):
            continue
        rows = [[(_text(c), int(c.get("colspan", 1) or 1)) for c in tr.find_all(["td", "th"])] for tr in table.find_all("tr")]
        if not any(text for row in rows for text, _ in row):
            table.decompose()
            dropped += 1
            continue
        table.replace_with(_clean_table(soup, rows))
    return dropped


def _clean_table(soup: BeautifulSoup, rows: list[list[tuple[str, int]]]) -> Tag:
    """One cell per column: no repeated merged cells, no '$'/'%'/')' filler columns."""
    grid = []  # per row: [text, start column, span]
    for row in rows:
        position, cells = 0, []
        for text, span in row:
            cells.append([text, position, span])
            position += span
        grid.append(cells)
    width = max((cells[-1][1] + cells[-1][2] for cells in grid if cells), default=0)

    for cells in grid:
        for k, cell in enumerate(cells):
            if cell[0] == "$":
                cell[0] = ""
            elif cell[0] in TABLE_FILLER:  # glue "%" / ")" onto the value before it
                previous = next((c for c in reversed(cells[:k]) if c[0]), None)
                if previous:
                    previous[0] += cell[0]
                cell[0] = ""

    # A header spanning several columns sits over the column that holds the numbers.
    data_columns = {c[1] for cells in grid for c in cells if c[2] == 1 and c[0]}
    placed = []
    for cells in grid:
        row = [""] * width
        for text, start, span in cells:
            if text:
                target = next((j for j in range(start, start + span) if j in data_columns), start)
                row[target] = f"{row[target]} {text}".strip()
        placed.append(row)

    keep = [j for j in range(width) if any(row[j] for row in placed)]
    table = soup.new_tag("table")
    for row in placed:
        if not any(row[j] for j in keep):
            continue
        tr = soup.new_tag("tr")
        for j in keep:
            td = soup.new_tag("td")
            td.string = row[j]
            tr.append(td)
        table.append(tr)
    return table
