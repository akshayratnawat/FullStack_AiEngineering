"""Load the converted Markdown filings into the `source_documents` table.

Reads data/markdown/manifest.json (one entry per filing) plus each .md file, and
upserts one row per filing. Chunks and embeddings are a later step.

Run from the backend folder:
    uv run python ingest/ingest_documents.py --dry-run   # show what would be written
    uv run python ingest/ingest_documents.py             # write to Supabase

Safe to re-run: rows are matched on `accession_number`, so existing filings are
updated in place instead of duplicated.
"""

import argparse
import asyncio
import json
import uuid
from datetime import date
from pathlib import Path

from app.database.supabase import create_service_client

MARKDOWN_DIR = Path(__file__).resolve().parents[2] / "data" / "markdown"
TABLE = "source_documents"
# Manifest fields with their own column; everything else goes into `extra`.
COLUMN_FIELDS = {
    "ticker", "cik", "form", "filing_date", "report_date",
    "accession_number", "source_url", "local_path",
}


def build_row(filing: dict, document_id: uuid.UUID) -> dict:
    """Map one manifest entry (plus its .md file) onto a `source_documents` row."""
    return {
        # The Supabase API skips the model's Python-side default, so we send the id.
        "id": str(document_id),
        **{key: filing[key] for key in COLUMN_FIELDS - {"local_path"}},
        # Same rule as the data/downloads/<year> folders: year the fiscal period ended.
        "fiscal_year": date.fromisoformat(filing["report_date"]).year,
        "content_markdown": (MARKDOWN_DIR / filing["local_path"]).read_text(encoding="utf-8"),
        "extra": {key: value for key, value in filing.items() if key not in COLUMN_FIELDS},
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="print the rows, write nothing")
    args = parser.parse_args()

    manifest = json.loads((MARKDOWN_DIR / "manifest.json").read_text(encoding="utf-8"))
    filings = manifest["filings"]

    if args.dry_run:
        for filing in filings:
            row = build_row(filing, uuid.uuid4())
            print(
                f"{row['ticker']:<5} FY{row['fiscal_year']} {row['filing_date']} "
                f"{row['accession_number']}  {len(row['content_markdown']):>9,} chars  "
                f"extra={sorted(row['extra'])}"
            )
        print(f"\nDry run: {len(filings)} rows would be written to {TABLE}.")
        return

    client = await create_service_client()
    # Re-use the id of a filing that is already stored. A new id on the upsert would
    # overwrite it, and later chunk rows point at that id.
    existing = await client.table(TABLE).select("id, accession_number").execute()
    ids = {row["accession_number"]: row["id"] for row in existing.data}

    written, failed = 0, []
    for filing in filings:
        accession = filing["accession_number"]
        document_id = uuid.UUID(ids[accession]) if accession in ids else uuid.uuid4()
        try:
            # One request per filing: each row carries up to ~5 MB of text.
            await (
                client.table(TABLE)
                .upsert(build_row(filing, document_id), on_conflict="accession_number")
                .execute()
            )
        except Exception as error:  # keep going; report at the end
            failed.append((accession, f"{type(error).__name__}: {error}"))
            print(f"{accession}: FAILED ({type(error).__name__})")
            continue
        written += 1
        print(f"{accession}: {'updated' if accession in ids else 'inserted'}")

    count = await client.table(TABLE).select("id", count="exact").limit(1).execute()
    print(f"\nWritten {written}, failed {len(failed)}. Rows now in {TABLE}: {count.count}")
    for accession, message in failed:
        print(f"  FAILED {accession}: {message}")


if __name__ == "__main__":
    asyncio.run(main())
