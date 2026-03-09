#!/usr/bin/env python3
"""
Pipeline Script 2: Process HMDA Data into Aggregates (2007-2024)

Loads downloaded CSVs and aggregates by tract, county, state, and national level.

Key logic:
- Race classification: hispanic → asian → black → white → multi
- Census tract GEOID: zero-padded 11-char format
- Per-tract: compute race pct, determine dominant race, compute weighted-median income
- Rollup: tract → county → state → national
- Output: compact JSON files per year and level

Run from: National Dashboard/
"""

import os
import sys
import json
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, Any, Tuple, List

YEARS = list(range(2007, 2025))
RACES = ["asian", "black", "hispanic", "white", "multi", "unknown"]

def get_script_dir() -> Path:
    """Return the directory where this script is located."""
    return Path(__file__).parent.parent

def weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    """
    Compute weighted median of values with given weights.

    Returns float or np.nan if empty.
    """
    if len(values) == 0:
        return np.nan

    # Remove NaN values
    mask = ~np.isnan(values)
    vals = values[mask]
    wts = weights[mask]

    if len(vals) == 0:
        return np.nan

    # Sort by values
    sort_idx = np.argsort(vals)
    sorted_vals = vals[sort_idx]
    sorted_wts = wts[sort_idx]

    # Cumulative weights
    cum_wts = np.cumsum(sorted_wts)
    total_wt = cum_wts[-1]

    if total_wt == 0:
        return np.nan

    # Find index where cumulative weight crosses 50%
    threshold = total_wt / 2.0
    idx = np.searchsorted(cum_wts, threshold)
    idx = min(idx, len(sorted_vals) - 1)

    return float(sorted_vals[idx])

def classify_race(row: pd.Series) -> str:
    """
    Classify applicant race based on derived_race and derived_ethnicity.

    Returns one of: "hispanic", "asian", "black", "white", "multi", or "unknown".
    Never returns None — loans with unclassifiable race are kept and counted as "unknown"
    so that tracts with no race data remain visible on the map.
    """
    ethnicity = row.get('derived_ethnicity', '')
    race = row.get('derived_race', '')

    # Hispanic takes priority
    if ethnicity == "Hispanic or Latino":
        return "hispanic"

    # Then check race, excluding hispanics
    if pd.isna(race) or race == "" or race == "Not applicable":
        return "unknown"

    if race == "Asian":
        return "asian"
    elif race == "Black or African American":
        return "black"
    elif race == "White":
        return "white"
    elif race in ["2 or more minority races", "Joint"]:
        return "multi"
    else:
        return "unknown"

def classify_race_legacy(row: pd.Series) -> str:
    """
    Classify applicant race from the legacy HMDA format (2007-2016).

    Uses applicant_ethnicity (code 1 = Hispanic) and applicant_race_1 (codes 1-7).
    Hispanic ethnicity takes priority over race, matching the new-format logic.
    Never returns None — unclassifiable records are returned as "unknown".
    """
    # Ethnicity code 1 = Hispanic or Latino (takes priority)
    eth = str(row.get('applicant_ethnicity', '')).strip()
    if eth == '1':
        return "hispanic"

    race_map = {
        '2': 'asian',   # Asian
        '3': 'black',   # Black or African American
        '5': 'white',   # White
        '1': 'multi',   # American Indian or Alaska Native
        '4': 'multi',   # Native Hawaiian or Other Pacific Islander
    }
    race = str(row.get('applicant_race_1', '')).strip()
    return race_map.get(race, "unknown")


def build_legacy_geoid(row: pd.Series) -> str:
    """
    Build an 11-character census tract GEOID from legacy HMDA fields.

    Legacy HMDA stores: state_code (2-digit), county_code (3-digit),
    census_tract_number (variable string like "0001.00" or "4400").

    GEOID = state(2) + county(3) + int_part(4) + dec_part(2) = 11 chars
    """
    # pandas upcasts row dtypes to float64 when the row contains mixed types,
    # so state_code=1 (int64) becomes 1.0 (float64) and str(1.0)='1.0' which
    # breaks zfill(2). Convert via int(float()) to get clean integer strings.
    try:
        state  = str(int(float(row.get('state_code',  0) or 0))).zfill(2)
        county = str(int(float(row.get('county_code', 0) or 0))).zfill(3)
    except (ValueError, TypeError):
        return None

    tract  = str(row.get('census_tract_number', '')).strip()

    if not tract or tract in ('nan', 'NA', 'None', ''):
        return None

    if '.' in tract:
        int_part, dec_part = tract.split('.', 1)
        int_part = int_part.strip().zfill(4)
        dec_part = (dec_part.strip() + '00')[:2]
    else:
        int_part = tract.zfill(4)
        dec_part = '00'

    return state + county + int_part + dec_part


def aggregate_tracts(df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    """
    Aggregate tract-level data.

    Returns dict: {geoid: {r, tx, inc, pw, pb, pa, ph, pm, pu, ...}}

    All loans are included regardless of race classification — loans with
    unclassifiable race are assigned "_race = 'unknown'" by classify_race(),
    so every row contributes to both tx and race percentages.
    """
    tract_data = {}

    # Ensure census_tract is 11-char zero-padded string
    df['census_tract'] = df['census_tract'].astype(str).str.zfill(11)

    for geoid, group in df.groupby('census_tract'):
        tx_count = len(group)

        # Count by race (all rows have a valid race now, including "unknown")
        race_counts = {race: (group['_race'] == race).sum() for race in RACES}

        # Percentages — dominant race excludes "unknown" from the dominance competition
        # so a tract where most borrowers didn't provide race info isn't labelled "Unknown"
        pct_by_race = {f"p{r[0]}": race_counts[r] / tx_count for r in RACES}

        # Dominant race = most common among known races (excludes "unknown" from competition
        # so a tract where most buyers didn't disclose race still gets its real modal color)
        known_races = [r for r in RACES if r != "unknown"]
        known_total = sum(race_counts[r] for r in known_races)
        if known_total > 0:
            known_pcts = {r: race_counts[r] / known_total for r in known_races}
            dominant_race = max(known_races, key=lambda r: known_pcts[r])
        else:
            dominant_race = "unknown"

        # Weighted median income
        incomes = group['_income'].values
        weights = np.ones_like(incomes)
        median_inc = weighted_median(incomes, weights)

        # Per-race median income
        per_race_inc = {}
        for race in RACES:
            race_mask = (group['_race'] == race).values
            race_incomes = group['_income'].values[race_mask]
            race_wts = np.ones_like(race_incomes)
            race_med = weighted_median(race_incomes, race_wts)
            if not np.isnan(race_med):
                per_race_inc[f"i{race[0]}"] = int(race_med)

        tract_data[geoid] = {
            'r': dominant_race,
            'tx': tx_count,
            'inc': int(median_inc) if not np.isnan(median_inc) else None,
            **pct_by_race,
            **per_race_inc
        }

    return tract_data

def aggregate_counties(tract_data: Dict) -> Dict[str, Dict[str, Any]]:
    """
    Rollup tract data to county level.

    County FIPS = geoid[:5] (first 5 digits of 11-char tract GEOID).
    """
    county_data = {}

    for geoid, tract_info in tract_data.items():
        county_fips = geoid[:5]

        if county_fips not in county_data:
            county_data[county_fips] = {
                'tx': 0,
                'inc_sum': 0,
                'inc_wt': 0,
                **{f"p{r[0]}_sum": 0 for r in RACES},
            }

        county_data[county_fips]['tx'] += tract_info['tx']
        if tract_info['inc'] is not None:
            county_data[county_fips]['inc_sum'] += tract_info['inc'] * tract_info['tx']
            county_data[county_fips]['inc_wt'] += tract_info['tx']

        for race in RACES:
            key = f"p{race[0]}"
            if key in tract_info:
                county_data[county_fips][f"p{race[0]}_sum"] += tract_info[key] * tract_info['tx']

    # Finalize county aggregates
    result = {}
    for county_fips, data in county_data.items():
        tx = data['tx']
        if tx == 0:
            continue

        inc = int(data['inc_sum'] / data['inc_wt']) if data['inc_wt'] > 0 else None

        pcts = {f"p{r[0]}": data[f"p{r[0]}_sum"] / tx for r in RACES}
        known_races = [r for r in RACES if r != "unknown"]
        known_pcts = {r: pcts[f"p{r[0]}"] for r in known_races}
        known_total_pct = sum(known_pcts.values())
        dominant_race = max(known_races, key=lambda r: known_pcts[r]) if known_total_pct > 0 else "unknown"

        result[county_fips] = {
            'r': dominant_race,
            'tx': tx,
            'inc': inc,
            **pcts
        }

    return result

def aggregate_states(county_data: Dict) -> Dict[str, Dict[str, Any]]:
    """
    Rollup county data to state level.

    State FIPS = geoid[:2] (first 2 digits of 5-char county FIPS).
    """
    state_data = {}

    for county_fips, county_info in county_data.items():
        state_fips = county_fips[:2]

        if state_fips not in state_data:
            state_data[state_fips] = {
                'tx': 0,
                'inc_sum': 0,
                'inc_wt': 0,
                **{f"p{r[0]}_sum": 0 for r in RACES},
            }

        state_data[state_fips]['tx'] += county_info['tx']
        if county_info['inc'] is not None:
            state_data[state_fips]['inc_sum'] += county_info['inc'] * county_info['tx']
            state_data[state_fips]['inc_wt'] += county_info['tx']

        for race in RACES:
            key = f"p{race[0]}"
            if key in county_info:
                state_data[state_fips][f"p{race[0]}_sum"] += county_info[key] * county_info['tx']

    # Finalize state aggregates
    result = {}
    for state_fips, data in state_data.items():
        tx = data['tx']
        if tx == 0:
            continue

        inc = int(data['inc_sum'] / data['inc_wt']) if data['inc_wt'] > 0 else None

        pcts = {f"p{r[0]}": data[f"p{r[0]}_sum"] / tx for r in RACES}
        known_races = [r for r in RACES if r != "unknown"]
        known_pcts = {r: pcts[f"p{r[0]}"] for r in known_races}
        known_total_pct = sum(known_pcts.values())
        dominant_race = max(known_races, key=lambda r: known_pcts[r]) if known_total_pct > 0 else "unknown"

        result[state_fips] = {
            'r': dominant_race,
            'tx': tx,
            'inc': inc,
            **pcts
        }

    return result

def compute_national_stats(df: pd.DataFrame) -> Tuple[Dict[str, int], Dict[str, int]]:
    """
    Compute national-level homebuyer counts and median income by race.

    Returns (homebuyers_dict, income_dict).
    """
    homebuyers = {race: 0 for race in RACES}
    income_by_race = {race: [] for race in RACES}

    for race in RACES:
        mask = df['_race'] == race
        homebuyers[race] = mask.sum()
        race_incomes = df[mask]['_income'].dropna().values
        if len(race_incomes) > 0:
            income_by_race[race] = float(np.median(race_incomes))

    homebuyers['total'] = len(df)

    return homebuyers, income_by_race

def detect_separator(file_path: Path) -> str:
    """
    Auto-detect CSV separator by inspecting the first line.

    CFPB historic data (2007-2016) uses pipe-delimited format.
    CFPB Data Browser API (2017+) uses comma-delimited format.

    Returns ',' or '|'.
    """
    try:
        with open(file_path, encoding='utf-8', errors='replace') as f:
            first_line = f.readline()
        # Pipe-delimited if '|' appears much more than ','
        if first_line.count('|') > first_line.count(','):
            return '|'
    except Exception:
        pass
    return ','


def process_year(year: int, raw_dir: Path, output_dir: Path) -> bool:
    """
    Process all data files for a single year.

    Accepts .csv, .txt, and .dat files. Auto-detects comma vs pipe delimiter.
    Returns True if successful, False (with warning) if no data found.
    """
    print(f"\nProcessing year {year}...")

    year_dir = raw_dir / str(year)
    if not year_dir.exists():
        print(f"  WARNING: No raw data found for {year} — skipping")
        return False

    # Accept CSV, TXT, and DAT files (legacy HMDA comes as .txt or .dat)
    data_files = []
    for pattern in ("*.csv", "*.txt", "*.dat"):
        data_files.extend(year_dir.glob(pattern))
    data_files = sorted(set(data_files))

    if not data_files:
        print(f"  WARNING: No data files found for {year} — skipping")
        if year < 2017:
            print(f"  (Pre-2017 data must be placed manually — see pipeline/1_download_hmda.py)")
        return False

    # Load all data files for this year
    dfs = []
    for data_file in data_files:
        try:
            sep = detect_separator(data_file)
            df = pd.read_csv(
                data_file,
                sep=sep,
                dtype={'census_tract': str},
                low_memory=False
            )
            dfs.append(df)
            fmt = "pipe-delimited" if sep == '|' else "CSV"
            print(f"  Loaded {data_file.name}: {len(df)} rows ({fmt})")
        except Exception as e:
            print(f"  ERROR loading {data_file.name}: {e}")
            return False

    # Combine
    combined = pd.concat(dfs, ignore_index=True)
    print(f"  Combined: {len(combined)} total rows")

    # Detect format: legacy (2007-2016) uses applicant_race_1; new (2017+) uses derived_race
    is_legacy = 'applicant_race_1' in combined.columns
    print(f"  Format: {'legacy (pre-2018)' if is_legacy else 'new (2017+)'}")

    if is_legacy:
        # Legacy: build GEOID from state_code + county_code + census_tract_number
        combined['census_tract'] = combined.apply(build_legacy_geoid, axis=1)
        # Legacy: ensure action_taken==1 (originated) and loan_purpose==1 (purchase)
        # The API query params should handle this, but filter as a safeguard
        for col, val in [('action_taken', '1'), ('loan_purpose', '1')]:
            if col in combined.columns:
                combined = combined[combined[col].astype(str).str.strip() == val]
                print(f"  After filtering {col}=={val}: {len(combined)} rows")
    else:
        # Modern format: census_tract is already the 11-char GEOID
        pass

    # Clean: drop rows where census_tract is NaN or missing
    combined = combined.dropna(subset=['census_tract'])
    combined = combined[combined['census_tract'].astype(str).str.strip().str.len() == 11]
    print(f"  After dropping invalid census_tract: {len(combined)} rows")

    # Classify race (None = unclassifiable; rows are kept so tx counts are accurate)
    if is_legacy:
        combined['_race'] = combined.apply(classify_race_legacy, axis=1)
    else:
        combined['_race'] = combined.apply(classify_race, axis=1)
    unknown_count = (combined['_race'] == 'unknown').sum()
    known_count = len(combined) - unknown_count
    print(f"  Race-classified rows: {known_count}/{len(combined)} ({known_count/len(combined)*100:.1f}%); unknown: {unknown_count}")

    # Parse income
    if 'applicant_income_000s' in combined.columns:
        # Legacy format: income in thousands (000s)
        combined['_income'] = pd.to_numeric(combined['applicant_income_000s'], errors='coerce') * 1000
    elif 'applicant_income_thousands' in combined.columns:
        combined['_income'] = pd.to_numeric(combined['applicant_income_thousands'], errors='coerce') * 1000
    elif 'income' in combined.columns:
        combined['_income'] = pd.to_numeric(combined['income'], errors='coerce') * 1000
    else:
        print(f"  WARNING: No income column found for {year}")
        combined['_income'] = np.nan

    # Aggregate
    tract_agg = aggregate_tracts(combined)
    county_agg = aggregate_counties(tract_agg)
    state_agg = aggregate_states(county_agg)
    homebuyers, income_data = compute_national_stats(combined)

    print(f"  Aggregated to: {len(tract_agg)} tracts, {len(county_agg)} counties, {len(state_agg)} states")

    # Write outputs
    output_dir.mkdir(parents=True, exist_ok=True)

    def write_json(path: Path, obj: Any):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(obj, f, separators=(',', ':'), default=str)

    write_json(output_dir / f"tract_agg_{year}.json", tract_agg)
    write_json(output_dir / f"county_agg_{year}.json", county_agg)
    write_json(output_dir / f"state_agg_{year}.json", state_agg)

    national = {
        'homebuyers': homebuyers,
        'income': income_data
    }
    write_json(output_dir / f"national_{year}.json", national)

    print(f"  Wrote outputs to processed/")

    return True

def main():
    """Process all HMDA data by year."""
    script_dir = get_script_dir()
    raw_dir = script_dir / "raw_data"
    output_dir = script_dir / "processed"

    print("=== HMDA Data Processing ===")
    print(f"Input: {raw_dir}")
    print(f"Output: {output_dir}\n")

    successes = 0
    failures = 0

    for year in YEARS:
        if process_year(year, raw_dir, output_dir):
            successes += 1
        else:
            failures += 1

    print(f"\n=== Summary ===")
    print(f"Years processed: {successes}/{len(YEARS)}")
    if failures > 0:
        print(f"Years failed: {failures}")
        sys.exit(1)
    else:
        print("All years processed successfully!")
        sys.exit(0)

if __name__ == "__main__":
    main()
