#!/usr/bin/env python3
"""
Pipeline Script 5: Build Frontend Data Files

Converts processed JSON aggregates into frontend data/*.json files.

Outputs:
- data/states_{year}.json
- data/counties_{year}.json
- data/tracts_{epoch}_{year}.json (epoch = 2000, 2010, or 2020 based on year)
- data/years.json
- data/homebuyers.json
- data/income.json
- data/metadata.json

Fallback: If processed/ not found, tries to load from existing GA+AL CSVs
at ../HMDA Python/Programs/ for testing.

Run from: National Dashboard/
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, Any, List, Set
from datetime import datetime

RACES = ["asian", "black", "hispanic", "white", "multi"]

# State FIPS codes (string keys)
STATE_FIPS = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08", "CT": "09", "DE": "10",
    "DC": "11", "FL": "12", "GA": "13", "HI": "15", "ID": "16", "IL": "17", "IN": "18", "IA": "19",
    "KS": "20", "KY": "21", "LA": "22", "ME": "23", "MD": "24", "MA": "25", "MI": "26", "MN": "27",
    "MS": "28", "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33", "NJ": "34", "NM": "35",
    "NY": "36", "NC": "37", "ND": "38", "OH": "39", "OK": "40", "OR": "41", "PA": "42", "RI": "44",
    "SC": "45", "SD": "46", "TN": "47", "TX": "48", "UT": "49", "VT": "50", "VA": "51", "WA": "53",
    "WV": "54", "WI": "55", "WY": "56"
}

def get_script_dir() -> Path:
    """Return the directory where this script is located."""
    return Path(__file__).parent.parent

def epoch_for_year(year: int) -> int:
    """Determine census epoch (2010 or 2020) for a given year."""
    if year >= 2022:
        return 2020
    elif year >= 2012:
        return 2010
    else:
        return 2000

def write_json(path: Path, obj: Any) -> int:
    """
    Write object to JSON file (compact format).

    Returns file size in KB.
    """
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, separators=(',', ':'), default=str)

    size_kb = path.stat().st_size / 1024
    return size_kb

def load_processed_data(processed_dir: Path, year: int) -> tuple:
    """
    Load processed aggregates for a year.

    Returns (tract_data, county_data, state_data, national_data) or None if not found.
    """
    tract_file = processed_dir / f"tract_agg_{year}.json"
    county_file = processed_dir / f"county_agg_{year}.json"
    state_file = processed_dir / f"state_agg_{year}.json"
    national_file = processed_dir / f"national_{year}.json"

    if not all([tract_file.exists(), county_file.exists(), state_file.exists(), national_file.exists()]):
        return None

    try:
        with open(tract_file, encoding='utf-8') as f:
            tract_data = json.load(f)
        with open(county_file, encoding='utf-8') as f:
            county_data = json.load(f)
        with open(state_file, encoding='utf-8') as f:
            state_data = json.load(f)
        with open(national_file, encoding='utf-8') as f:
            national_data = json.load(f)

        return (tract_data, county_data, state_data, national_data)
    except Exception as e:
        print(f"  ERROR loading processed data for {year}: {e}")
        return None

def build_data_files(base_dir: Path) -> bool:
    """
    Build all frontend data files.

    Returns True if successful.
    """
    processed_dir = base_dir / "processed"
    data_dir = base_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== Building Frontend Data Files ===\n")

    # Discover available years
    years_found = set()

    if processed_dir.exists():
        for json_file in processed_dir.glob("national_*.json"):
            try:
                year = int(json_file.stem.split('_')[1])
                years_found.add(year)
            except Exception:
                pass

    if not years_found:
        print(f"WARNING: No processed data found in {processed_dir}")
        print(f"Attempting fallback to existing GA+AL data...")

        # Fallback: try to load from existing GA+AL project
        fallback_dir = base_dir.parent / "HMDA Python" / "Programs"
        if fallback_dir.exists():
            print(f"Found fallback directory: {fallback_dir}")
            # For testing, we'd need to parse the existing structure
            # For now, just warn
            print("Fallback loading not implemented; please run pipeline 1-2 first")
            return False
        else:
            print("Fallback directory not found")
            return False

    years_sorted = sorted(years_found)
    print(f"Years found: {years_sorted}\n")

    # Containers for aggregating across years
    all_homebuyers = {}
    all_income = {}
    tract_count_by_epoch = {2000: 0, 2010: 0, 2020: 0}

    # Process each year
    for year in years_sorted:
        print(f"Processing year {year}...")

        result = load_processed_data(processed_dir, year)
        if not result:
            print(f"  SKIP (data not found)")
            continue

        tract_data, county_data, state_data, national_data = result

        # Write states
        size_kb = write_json(data_dir / f"states_{year}.json", state_data)
        print(f"  states_{year}.json: {len(state_data)} states, {size_kb:.0f} KB")

        # Validate state FIPS codes
        expected_states = set(STATE_FIPS.values())
        found_states = set(state_data.keys())
        unexpected = found_states - expected_states
        if unexpected:
            print(f"    WARNING: Unexpected state FIPS codes: {sorted(unexpected)}")

        # Write counties
        size_kb = write_json(data_dir / f"counties_{year}.json", county_data)
        print(f"  counties_{year}.json: {len(county_data)} counties, {size_kb:.0f} KB")

        # Write tracts (epoch-specific)
        epoch = epoch_for_year(year)
        size_kb = write_json(data_dir / f"tracts_{epoch}_{year}.json", tract_data)
        print(f"  tracts_{epoch}_{year}.json: {len(tract_data)} tracts, {size_kb:.0f} KB")
        tract_count_by_epoch[epoch] = max(tract_count_by_epoch[epoch], len(tract_data))

        # Aggregate national data
        all_homebuyers[year] = national_data.get('homebuyers', {})
        all_income[year] = national_data.get('income', {})

    if not all_homebuyers:
        print("\nERROR: No years processed")
        return False

    # Write years.json
    size_kb = write_json(data_dir / "years.json", years_sorted)
    print(f"\nyears.json: {len(years_sorted)} years, {size_kb:.0f} KB")

    # Write homebuyers.json
    size_kb = write_json(data_dir / "homebuyers.json", all_homebuyers)
    print(f"homebuyers.json: {len(all_homebuyers)} year(s), {size_kb:.0f} KB")

    # Write income.json
    size_kb = write_json(data_dir / "income.json", all_income)
    print(f"income.json: {len(all_income)} year(s), {size_kb:.0f} KB")

    # Write metadata.json
    metadata = {
        'built_at': datetime.utcnow().isoformat(),
        'data_range': {
            'min_year': min(years_sorted),
            'max_year': max(years_sorted)
        },
        'state_count': 51,  # 50 states + DC
        'tract_count_by_epoch': tract_count_by_epoch
    }
    size_kb = write_json(data_dir / "metadata.json", metadata)
    print(f"metadata.json: {size_kb:.0f} KB")

    print(f"\n=== Summary ===")
    print(f"Output directory: {data_dir}")
    print(f"Files written: {len(list(data_dir.glob('*.json')))}")
    print(f"Years covered: {min(years_sorted)}-{max(years_sorted)}")

    return True

def main():
    """Main entry point."""
    script_dir = get_script_dir()

    try:
        if build_data_files(script_dir):
            print("\nAll data files built successfully!")
            print("\nNext: Set up index.html and serve.py to test the dashboard")
            sys.exit(0)
        else:
            sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
