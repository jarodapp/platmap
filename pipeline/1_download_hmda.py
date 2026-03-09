#!/usr/bin/env python3
"""
Pipeline Script 1: Download HMDA Data (2007-2024)

Downloads HMDA data for all 50 US states + DC using two sources:

  2018-2024  CFPB Data Browser API (CSV, new column format)
             https://ffiec.cfpb.gov/v2/data-browser-api/view/csv
             Columns: derived_race, derived_ethnicity, income
             Already filtered to originated home-purchase loans.

  2007-2017  CFPB Historic Data (ZIP, legacy column format)
             https://files.consumerfinance.gov/hmda-historic-loan-data/
             Columns: applicant_race_1, applicant_ethnicity, applicant_income_000s
             Filtered to first-lien owner-occupied 1-4 family homes.
             Script 2 will further filter to action_taken=1 & loan_purpose=1.
             Note: the CFPB API returns 400 for years before 2018.

Skips files that already exist and are large enough.
Retries failures up to 3 times with a delay.

Run from: National Dashboard/
"""

import io
import sys
import time
import zipfile
import requests
from pathlib import Path
from typing import Dict

# ── Configuration ─────────────────────────────────────────────────────────────

# CFPB Data Browser API (2018+) — only covers new format data
API_BASE_URL  = "https://ffiec.cfpb.gov/v2/data-browser-api/view/csv"
API_YEARS     = list(range(2018, 2025))

# CFPB Historic Data (2007-2017) — uses legacy column format (numeric codes)
# The CFPB API confirmed to return 400 for years < 2018.
LEGACY_BASE_URL = (
    "https://files.consumerfinance.gov/hmda-historic-loan-data/"
    "hmda_{year}_{state}_first-lien-owner-occupied-1-4-family-records_codes.zip"
)
LEGACY_YEARS  = list(range(2007, 2018))

ALL_YEARS     = LEGACY_YEARS + API_YEARS   # 2007-2024

MIN_FILE_SIZE = 50_000   # bytes — skip if existing file exceeds this
MAX_RETRIES   = 3
RETRY_DELAY   = 5        # seconds between retries
REQUEST_DELAY = 0.5      # seconds between requests

# 50 states + DC
STATE_ABBR = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL",
    "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME",
    "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH",
    "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_script_dir() -> Path:
    return Path(__file__).parent.parent

def setup_dirs(base_dir: Path) -> Path:
    for year in ALL_YEARS:
        (base_dir / "raw_data" / str(year)).mkdir(parents=True, exist_ok=True)
    return base_dir / "raw_data"

def already_downloaded(state_file: Path) -> bool:
    return state_file.exists() and state_file.stat().st_size > MIN_FILE_SIZE

# ── Legacy download (2007-2016) ───────────────────────────────────────────────

def download_legacy(state: str, year: int, output_dir: Path, failures: Dict) -> bool:
    """
    Download a state/year ZIP from CFPB historic data, extract the CSV inside,
    and save it as raw_data/{year}/{STATE}.csv.
    """
    state_file = output_dir / str(year) / f"{state}.csv"
    if already_downloaded(state_file):
        return True

    url = LEGACY_BASE_URL.format(year=year, state=state.lower())

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, timeout=120)
            response.raise_for_status()

            # Unzip in memory and extract the first CSV file
            with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
                csv_names = [n for n in zf.namelist() if n.lower().endswith('.csv')]
                if not csv_names:
                    raise ValueError(f"No CSV found in ZIP ({zf.namelist()})")
                csv_bytes = zf.read(csv_names[0])

            # Validate header
            first_line = csv_bytes[:500].decode('utf-8', errors='replace').split('\n')[0]
            if 'activity_year' not in first_line.lower() and 'as_of_year' not in first_line.lower():
                raise ValueError(f"Unexpected header: {first_line[:120]}")

            state_file.write_bytes(csv_bytes)
            return True

        except Exception as e:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
            else:
                failures[f"{state}_{year}"] = str(e)
                return False

        time.sleep(REQUEST_DELAY)

    return False

# ── API download (2017-2024) ──────────────────────────────────────────────────

def download_api(state: str, year: int, output_dir: Path, failures: Dict) -> bool:
    """
    Download a state/year CSV from the CFPB Data Browser API and save it as
    raw_data/{year}/{STATE}.csv.
    """
    state_file = output_dir / str(year) / f"{state}.csv"
    if already_downloaded(state_file):
        return True

    url = f"{API_BASE_URL}?states={state}&years={year}&actions_taken=1&loan_purposes=1"

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, timeout=60)
            response.raise_for_status()

            content = response.text
            first_line = content.split('\n')[0] if content else ''
            if 'activity_year' not in first_line:
                raise ValueError(f"Missing activity_year header: {first_line[:120]}")

            state_file.write_text(content, encoding='utf-8')
            return True

        except Exception as e:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
            else:
                failures[f"{state}_{year}"] = str(e)
                return False

        time.sleep(REQUEST_DELAY)

    return False

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    script_dir = get_script_dir()
    output_dir = setup_dirs(script_dir)

    failures: Dict[str, str] = {}
    downloaded  = 0
    skipped     = 0

    total = len(STATE_ABBR) * len(ALL_YEARS)
    processed = 0

    print("=== HMDA Data Download ===")
    print(f"2007-2017 : CFPB Historic Data (ZIP + extract, legacy format)")
    print(f"2018-2024 : CFPB Data Browser API (CSV, new format)")
    print(f"States: {len(STATE_ABBR)}  ·  Years: {len(ALL_YEARS)}  ·  Files: {total}")
    print()

    start = time.time()

    for year in ALL_YEARS:
        use_legacy = year < 2018
        source = "legacy" if use_legacy else "API"
        print(f"--- {year} ({source}) ---")

        for state in STATE_ABBR:
            processed += 1
            state_file = output_dir / str(year) / f"{state}.csv"

            if already_downloaded(state_file):
                print(f"  {state}: SKIP  ({processed}/{total})", flush=True)
                skipped += 1
                continue

            if use_legacy:
                ok = download_legacy(state, year, output_dir, failures)
            else:
                ok = download_api(state, year, output_dir, failures)

            result = "OK" if ok else "FAIL"
            print(f"  {state}: {result}  ({processed}/{total})", flush=True)
            if ok:
                downloaded += 1

    elapsed = time.time() - start

    print(f"\n=== Summary ===")
    print(f"Elapsed    : {elapsed/60:.1f} min")
    print(f"Downloaded : {downloaded}")
    print(f"Skipped    : {skipped}  (already on disk)")
    print(f"Failures   : {len(failures)}")

    if failures:
        print("\nFailed downloads:")
        for key, err in sorted(failures.items()):
            print(f"  {key}: {err}")
        sys.exit(1)
    else:
        print("\nAll downloads complete. Ready for pipeline/2_process_hmda.py")
        sys.exit(0)

if __name__ == "__main__":
    main()
