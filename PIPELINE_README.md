# National HMDA Dashboard Pipeline

Production-grade Python pipeline for building a national (50-state + DC) HMDA mortgage disclosure dashboard using MapLibre GL + PMTiles.

## Overview

The pipeline consists of 5 sequential scripts that:

1. **Download** HMDA data from CFPB API (2018-2024, all states)
2. **Process** raw CSV data into aggregated JSON (tract/county/state/national)
3. **Download** Census TIGER shapefiles and build merged GeoJSON
4. **Build** PMTiles for efficient frontend rendering
5. **Generate** frontend data files (years, demographics, geographies)

Each script is standalone and can be run from the `National Dashboard/` directory.

---

## System Requirements

- Python 3.8+
- pip packages:
  - `requests` (for API downloads)
  - `pandas` (for data aggregation)
  - `numpy` (for weighted statistics)
  - `geopandas` (for shapefile processing)
  - `shapely` (geometry operations)
- `tippecanoe` (for PMTiles generation)
  - Ubuntu/Debian: `sudo apt-get install -y tippecanoe`
  - macOS: `brew install tippecanoe`

Install Python dependencies:
```bash
pip install requests pandas numpy geopandas shapely
```

---

## Pipeline Scripts

### Script 1: `pipeline/1_download_hmda.py`

**Purpose:** Download HMDA data from CFPB Data Browser API.

**What it does:**
- Downloads CSV files for all 50 states + DC (51 total)
- Covers years 2018-2024 (7 years)
- 357 files total
- Rate-limited to 1 request/second
- Retries up to 3 times with 5-second delays
- Validates file contents (checks for "activity_year" header)
- Skips files already downloaded (if size > 100 KB)

**Output:**
```
raw_data/
├── 2018/
│   ├── AL.csv
│   ├── AK.csv
│   └── ... (51 files per year)
├── 2019/
└── ... (through 2024)
```

**Usage:**
```bash
cd "National Dashboard"
python3 pipeline/1_download_hmda.py
```

**Time estimate:** ~6-10 hours (357 files × 1 req/sec rate limiting)

**Key features:**
- Progress output: "Downloading GA 2024 (12/357)..."
- Failure summary at end with specific errors
- Safe to interrupt and resume (checks for existing files)

---

### Script 2: `pipeline/2_process_hmda.py`

**Purpose:** Aggregate downloaded CSVs into structured JSON files.

**What it does:**
- Loads all state CSVs for each year
- Classifies applicants by race (rules below)
- Aggregates to tract → county → state → national levels
- Computes per-race statistics (counts, percentages, median incomes)
- Outputs compact JSON files

**Race classification logic:**
1. **Hispanic:** `derived_ethnicity == "Hispanic or Latino"` (takes priority)
2. **Asian:** `derived_race == "Asian"` AND NOT hispanic
3. **Black:** `derived_race == "Black or African American"` AND NOT hispanic
4. **White:** `derived_race == "White"` AND NOT hispanic
5. **Multi:** `derived_race in ["2 or more minority races", "Joint"]`
6. Unknown/missing values are excluded

**Dominant race determination:**
- Per geography: highest race percentage
- If max percentage < 40%: marked as "Highly Diverse"

**Output per year:**
```
processed/
├── tract_agg_2018.json      {geoid: {r, tx, inc, pw, pb, pa, ph, pm}}
├── county_agg_2018.json     {fips5: {r, tx, inc, pw, pb, pa, ph, pm}}
├── state_agg_2018.json      {fips2: {r, tx, inc, pw, pb, pa, ph, pm}}
├── national_2018.json       {homebuyers: {...}, income: {...}}
└── ... (through 2024)
```

**JSON field meanings:**
- `r`: dominant race string
- `tx`: transaction count
- `inc`: weighted median income (dollars)
- `pw/pb/pa/ph/pm`: percent white/black/asian/hispanic/multi
- `iw/ib/ia/ih/im`: (optional) per-race median income

**Usage:**
```bash
python3 pipeline/2_process_hmda.py
```

**Time estimate:** ~5-15 minutes (depends on total CSV size)

---

### Script 3: `pipeline/3_download_tiles.py`

**Purpose:** Download Census TIGER shapefiles and build merged GeoJSON files.

**What it does:**
- Downloads state tract shapefiles for 2010 and 2020 census epochs
- Downloads national county shapefile (2020)
- Extracts all ZIPs
- Merges state shapefiles into single GeoJSON per epoch
- Simplifies geometries (0.005 tolerance)
- Creates state boundaries by dissolving counties
- Sets feature `id` property for MapLibre feature-state

**Downloads:**
- 51 states × 2 epochs (2010, 2020) = 102 tract ZIPs
- 1 national county ZIP
- ~500 MB total download size

**Output:**
```
shapefiles/
├── tracts_2010_merged.geojson      (all states, 2010 tracts)
├── tracts_2020_merged.geojson      (all states, 2020 tracts)
├── counties_merged.geojson         (all US counties)
├── states.geojson                  (state boundaries)
├── tracts_2010/                    (extracted state ZIPs)
├── tracts_2020/                    (extracted state ZIPs)
├── counties_source/                (extracted national county ZIP)
└── downloads/                      (downloaded ZIPs, safe to delete after)
```

**Usage:**
```bash
python3 pipeline/3_download_tiles.py
```

**Time estimate:** ~20-40 minutes (mostly network I/O)

**Optional cleanup:** After successful completion, you can delete the `downloads/` and `*_source/` directories to save ~500 MB disk space.

---

### Script 4: `pipeline/4_build_pmtiles.py`

**Purpose:** Generate PMTiles for efficient map rendering.

**What it does:**
- Validates `tippecanoe` is installed
- Runs tippecanoe to generate PMTiles for each tile layer:
  - `states.pmtiles`: z2-z6 (world to state zoom)
  - `counties.pmtiles`: z4-z9 (region to county zoom)
  - `tracts_2010.pmtiles`: z7-z14 (detailed tract zoom)
  - `tracts_2020.pmtiles`: z7-z14 (detailed tract zoom)
- Skips existing outputs (unless `--force` flag passed)
- Uses density optimization flags for better performance

**Output:**
```
tiles/
├── states.pmtiles           (~10-20 MB)
├── counties.pmtiles         (~50-100 MB)
├── tracts_2010.pmtiles      (~200-400 MB)
└── tracts_2020.pmtiles      (~200-400 MB)
```

**Usage:**
```bash
# First time
python3 pipeline/4_build_pmtiles.py

# Force regenerate
python3 pipeline/4_build_pmtiles.py --force
```

**Time estimate:** ~30-60 minutes (depends on tippecanoe performance)

---

### Script 5: `pipeline/5_build_data_files.py`

**Purpose:** Convert aggregated JSON into frontend data files.

**What it does:**
- Loads processed aggregates from script 2
- Writes per-year files for states, counties, tracts
- Aggregates homebuyer counts and income stats across all years
- Writes `years.json`, `homebuyers.json`, `income.json`, `metadata.json`
- Validates state FIPS codes
- Generates build timestamp

**Output:**
```
data/
├── states_2018.json         {fips2: {r, tx, inc, pw, ...}}
├── states_2019.json
├── ... (through 2024)
├── counties_2018.json       {fips5: {r, tx, inc, pw, ...}}
├── ... (through 2024)
├── tracts_2010_2018.json    (for years 2018-2021, using 2010 tracts)
├── tracts_2010_2019.json
├── ... through 2021
├── tracts_2020_2022.json    (for years 2022+, using 2020 tracts)
├── tracts_2020_2023.json
├── ... through 2024
├── years.json               [2018, 2019, ..., 2024]
├── homebuyers.json          {2018: {asian, black, ..., total}, ...}
├── income.json              {2018: {asian, black, ..., multi}, ...}
└── metadata.json            {built_at, data_range, state_count, ...}
```

**Usage:**
```bash
python3 pipeline/5_build_data_files.py
```

**Time estimate:** ~1-2 minutes

---

## Running the Complete Pipeline

### Step-by-step:

```bash
cd "/sessions/ecstatic-optimistic-tesla/mnt/HDMA Project/National Dashboard"

# Step 1: Download HMDA data (~6-10 hours)
python3 pipeline/1_download_hmda.py

# Step 2: Process into aggregates (~5-15 minutes)
python3 pipeline/2_process_hmda.py

# Step 3: Download shapefiles and build GeoJSON (~20-40 minutes)
python3 pipeline/3_download_tiles.py

# Step 4: Build PMTiles (~30-60 minutes)
python3 pipeline/4_build_pmtiles.py

# Step 5: Generate frontend data files (~1-2 minutes)
python3 pipeline/5_build_data_files.py
```

**Total time:** ~8-15 hours (mostly dependent on CFPB API rate limits and tippecanoe performance)

### Parallel downloads (optional):

Scripts 1, 3, and 4 are I/O bound and can potentially be optimized:
- Script 1: Could use threading (respecting rate limit), but current sequential approach is safe
- Script 3: Downloads in series; Census servers are generally fast
- Script 4: tippecanoe is single-threaded; one PMTiles generation per invocation

Current approach prioritizes stability and rate-limit compliance.

---

## Data Sources

### HMDA Data
- **Source:** CFPB Data Browser API
- **URL:** `https://ffiec.cfpb.gov/v2/data-browser-api/view/csv`
- **Parameters:** states, years (2018-2024), actions_taken=1, loan_purposes=1
- **CSV columns:** activity_year, census_tract, derived_race, derived_ethnicity, applicant_income_thousands, ...

### Census Shapefiles
- **2010 tracts:** `https://www2.census.gov/geo/tiger/TIGER2010/TRACT/2010/tl_2010_{fips2}_tract10.zip`
- **2020 tracts:** `https://www2.census.gov/geo/tiger/TIGER2020/TRACT/tl_2020_{fips2}_tract.zip`
- **Counties:** `https://www2.census.gov/geo/tiger/TIGER2020/COUNTY/tl_2020_us_county.zip`

---

## Directory Structure

```
National Dashboard/
├── pipeline/
│   ├── 1_download_hmda.py
│   ├── 2_process_hmda.py
│   ├── 3_download_tiles.py
│   ├── 4_build_pmtiles.py
│   └── 5_build_data_files.py
├── raw_data/                (CSV files from CFPB API)
├── processed/               (aggregated JSON from script 2)
├── shapefiles/              (GeoJSON and TIGER shapefiles)
├── tiles/                   (PMTiles output)
├── data/                    (frontend data files)
├── downloads/               (temporary: TIGER ZIPs, safe to delete)
└── PIPELINE_README.md       (this file)
```

---

## Error Handling & Recovery

### Script 1 (Download):
- Retries up to 3 times with 5-second delays
- Skips already-downloaded files (safe to re-run)
- Lists failures at end with specific error messages

**If failures occur:**
```bash
# Fix network issue, then re-run
python3 pipeline/1_download_hmda.py
# It will skip existing files and retry only failed ones
```

### Scripts 2-5:
- Print detailed error messages
- Exit with status code 1 on failure
- Designed to fail fast if dependencies missing

**If a script fails:**
1. Read the error message
2. Install missing dependencies (requests, pandas, geopandas, etc.)
3. Re-run the same script

### Script 3 (Shapefiles):
- Downloads are cached; safe to re-run
- Extraction happens to `shapefiles/tracts_2010/` etc. (cached)
- GeoJSON output overwrites previous (use `--force` flag if needed)

### Script 4 (PMTiles):
- Check `tippecanoe --version` before processing
- PMTiles files are cached; skip if exist
- Use `--force` flag to regenerate: `python3 pipeline/4_build_pmtiles.py --force`

---

## Output Specifications

### Tract/County/State JSON Format

```json
{
  "geoid_or_fips": {
    "r": "white|black|hispanic|asian|multi|Highly Diverse",
    "tx": 1234,
    "inc": 75000,
    "pw": 0.65,
    "pb": 0.15,
    "ph": 0.12,
    "pa": 0.06,
    "pm": 0.02,
    "iw": 80000,
    "ib": 55000,
    "ih": 62000,
    "ia": 95000
  }
}
```

### Homebuyers JSON Format

```json
{
  "2018": {
    "asian": 123456,
    "black": 234567,
    "hispanic": 345678,
    "white": 1234567,
    "multi": 45678,
    "total": 2000000
  }
}
```

### Income JSON Format

```json
{
  "2018": {
    "asian": 90000.5,
    "black": 65000.25,
    "hispanic": 70000.75,
    "white": 85000.0,
    "multi": 75500.0
  }
}
```

---

## Testing & Validation

### Quick validation after each script:

```bash
# After script 1: Check raw_data/ directory
ls raw_data/2024/ | wc -l  # Should be 51

# After script 2: Check processed/ directory
ls processed/*_2024.json | wc -l  # Should be 4 files

# After script 3: Check shapefiles/
ls shapefiles/*.geojson  # Should be 4 files

# After script 4: Check tiles/
ls -lh tiles/*.pmtiles  # Should be 4 files, sizes ~10MB-400MB

# After script 5: Check data/
ls data/*.json | wc -l  # Should be 8+ files
```

### Verify JSON integrity:

```bash
# Check any JSON file
python3 -m json.tool data/states_2024.json > /dev/null && echo "Valid JSON"
```

---

## Frontend Integration

After running the complete pipeline, you have:

1. **Tile layers** (`tiles/*.pmtiles`): MapLibre GL tile sources
2. **Data files** (`data/*.json`): Statistics for charts and info panels
3. **Metadata** (`data/metadata.json`): Build timestamp and data ranges

### Recommended frontend setup:

```javascript
// index.html
const map = new maplibregl.Map({
  container: 'map',
  style: 'https://tiles.openstreetmap.se/fiord/style.json',
  center: [-100, 40],
  zoom: 4
});

// Add PMTiles sources
map.addSource('states', {
  type: 'vector',
  url: 'pmtiles://./tiles/states.pmtiles'
});

map.addSource('counties', {
  type: 'vector',
  url: 'pmtiles://./tiles/counties.pmtiles'
});

// Load data files for UI
fetch('data/years.json').then(r => r.json()).then(years => {
  // Populate year selector
});

fetch('data/homebuyers.json').then(r => r.json()).then(data => {
  // Populate charts
});
```

---

## Performance Notes

- **Tract count:** ~70,000 per epoch (2010 and 2020)
- **County count:** ~3,000 total
- **State count:** 51 (50 states + DC)
- **Total PMTiles size:** ~450-600 MB (all 4 layers combined)
- **Data files size:** ~5-10 MB (all JSON combined)

Frontend should paginate tile rendering by zoom level:
- z0-2: No tile layer visible
- z2-3: Show states layer
- z4-6: Show states + counties
- z7+: Show states + counties + tracts (appropriate epoch)

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Script 1: "Connection timeout" | Check network; re-run (skips existing) |
| Script 1: "Invalid CSV" | CFPB API issue; re-run with retry |
| Script 2: "ImportError: No module named pandas" | `pip install pandas numpy` |
| Script 3: "ImportError: No module named geopandas" | `pip install geopandas shapely` |
| Script 3: "Extracted shapefiles not found" | Network failure during download; re-run script 3 |
| Script 4: "tippecanoe: command not found" | Install tippecanoe (see requirements) |
| Script 4: "tippecanoe failed" | Check disk space; try `--force` flag |
| Script 5: "No processed data found" | Run scripts 1-2 first |

---

## License & Attribution

- **HMDA Data:** Public domain (CFPB)
- **Census Shapefiles:** Public domain (US Census Bureau)
- **Pipeline:** As specified in your project

---

## Questions?

Refer to the individual script docstrings:
```bash
head -30 pipeline/1_download_hmda.py
```

Each script prints detailed progress output and comprehensive error messages.
