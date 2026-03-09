#!/usr/bin/env python3
"""
Pipeline Script 3: Download Census TIGER Shapefiles and Build GeoJSON

Downloads state census tract shapefiles for 2010 and 2020 epochs, plus national county file.
Merges and simplifies geometries. Outputs merged GeoJSON files for use in PMTiles generation.

Requirements: geopandas, pandas, shapely

Run from: National Dashboard/
"""

import os
import sys
import json
import zipfile
import requests
import shutil
from pathlib import Path
from typing import Dict, List

import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon, shape as sh_shape


# ---------------------------------------------------------------------------
# Fiona-free I/O helpers
# Uses pyshp (pip install pyshp) for reading shapefiles and plain json for
# writing GeoJSON, so neither fiona nor pyogrio is required.
# ---------------------------------------------------------------------------

def read_shapefile_native(shp_path: Path) -> gpd.GeoDataFrame:
    """Read a shapefile using pyshp — no fiona / pyogrio needed."""
    try:
        import shapefile as shplib
    except ImportError:
        print("  ERROR: pyshp not installed. Run: pip install pyshp")
        raise

    sf = shplib.Reader(str(shp_path))
    field_names = [f[0] for f in sf.fields[1:]]   # skip deletion-flag field

    rows = []
    for rec in sf.iterShapeRecords():
        geom = sh_shape(rec.shape.__geo_interface__)
        row = dict(zip(field_names, rec.record))
        row['geometry'] = geom
        rows.append(row)

    return gpd.GeoDataFrame(rows, geometry='geometry', crs='EPSG:4326')


def read_geojson_native(geojson_path: Path) -> gpd.GeoDataFrame:
    """Read a GeoJSON file without fiona."""
    with open(geojson_path) as f:
        data = json.load(f)

    rows = []
    for feature in data['features']:
        props = dict(feature.get('properties') or {})
        props['geometry'] = sh_shape(feature['geometry'])
        rows.append(props)

    return gpd.GeoDataFrame(rows, geometry='geometry', crs='EPSG:4326')


def write_geojson_native(gdf: gpd.GeoDataFrame, output_path: Path) -> None:
    """Write a GeoDataFrame to GeoJSON without fiona."""
    def _py(v):
        """Convert numpy scalars to plain Python types."""
        if hasattr(v, 'item'):
            return v.item()
        if v != v:          # NaN check
            return None
        return v

    features = []
    for _, row in gdf.iterrows():
        geom = row['geometry']
        props = {k: _py(v) for k, v in row.items() if k != 'geometry'}
        features.append({
            'type': 'Feature',
            'geometry': geom.__geo_interface__,
            'properties': props
        })

    with open(output_path, 'w') as f:
        json.dump({'type': 'FeatureCollection', 'features': features}, f)

# State FIPS codes (2-digit, zero-padded)
STATE_FIPS_2DIGIT = [
    "01", "02", "04", "05", "06", "08", "09", "10",
    "11", "12", "13", "15", "16", "17", "18", "19",
    "20", "21", "22", "23", "24", "25", "26", "27",
    "28", "29", "30", "31", "32", "33", "34", "35",
    "36", "37", "38", "39", "40", "41", "42", "44",
    "45", "46", "47", "48", "49", "50", "51", "53",
    "54", "55", "56"
]

def get_script_dir() -> Path:
    """Return the directory where this script is located."""
    return Path(__file__).parent.parent

def download_file(url: str, output_path: Path, description: str = "") -> bool:
    """
    Download a file from URL to output_path.

    Returns True if successful, False otherwise.
    Skips if file already exists.
    """
    if output_path.exists():
        print(f"  SKIP {description} ({output_path.name})")
        return True

    try:
        print(f"  FETCH {description}...", end=' ', flush=True)
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        output_path.write_bytes(response.content)
        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"OK ({size_mb:.1f} MB)")
        return True
    except Exception as e:
        print(f"FAIL: {e}")
        return False

def extract_zip(zip_path: Path, extract_dir: Path) -> bool:
    """
    Extract ZIP file to extract_dir.

    Returns True if successful.
    """
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(extract_dir)
        return True
    except Exception as e:
        print(f"  ERROR extracting {zip_path.name}: {e}")
        return False

def download_tracts(base_dir: Path, epoch: int) -> bool:
    """
    Download all state tract shapefiles for a given census epoch (2000, 2010 or 2020).

    2000-boundary tracts are published in the TIGER2010 archive as tl_2010_XX_tract00.zip.
    2010 tracts: TIGER2010/TRACT/2010/tl_2010_XX_tract10.zip
    2020 tracts: TIGER2020/TRACT/tl_2020_XX_tract.zip

    Returns True if all downloads succeeded.
    """
    print(f"\n=== Downloading {epoch} Census Tracts ===")

    success_count = 0
    fail_count = 0

    for fips2 in STATE_FIPS_2DIGIT:
        if epoch == 2000:
            # 2000 boundaries stored in TIGER2010 archive with "00" suffix
            zip_name = f"tl_2010_{fips2}_tract00.zip"
            url = f"https://www2.census.gov/geo/tiger/TIGER2010/TRACT/2000/{zip_name}"
        elif epoch == 2010:
            zip_name = f"tl_2010_{fips2}_tract10.zip"
            url = f"https://www2.census.gov/geo/tiger/TIGER2010/TRACT/2010/{zip_name}"
        else:  # 2020
            zip_name = f"tl_2020_{fips2}_tract.zip"
            url = f"https://www2.census.gov/geo/tiger/TIGER2020/TRACT/{zip_name}"

        zip_path = base_dir / "downloads" / zip_name

        if download_file(url, zip_path, f"{epoch} tracts FIPS {fips2}"):
            success_count += 1
        else:
            fail_count += 1

    print(f"\n{epoch} Tracts: {success_count} OK, {fail_count} FAIL")
    return fail_count == 0

def extract_tracts(base_dir: Path, epoch: int) -> bool:
    """Extract all downloaded tract ZIPs."""
    print(f"\nExtracting {epoch} tracts...")

    extract_dir = base_dir / f"shapefiles/tracts_{epoch}"
    extract_dir.mkdir(parents=True, exist_ok=True)

    downloads_dir = base_dir / "downloads"
    # Use epoch-specific glob patterns to avoid cross-contamination between
    # 2000 ("tl_2010_XX_tract00.zip") and 2010 ("tl_2010_XX_tract10.zip") files
    if epoch == 2000:
        glob_pat = "tl_2010_*_tract00.zip"
    elif epoch == 2010:
        glob_pat = "tl_2010_*_tract10.zip"
    else:  # 2020
        glob_pat = "tl_2020_*_tract.zip"
    zip_files = sorted(downloads_dir.glob(glob_pat))

    for zip_path in zip_files:
        print(f"  Extracting {zip_path.name}...")
        if not extract_zip(zip_path, extract_dir):
            return False

    return True

def download_counties(base_dir: Path) -> bool:
    """Download national county shapefile."""
    print(f"\n=== Downloading National County Shapefile ===")

    url = "https://www2.census.gov/geo/tiger/TIGER2020/COUNTY/tl_2020_us_county.zip"
    zip_path = base_dir / "downloads" / "tl_2020_us_county.zip"

    return download_file(url, zip_path, "National counties (2020)")

def extract_counties(base_dir: Path) -> bool:
    """Extract county ZIP."""
    print(f"\nExtracting counties...")

    extract_dir = base_dir / "shapefiles/counties_source"
    extract_dir.mkdir(parents=True, exist_ok=True)

    zip_path = base_dir / "downloads" / "tl_2020_us_county.zip"

    if not zip_path.exists():
        print(f"  ERROR: {zip_path} not found")
        return False

    return extract_zip(zip_path, extract_dir)

def merge_tracts(base_dir: Path, epoch: int) -> bool:
    """
    Merge all state tract shapefiles for an epoch into a single GeoJSON.

    Returns True if successful.
    """
    print(f"\nMerging {epoch} tracts...")

    source_dir = base_dir / f"shapefiles/tracts_{epoch}"
    # Only include tract shapefiles (e.g. tl_2020_01_tract.shp), never county or other files
    shapefiles = sorted(p for p in source_dir.glob("*.shp") if "tract" in p.name.lower())

    if not shapefiles:
        print(f"  ERROR: No shapefiles found in {source_dir}")
        return False

    gdfs = []
    for shp_path in shapefiles:
        try:
            gdf = read_shapefile_native(shp_path)
            # Use GEOID column (or equivalent)
            # 2000 TIGER files use CTIDFP00; 2010 use GEOID10; 2020 use GEOID20
            if 'GEOID10' in gdf.columns:
                gdf['GEOID'] = gdf['GEOID10']
            elif 'GEOID20' in gdf.columns:
                gdf['GEOID'] = gdf['GEOID20']
            elif 'CTIDFP00' in gdf.columns:
                gdf['GEOID'] = gdf['CTIDFP00']
            elif 'GEOID' not in gdf.columns:
                print(f"  WARNING: No GEOID column in {shp_path.name}")
                continue

            # Keep only relevant columns
            gdf = gdf[['GEOID', 'geometry']]
            gdfs.append(gdf)
            print(f"  Loaded {shp_path.name}: {len(gdf)} features")
        except Exception as e:
            print(f"  ERROR loading {shp_path.name}: {e}")
            return False

    # Merge all
    merged = pd.concat(gdfs, ignore_index=True)
    print(f"  Merged: {len(merged)} total features")

    # Ensure GEOID is 11-char zero-padded
    merged['GEOID'] = merged['GEOID'].astype(str).str.zfill(11)
    merged = merged.set_index('GEOID')

    # Simplify geometries
    print(f"  Simplifying geometries...")
    merged['geometry'] = merged['geometry'].simplify(0.00005, preserve_topology=True)

    # Set feature ID for MapLibre feature-state
    merged = merged.reset_index()
    merged = merged.rename(columns={'GEOID': 'id'})

    # Convert to GeoDataFrame
    merged_gdf = gpd.GeoDataFrame(merged, geometry='geometry', crs='EPSG:4326')

    # Write GeoJSON with feature IDs
    output_path = base_dir / f"shapefiles/tracts_{epoch}_merged.geojson"
    write_geojson_native(merged_gdf, output_path)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  Wrote {output_path.name}: {len(merged_gdf)} features, {size_mb:.1f} MB")

    return True

def merge_counties(base_dir: Path) -> bool:
    """
    Merge national county shapefile into a single GeoJSON.

    Returns True if successful.
    """
    print(f"\nMerging counties...")

    source_dir = base_dir / "shapefiles/counties_source"
    shapefiles = sorted(source_dir.glob("*.shp"))

    if not shapefiles:
        print(f"  ERROR: No shapefiles found in {source_dir}")
        return False

    try:
        gdf = read_shapefile_native(shapefiles[0])
        print(f"  Loaded {shapefiles[0].name}: {len(gdf)} features")

        # Ensure GEOID is 5-char zero-padded
        if 'GEOID' not in gdf.columns:
            print(f"  ERROR: No GEOID column")
            return False

        gdf['GEOID'] = gdf['GEOID'].astype(str).str.zfill(5)
        gdf = gdf.set_index('GEOID')

        # Simplify geometries
        print(f"  Simplifying geometries...")
        gdf['geometry'] = gdf['geometry'].simplify(0.00005, preserve_topology=True)

        # Reset index for feature ID
        gdf = gdf.reset_index()
        gdf = gdf.rename(columns={'GEOID': 'id'})

        # Write GeoJSON
        output_path = base_dir / "shapefiles/counties_merged.geojson"
        write_geojson_native(gdf, output_path)

        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"  Wrote {output_path.name}: {len(gdf)} features, {size_mb:.1f} MB")

        return True

    except Exception as e:
        print(f"  ERROR: {e}")
        return False

def build_states_from_counties(base_dir: Path) -> bool:
    """
    Build state boundaries by dissolving counties.

    Returns True if successful.
    """
    print(f"\nBuilding state boundaries...")

    county_path = base_dir / "shapefiles/counties_merged.geojson"

    if not county_path.exists():
        print(f"  ERROR: {county_path} not found")
        return False

    try:
        counties = read_geojson_native(county_path)
        print(f"  Loaded counties: {len(counties)} features")

        # State FIPS is first 2 digits of 5-digit county FIPS
        counties['STATE_FIPS'] = counties['id'].astype(str).str[:2]

        # Dissolve by state
        states = counties.dissolve(by='STATE_FIPS')
        states = states.reset_index()

        # Drop any pre-existing 'id' column from county data (would cause
        # a duplicate column collision when we rename STATE_FIPS → id)
        if 'id' in states.columns:
            states = states.drop(columns=['id'])
        states = states.rename(columns={'STATE_FIPS': 'id'})

        # Add human-readable state name
        STATE_NAMES = {
            '01':'Alabama','02':'Alaska','04':'Arizona','05':'Arkansas',
            '06':'California','08':'Colorado','09':'Connecticut','10':'Delaware',
            '11':'District of Columbia','12':'Florida','13':'Georgia','15':'Hawaii',
            '16':'Idaho','17':'Illinois','18':'Indiana','19':'Iowa','20':'Kansas',
            '21':'Kentucky','22':'Louisiana','23':'Maine','24':'Maryland',
            '25':'Massachusetts','26':'Michigan','27':'Minnesota','28':'Mississippi',
            '29':'Missouri','30':'Montana','31':'Nebraska','32':'Nevada',
            '33':'New Hampshire','34':'New Jersey','35':'New Mexico','36':'New York',
            '37':'North Carolina','38':'North Dakota','39':'Ohio','40':'Oklahoma',
            '41':'Oregon','42':'Pennsylvania','44':'Rhode Island','45':'South Carolina',
            '46':'South Dakota','47':'Tennessee','48':'Texas','49':'Utah',
            '50':'Vermont','51':'Virginia','53':'Washington','54':'West Virginia',
            '55':'Wisconsin','56':'Wyoming','60':'American Samoa','66':'Guam',
            '69':'Northern Mariana Islands','72':'Puerto Rico','78':'Virgin Islands',
        }
        states['NAME'] = states['id'].map(STATE_NAMES).fillna(states['id'])

        # Keep only the essential columns (drop leftover county columns)
        states = states[['id', 'NAME', 'geometry']]

        # Extract exterior ring only (keep as Polygon)
        def get_exterior(geom):
            if geom.geom_type == 'Polygon':
                return Polygon(geom.exterior)
            elif geom.geom_type == 'MultiPolygon':
                # Get largest polygon
                largest = max(geom.geoms, key=lambda p: p.area)
                return Polygon(largest.exterior)
            else:
                return geom

        states['geometry'] = states['geometry'].apply(get_exterior)

        print(f"  Dissolved to {len(states)} states")

        # Simplify
        states['geometry'] = states['geometry'].simplify(0.001, preserve_topology=True)

        # Write GeoJSON
        output_path = base_dir / "shapefiles/states.geojson"
        write_geojson_native(states, output_path)

        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"  Wrote {output_path.name}: {len(states)} features, {size_mb:.1f} MB")

        return True

    except Exception as e:
        print(f"  ERROR: {e}")
        return False

def main():
    """Download and process Census TIGER shapefiles."""
    script_dir = get_script_dir()
    base_dir = script_dir

    print("=== Census TIGER Shapefile Pipeline ===")
    print(f"Base directory: {base_dir}\n")

    # Create downloads directory
    downloads_dir = base_dir / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)

    # Download tracts (all three census epochs)
    success = True

    if not download_tracts(base_dir, 2000):  # 2007-2011 HMDA data
        success = False
    if not download_tracts(base_dir, 2010):  # 2012-2021 HMDA data
        success = False
    if not download_tracts(base_dir, 2020):  # 2022+ HMDA data
        success = False

    # Download counties
    if not download_counties(base_dir):
        success = False

    if not success:
        print("\n=== Some downloads failed ===")
        sys.exit(1)

    # Extract
    if not extract_tracts(base_dir, 2000):
        sys.exit(1)
    if not extract_tracts(base_dir, 2010):
        sys.exit(1)
    if not extract_tracts(base_dir, 2020):
        sys.exit(1)
    if not extract_counties(base_dir):
        sys.exit(1)

    # Merge and simplify
    if not merge_tracts(base_dir, 2000):
        sys.exit(1)
    if not merge_tracts(base_dir, 2010):
        sys.exit(1)
    if not merge_tracts(base_dir, 2020):
        sys.exit(1)
    if not merge_counties(base_dir):
        sys.exit(1)
    if not build_states_from_counties(base_dir):
        sys.exit(1)

    print("\n=== All shapefile processing complete ===")
    print("Next: python pipeline/4_build_pmtiles.py")
    sys.exit(0)

if __name__ == "__main__":
    main()
