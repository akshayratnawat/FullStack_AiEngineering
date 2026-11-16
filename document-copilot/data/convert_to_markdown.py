"""Convert the downloaded SEC filings (HTML) into Markdown with Docling.

Input:  data/downloads/<year>/<name>.htm
Output: data/markdown/<year>/<name>.md   (same folder structure, same file name)

Run from the backend folder, where docling is installed (dev group):
    cd backend
    uv run python ../data/convert_to_markdown.py            # convert everything
    uv run python ../data/convert_to_markdown.py --limit 1  # try one file first

Files that already have a .md are skipped, so the script can be re-run safely.
Use --force to convert them again.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from docling.document_converter import DocumentConverter

DATA_DIR = Path(__file__).resolve().parent
INPUT_DIR = DATA_DIR / "downloads"
OUTPUT_DIR = DATA_DIR / "markdown"
HTML_SUFFIXES = {".htm", ".html"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, default=None, help="convert at most N files")
    parser.add_argument("--force", action="store_true", help="re-convert existing .md files")
    args = parser.parse_args()

    sources = sorted(p for p in INPUT_DIR.rglob("*") if p.suffix.lower() in HTML_SUFFIXES)
    converter = DocumentConverter()
    done = skipped = 0
    failed: list[tuple[Path, str]] = []

    for index, source in enumerate(sources, start=1):
        relative = source.relative_to(INPUT_DIR)
        target = (OUTPUT_DIR / relative).with_suffix(".md")
        label = f"[{index}/{len(sources)}] {relative.as_posix()}"

        if target.exists() and not args.force:
            skipped += 1
            print(f"{label}: skipped (already converted)")
            continue
        if args.limit is not None and done >= args.limit:
            break

        started = time.perf_counter()
        try:
            result = converter.convert(source)
            markdown = result.document.export_to_markdown()
        except Exception as error:  # keep going; report at the end
            failed.append((source, f"{type(error).__name__}: {error}"))
            print(f"{label}: FAILED ({type(error).__name__})")
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(markdown, encoding="utf-8")
        done += 1
        print(f"{label}: {len(markdown):,} chars in {time.perf_counter() - started:.1f}s")

    print(f"\nConverted {done}, skipped {skipped}, failed {len(failed)}.")
    for source, message in failed:
        print(f"  FAILED {source.relative_to(INPUT_DIR).as_posix()}: {message}")


if __name__ == "__main__":
    main()
