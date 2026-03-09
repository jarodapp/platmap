# Quick Start Guide

## Prerequisites

```bash
# Install Python dependencies
pip install requests pandas numpy geopandas shapely

# Install tippecanoe
sudo apt-get install -y tippecanoe  # Linux
# OR
brew install tippecanoe  # macOS
```

## Run the Pipeline

From the `National Dashboard/` directory:

```bash
# 1. Download HMDA data (6-10 hours)
python3 pipeline/1_download_hmda.py

# 2. Process into aggregates (5-15 minutes)
python3 pipeline/2_process_hmda.py

# 3. Download shapefiles & build GeoJSON (20-40 minutes)
python3 pipeline/3_download_tiles.py

# 4. Build PMTiles (30-60 minutes)
python3 pipeline/4_build_pmtiles.py

# 5. Generate frontend data files (1-2 minutes)
python3 pipeline/5_build_data_files.py
```

**Total time:** ~8-15 hours

## Verify Output

```bash
# Check each directory was populated
ls raw_data/2024/ | wc -l           # Should be 51
ls processed/*_2024.json | wc -l    # Should be 4
ls shapefiles/*.geojson             # Should be 4 files
ls -lh tiles/*.pmtiles              # Should be 4 files
ls data/*.json | wc -l              # Should be 8+ files
```

## What You Get

- **`tiles/`**: 4 PMTiles files ready for MapLibre GL
- **`data/`**: JSON files for frontend (years, stats, geometries)
- **`shapefiles/`**: Merged GeoJSON (useful for debugging)

## Next Steps

1. Set up `index.html` with MapLibre GL
2. Load `tiles/*.pmtiles` as vector sources
3. Load `data/*.json` for charts and filters
4. Serve with `python3 -m http.server 8000`

See `PIPELINE_README.md` for full documentation.
