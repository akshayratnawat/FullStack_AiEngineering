# /// script
# requires-python = ">=3.12"
# ///
"""Download recent 10-K annual reports from SEC EDGAR for a fixed set of companies.

Output (under `data/downloads/`):
  <year>/<ticker>_10-k_<filing_date>_<accession>.<ext>   the raw filing documents
  manifest.json                                          metadata for every file

Run with: `uv run data/download.py`
"""
from __future__ import annotations

import json
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib import request


# Params: edit these, then run `uv run data/download.py`
# SEC requires a User-Agent identifying you (name + email); replace the placeholder.
USER_AGENT = "Document Copilot your.email@example.com"
TICKERS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "JPM", "META", "TSLA"]  
FILINGS_PER_COMPANY = 5  # also the number of past years covered (see target_years)
OUTPUT_DIR = Path(__file__).resolve().parent / "downloads"
CLEAR_OUTPUT_DIR = True  # wipe previous downloads so each run starts clean

# EDGAR identifies companies by CIK (Central Index Key), not ticker.
# Every ticker in TICKERS must have an entry here.
COMPANY_CIKS = {
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "NVDA": "0001045810",
    "AMZN": "0001018724",
    "GOOGL": "0001652044",
    "JPM": "0000019617",
    "META": "0001326801",
    "TSLA": "0001318605"
}


def get_json(url: str) -> dict:
    """GET a URL and parse the JSON response (used for EDGAR's submissions API)."""
    req = request.Request(
        url, headers={"Accept": "application/json", "User-Agent": USER_AGENT}
    )
    with request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def get_bytes(url: str) -> bytes:
    """GET a URL and return the raw body (used for the filing documents)."""
    req = request.Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml",
            "User-Agent": USER_AGENT,
        },
    )
    with request.urlopen(req, timeout=60) as response:
        return response.read()


def download_filings() -> dict:
    """Download 10-Ks for every ticker, write manifest.json, and return the manifest."""
    if CLEAR_OUTPUT_DIR and OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # The last N completed years (excludes the current, not-yet-filed year).
    target_years = {
        str(year)
        for year in range(
            datetime.now(UTC).year - FILINGS_PER_COMPANY, datetime.now(UTC).year
        )
    }
    manifest = {
        "source": "SEC EDGAR",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "form": "10-K",
        "downloaded_count": 0,
        "filings": [],
    }

    for ticker in TICKERS:
        print(f"Downloading {ticker} filings...")
        cik = COMPANY_CIKS[ticker]
        submission = get_json(f"https://data.sec.gov/submissions/CIK{cik}.json")
        # The main response only lists recent filings; older ones live in extra
        # paginated files referenced under filings.files, so fetch those too.
        submissions = [submission]
        submissions.extend(
            get_json(f"https://data.sec.gov/submissions/{item['name']}")
            for item in submission.get("filings", {}).get("files", [])
        )

        # Collect matching 10-Ks, stopping early once we have enough.
        filings = []
        for sec_submission in submissions:
            filings.extend(extract_10k_filings(sec_submission, target_years))
            if len(filings) >= FILINGS_PER_COMPANY:
                break

        for filing in filings[:FILINGS_PER_COMPANY]:
            # EDGAR archive URLs use the accession number without dashes and the
            # CIK without leading zeros.
            accession_path = filing["accession_number"].replace("-", "")
            source_url = (
                "https://www.sec.gov/Archives/edgar/data/"
                f"{int(cik)}/{accession_path}/{filing['primary_document']}"
            )
            year_dir = OUTPUT_DIR / filing["year"]
            year_dir.mkdir(parents=True, exist_ok=True)
            local_path = year_dir / (
                f"{ticker.lower()}_{filing['form'].lower()}_"
                f"{filing['filing_date']}_{filing['accession_number']}"
                f"{Path(filing['primary_document']).suffix or '.html'}"
            )
            local_path.write_bytes(get_bytes(source_url))

            manifest["filings"].append(
                {
                    "ticker": ticker,
                    "cik": cik,
                    "form": filing["form"],
                    "filing_date": filing["filing_date"],
                    "report_date": filing["report_date"],
                    "accession_number": filing["accession_number"],
                    "primary_document": filing["primary_document"],
                    "source_url": source_url,
                    "local_path": str(local_path.relative_to(OUTPUT_DIR)),
                }
            )
            manifest["downloaded_count"] += 1

            # Stay well under SEC's rate limit (10 requests/second).
            time.sleep(0.2)

    manifest_path = OUTPUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def extract_10k_filings(
    submission: dict, target_years: set[str]
) -> list[dict[str, str]]:
    """Return the 10-K entries in one submissions payload that fall in target_years.

    The payload is column-oriented (parallel lists per field). The main response
    nests them under filings.recent; the older-history files have them at top level.
    """
    recent = submission["filings"]["recent"] if "filings" in submission else submission
    filings = []

    for form, accession, document, filing_date, report_date in zip(
        recent["form"],
        recent["accessionNumber"],
        recent["primaryDocument"],
        recent["filingDate"],
        recent["reportDate"],
        strict=True,
    ):
        # Bucket by fiscal period end (report_date); fall back to filing date if missing.
        year = (report_date or filing_date)[:4]
        if form == "10-K" and year in target_years:
            filings.append(
                {
                    "year": year,
                    "form": form,
                    "accession_number": accession,
                    "primary_document": document,
                    "filing_date": filing_date,
                    "report_date": report_date,
                }
            )

    return filings


if __name__ == "__main__":
    result = download_filings()
    print(f"Downloaded {result['downloaded_count']} filing(s) to {OUTPUT_DIR}")
    print(f"Manifest: {OUTPUT_DIR / 'manifest.json'}")
