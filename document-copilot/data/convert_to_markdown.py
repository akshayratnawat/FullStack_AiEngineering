"""Convert the downloaded SEC filings (HTML) into Markdown with Docling.

Input:  data/downloads/<year>/<name>.htm
Output: data/markdown/<year>/<name>.md   (same folder structure, same file name)

Run from the backend folder, where docling is installed (dev group):
    cd backend
    uv run python ../data/convert_to_markdown.py            # convert everything
    uv run python ../data/convert_to_markdown.py --limit 1  # try one file first

Each filing is cleaned first (see sec_html_cleanup.py) so Docling sees real headings
and compact tables.

Also writes data/markdown/manifest.json: the same metadata as
data/downloads/manifest.json, with local_path pointing at the .md file.

Files that already have a .md are skipped, so the script can be re-run safely.
Use --force to convert them again.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from docling.datamodel.base_models import DocumentStream
from docling.document_converter import DocumentConverter

from sec_html_cleanup import clean_sec_html

DATA_DIR = Path(__file__).resolve().parent
INPUT_DIR = DATA_DIR / "downloads"
OUTPUT_DIR = DATA_DIR / "markdown"
HTML_SUFFIXES = {".htm", ".html"}


def write_manifest() -> int:
    """Write markdown/manifest.json for every filing that has a converted .md file."""
    # Rebuilt from the downloads manifest on every run (not only for newly converted
    # files), so skipped files stay listed and the metadata never drifts from the source.
    downloads = json.loads((INPUT_DIR / "manifest.json").read_text(encoding="utf-8"))
    filings = []
    for filing in downloads["filings"]:
        source_path = Path(filing["local_path"])
        target = OUTPUT_DIR / source_path.with_suffix(".md")
        if not target.exists():
            continue
        filings.append(
            {
                **{key: value for key, value in filing.items() if key != "local_path"},
                "source_path": source_path.as_posix(),
                "local_path": target.relative_to(OUTPUT_DIR).as_posix(),
                "characters": len(target.read_text(encoding="utf-8")),
            }
        )
    manifest = {
        "source": downloads["source"],
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "form": downloads["form"],
        "converted_with": "docling",
        "converted_count": len(filings),
        "filings": filings,
    }
    (OUTPUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return len(filings)


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
            cleaned_html, stats = clean_sec_html(source.read_text(encoding="utf-8"))
            stream = DocumentStream(name=source.name, stream=BytesIO(cleaned_html.encode("utf-8")))
            markdown = converter.convert(stream).document.export_to_markdown()
        except Exception as error:  # keep going; report at the end
            failed.append((source, f"{type(error).__name__}: {error}"))
            print(f"{label}: FAILED ({type(error).__name__})")
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(markdown, encoding="utf-8")
        done += 1
        print(
            f"{label}: {len(markdown):,} chars, {stats['headings']} headings, "
            f"{time.perf_counter() - started:.1f}s"
        )

    count = write_manifest()
    print(f"\nManifest: {OUTPUT_DIR / 'manifest.json'} ({count} filings)")
    print(f"Converted {done}, skipped {skipped}, failed {len(failed)}.")
    for source, message in failed:
        print(f"  FAILED {source.relative_to(INPUT_DIR).as_posix()}: {message}")


if __name__ == "__main__":
    main()
