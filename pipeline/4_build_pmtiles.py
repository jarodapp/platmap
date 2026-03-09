#!/usr/bin/env python3
"""
Pipeline Script 4: Build PMTiles from Merged GeoJSONs

Uses tippecanoe to generate PMTiles for each tile layer:
- states: z2-z6
- counties: z4-z9
- tracts_2000: z7-z14  (2007-2011 HMDA data)
- tracts_2010: z7-z14  (2012-2021 HMDA data)
- tracts_2020: z7-z14  (2022+ HMDA data)

Skips output if file already exists (unless --force is passed).

Requirements: tippecanoe (https://github.com/felt/tippecanoe)

Run from: National Dashboard/
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import List

def get_script_dir() -> Path:
    """Return the directory where this script is located."""
    return Path(__file__).parent.parent

def check_tippecanoe() -> bool:
    """
    Check if tippecanoe is installed.

    Returns True if available, False otherwise.
    """
    try:
        result = subprocess.run(
            ["tippecanoe", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False

def install_tippecanoe_instructions():
    """Print installation instructions for tippecanoe."""
    print("\nWARNING: tippecanoe not found")
    print("\nInstall tippecanoe:")
    print("  Ubuntu/Debian:")
    print("    sudo apt-get update")
    print("    sudo apt-get install -y tippecanoe")
    print("\n  macOS:")
    print("    brew install tippecanoe")
    print("\n  From source:")
    print("    https://github.com/felt/tippecanoe")

def run_tippecanoe(
    input_geojson: Path,
    output_pmtiles: Path,
    layer_name: str,
    min_zoom: int,
    max_zoom: int,
    force: bool = False
) -> bool:
    """
    Run tippecanoe to generate PMTiles.

    Args:
        input_geojson: Path to input GeoJSON file
        output_pmtiles: Path to output PMTiles file
        layer_name: Name of the layer in PMTiles
        min_zoom: Minimum zoom level
        max_zoom: Maximum zoom level
        force: If True, overwrite existing output

    Returns True if successful, False otherwise.
    """
    # Skip if output already exists and not forcing
    if output_pmtiles.exists() and not force:
        size_mb = output_pmtiles.stat().st_size / (1024 * 1024)
        print(f"  SKIP {output_pmtiles.name} (exists, {size_mb:.1f} MB)")
        return True

    # Input validation
    if not input_geojson.exists():
        print(f"  ERROR: Input {input_geojson.name} not found")
        return False

    input_size_mb = input_geojson.stat().st_size / (1024 * 1024)
    print(f"  Processing {input_geojson.name} ({input_size_mb:.1f} MB)...", flush=True)

    # Build tippecanoe command
    # -T id:string  prevents tippecanoe's default behaviour of converting all-numeric
    # string property values (like GEOIDs "01001020100") to integers in the vector
    # tile — which would silently drop the leading zero and break feature-state lookups
    # for states with FIPS 01–09 (AL, AK, AZ, AR, CA, CO, CT).
    cmd = [
        "tippecanoe",
        "-o", str(output_pmtiles),
        "-l", layer_name,
        "-z", str(max_zoom),
        "-Z", str(min_zoom),
        "-T", "id:string",
        "--drop-densest-as-needed",
        "--detect-shared-borders",
        "--force"
    ]

    # Add coalesce-densest-as-needed for tracts (large feature counts)
    if "tract" in layer_name.lower():
        cmd.append("--coalesce-densest-as-needed")

    # Add input file
    cmd.append(str(input_geojson))

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        if result.returncode != 0:
            print(f"    ERROR: tippecanoe failed")
            print(f"    {result.stderr}")
            return False

        output_size_mb = output_pmtiles.stat().st_size / (1024 * 1024)
        print(f"    OK {output_pmtiles.name} ({output_size_mb:.1f} MB)")
        return True

    except subprocess.TimeoutExpired:
        print(f"    ERROR: tippecanoe timed out after 10 minutes")
        return False
    except Exception as e:
        print(f"    ERROR: {e}")
        return False

def main():
    """Build all PMTiles."""
    script_dir = get_script_dir()

    print("=== PMTiles Builder ===\n")

    # Check tippecanoe
    if not check_tippecanoe():
        install_tippecanoe_instructions()
        sys.exit(1)

    print("tippecanoe found. Proceeding...\n")

    # Parse --force flag
    force = "--force" in sys.argv

    # Define tile layers
    tiles_dir = script_dir / "tiles"
    tiles_dir.mkdir(parents=True, exist_ok=True)

    layers = [
        {
            "name": "states",
            "input": script_dir / "shapefiles/states.geojson",
            "output": tiles_dir / "states.pmtiles",
            "min_zoom": 2,
            "max_zoom": 6
        },
        {
            "name": "counties",
            "input": script_dir / "shapefiles/counties_merged.geojson",
            "output": tiles_dir / "counties.pmtiles",
            "min_zoom": 4,
            "max_zoom": 9
        },
        {
            "name": "tracts",
            "input": script_dir / "shapefiles/tracts_2000_merged.geojson",
            "output": tiles_dir / "tracts_2000.pmtiles",
            "min_zoom": 7,
            "max_zoom": 14
        },
        {
            "name": "tracts",
            "input": script_dir / "shapefiles/tracts_2010_merged.geojson",
            "output": tiles_dir / "tracts_2010.pmtiles",
            "min_zoom": 7,
            "max_zoom": 14
        },
        {
            "name": "tracts",
            "input": script_dir / "shapefiles/tracts_2020_merged.geojson",
            "output": tiles_dir / "tracts_2020.pmtiles",
            "min_zoom": 7,
            "max_zoom": 14
        }
    ]

    # Build each layer
    successes = 0
    failures = 0

    for layer in layers:
        if run_tippecanoe(
            input_geojson=layer["input"],
            output_pmtiles=layer["output"],
            layer_name=layer["name"],
            min_zoom=layer["min_zoom"],
            max_zoom=layer["max_zoom"],
            force=force
        ):
            successes += 1
        else:
            failures += 1

    print(f"\n=== Summary ===")
    print(f"Tiles built: {successes}/5")

    if failures > 0:
        print(f"Failures: {failures}")
        sys.exit(1)
    else:
        print("\nAll PMTiles built successfully!")
        print("\nNext steps:")
        print("  1. python pipeline/5_build_data_files.py")
        print("  2. python serve.py (to test locally)")
        sys.exit(0)

if __name__ == "__main__":
    main()
