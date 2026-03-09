# National Dashboard Directory Structure

## Current Structure (Post-Pipeline)

```
National Dashboard/
├── pipeline/
│   ├── 1_download_hmda.py          (4.4 KB) - Download CFPB API data
│   ├── 2_process_hmda.py           (12 KB)  - Aggregate to tract/county/state
│   ├── 3_download_tiles.py         (11 KB)  - Download TIGER shapefiles
│   ├── 4_build_pmtiles.py          (5.8 KB) - Build PMTiles with tippecanoe
│   └── 5_build_data_files.py       (7.8 KB) - Generate frontend JSON files
│
├── raw_data/                        (Post-script-1)
│   ├── 2018/
│   │   ├── AL.csv (100 KB)
│   │   ├── AK.csv
│   │   └── ... (51 files)
│   ├── 2019/
│   │   └── ... (51 files)
│   └── ... through 2024/
│   └── Total: ~357 CSV files, ~3-5 GB
│
├── processed/                       (Post-script-2)
│   ├── tract_agg_2018.json
│   ├── county_agg_2018.json
│   ├── state_agg_2018.json
│   ├── national_2018.json
│   ├── tract_agg_2019.json
│   └── ... through 2024 (28 files total)
│
├── downloads/                       (Temp, post-script-3, safe to delete)
│   ├── tl_2010_01_tract10.zip
│   ├── tl_2020_01_tract.zip
│   ├── tl_2020_us_county.zip
│   └── ... (102 tract ZIPs + 1 county ZIP)
│
├── shapefiles/
│   ├── tracts_2010/                (Extracted 2010 shapefiles)
│   │   ├── tl_2010_01_tract10.shp
│   │   ├── tl_2010_01_tract10.dbf
│   │   └── ...
│   │
│   ├── tracts_2020/                (Extracted 2020 shapefiles)
│   │   ├── tl_2020_01_tract.shp
│   │   └── ...
│   │
│   ├── counties_source/            (Extracted national county shapefile)
│   │   ├── tl_2020_us_county.shp
│   │   └── ...
│   │
│   ├── tracts_2010_merged.geojson  (Merged 2010 tracts, ~250 MB)
│   ├── tracts_2020_merged.geojson  (Merged 2020 tracts, ~250 MB)
│   ├── counties_merged.geojson     (~15 MB)
│   └── states.geojson              (~5 MB)
│
├── tiles/                           (Post-script-4)
│   ├── states.pmtiles              (~10-20 MB)
│   ├── counties.pmtiles            (~50-100 MB)
│   ├── tracts_2010.pmtiles         (~200-400 MB)
│   └── tracts_2020.pmtiles         (~200-400 MB)
│   └── Total: ~450-600 MB
│
├── data/                            (Post-script-5)
│   ├── states_2018.json            (30 KB - 51 states)
│   ├── states_2019.json
│   ├── ... through states_2024.json (6 files)
│   ├── counties_2018.json          (200 KB - 3,000 counties)
│   ├── ... through counties_2024.json (6 files)
│   ├── tracts_2010_2018.json       (5 MB - 70,000 tracts)
│   ├── tracts_2010_2019.json
│   ├── ... through tracts_2010_2021.json (4 files)
│   ├── tracts_2020_2022.json       (5 MB - 70,000 tracts)
│   ├── tracts_2020_2023.json
│   ├── tracts_2020_2024.json       (2 files)
│   ├── years.json                  (Compact: [2018, 2019, ..., 2024])
│   ├── homebuyers.json             (Aggregates across all years, ~5 KB)
│   ├── income.json                 (Aggregates across all years, ~2 KB)
│   └── metadata.json               (Build timestamp, ranges, stats)
│   └── Total: ~25-30 MB for all data files
│
├── PIPELINE_README.md              (Complete documentation)
├── QUICKSTART.md                   (Quick reference)
├── STRUCTURE.md                    (This file)
└── index.html                      (Frontend, to be created)
```

## Storage Estimates

| Directory | Size | Deletable? | Notes |
|-----------|------|-----------|-------|
| `raw_data/` | 3-5 GB | Optional | Can be deleted after processing if space needed |
| `processed/` | 50-100 MB | Optional | Can be deleted after script 5 if space needed |
| `downloads/` | 500 MB | **YES** | Safe to delete after script 3 |
| `shapefiles/` (extracted) | 500 MB | Optional | Can be deleted after script 4 |
| `shapefiles/` (GeoJSON) | 500 MB | Keep | Used for debugging/manual edits |
| `tiles/` | 450-600 MB | **KEEP** | Essential for frontend |
| `data/` | 25-30 MB | **KEEP** | Essential for frontend |
| **TOTAL** | ~5.5-6.5 GB | | ~600 MB minimum needed |

## Lean Production Setup

If storage is constrained, after successful pipeline run:

```bash
# Delete temporary files (safe)
rm -rf downloads/
rm -rf shapefiles/tracts_2010/
rm -rf shapefiles/tracts_2020/
rm -rf shapefiles/counties_source/

# Optionally delete raw data and processed (keep for reproducibility)
# rm -rf raw_data/
# rm -rf processed/

# Keep these:
# - shapefiles/*.geojson (for debugging)
# - tiles/*.pmtiles (REQUIRED for frontend)
# - data/*.json (REQUIRED for frontend)
```

This leaves you with ~500 MB for the essential frontend files.

## Script Outputs Summary

### Script 1: Download HMDA
- **Output:** `raw_data/{year}/*.csv`
- **Size:** 3-5 GB (357 files)
- **Can delete:** Yes (after script 2)

### Script 2: Process HMDA
- **Input:** `raw_data/`
- **Output:** `processed/`
- **Size:** 50-100 MB
- **Can delete:** Yes (after script 5)

### Script 3: Download Tiles
- **Output:** `shapefiles/`
- **Size:** 1 GB (including extracts)
- **Keep:** `*.geojson` files only (~500 MB)
- **Delete:** `downloads/` and `*_source/` folders (~500 MB)

### Script 4: Build PMTiles
- **Input:** `shapefiles/*.geojson`
- **Output:** `tiles/*.pmtiles`
- **Size:** 450-600 MB
- **Can delete:** No (essential for frontend)

### Script 5: Build Data Files
- **Input:** `processed/`
- **Output:** `data/*.json`
- **Size:** 25-30 MB
- **Can delete:** No (essential for frontend)

## Recommended Production Folder

For deployment, copy only these to production:

```
production-deploy/
├── tiles/           (450-600 MB) ← PMTiles for MapLibre
├── data/            (25-30 MB)   ← Statistics and metadata
└── index.html       ← Your frontend
```

**Total production size:** ~475-630 MB
