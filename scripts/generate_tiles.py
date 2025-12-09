#!/usr/bin/env python3
"""Generate PMTiles from city geometries for map visualization.

Exports city boundaries from PostGIS to GeoJSON, then runs tippecanoe
to generate PMTiles file for MapLibre GL JS.

Usage:
    python scripts/generate_tiles.py --export    # Export to GeoJSON
    python scripts/generate_tiles.py --tiles     # Generate PMTiles
    python scripts/generate_tiles.py --all       # Full pipeline

Requirements:
    - tippecanoe (brew install tippecanoe or build from source)
    - ogr2ogr (gdal-bin package)
"""

import argparse
import asyncio
import json
import subprocess
from datetime import datetime
from pathlib import Path

import asyncpg

from config import config, get_logger

logger = get_logger(__name__).bind(component="tile_generation")

# Output paths
DATA_DIR = Path("/opt/engagic/data")
GEOJSON_PATH = DATA_DIR / "cities.geojson"
PMTILES_PATH = DATA_DIR / "cities.pmtiles"
STATIC_TILES_PATH = Path("/opt/engagic/frontend/static/tiles")


async def export_geojson() -> None:
    """Export cities with geometry to GeoJSON with styling properties."""
    dsn = config.get_postgres_dsn()
    conn = await asyncpg.connect(dsn)

    try:
        # Get cities with geometry and meeting stats
        rows = await conn.fetch("""
            SELECT
                c.banana,
                c.name,
                c.state,
                c.status,
                c.vendor,
                ST_AsGeoJSON(c.geom)::json as geometry,
                COALESCE(m.meeting_count, 0) as meeting_count,
                COALESCE(m.summarized_count, 0) as summarized_count
            FROM cities c
            LEFT JOIN (
                SELECT
                    banana,
                    COUNT(*) as meeting_count,
                    COUNT(*) FILTER (WHERE summary IS NOT NULL) as summarized_count
                FROM meetings
                GROUP BY banana
            ) m ON c.banana = m.banana
            WHERE c.geom IS NOT NULL
            ORDER BY c.state, c.name
        """)

        logger.info("exporting cities", count=len(rows))

        # Build GeoJSON FeatureCollection
        features = []
        for row in rows:
            # Determine population status for styling
            # "populated" = has meeting data we can show
            has_data = row["meeting_count"] > 0
            has_summaries = row["summarized_count"] > 0

            feature = {
                "type": "Feature",
                "properties": {
                    "banana": row["banana"],
                    "name": row["name"],
                    "state": row["state"],
                    "status": row["status"],
                    "vendor": row["vendor"],
                    "meeting_count": row["meeting_count"],
                    "summarized_count": row["summarized_count"],
                    "has_data": has_data,
                    "has_summaries": has_summaries,
                },
                "geometry": row["geometry"],
            }
            features.append(feature)

        geojson = {
            "type": "FeatureCollection",
            "features": features,
            "generated_at": datetime.utcnow().isoformat() + "Z",
        }

        # Write to file
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(GEOJSON_PATH, "w") as f:
            json.dump(geojson, f)

        logger.info("geojson exported", path=str(GEOJSON_PATH), features=len(features))

        # Summary stats
        with_data = sum(1 for f in features if f["properties"]["has_data"])
        with_summaries = sum(1 for f in features if f["properties"]["has_summaries"])
        print(f"\nExport Summary:")
        print(f"  Total cities with geometry: {len(features)}")
        print(f"  Cities with meeting data: {with_data}")
        print(f"  Cities with summaries: {with_summaries}")

    finally:
        await conn.close()


def generate_pmtiles() -> None:
    """Run tippecanoe to generate PMTiles from GeoJSON."""
    if not GEOJSON_PATH.exists():
        logger.error("geojson not found, run --export first", path=str(GEOJSON_PATH))
        return

    logger.info("generating pmtiles")

    # tippecanoe options:
    # -o: output file
    # -Z: minimum zoom (3 = continental view)
    # -z: maximum zoom (12 = city-level detail)
    # -S: simplification at low zooms (smoother boundaries)
    # --detect-shared-borders: clean up shared city boundaries
    # -l: layer name
    # --force: overwrite existing
    result = subprocess.run(
        [
            "tippecanoe",
            "-o", str(PMTILES_PATH),
            "-Z", "3",
            "-z", "12",
            "-S", "10",
            "--detect-shared-borders",
            "-l", "cities",
            "--force",
            str(GEOJSON_PATH),
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        logger.error("tippecanoe failed", stderr=result.stderr)
        print(f"Error: {result.stderr}")
        return

    # Get file size
    size_mb = PMTILES_PATH.stat().st_size / (1024 * 1024)
    logger.info("pmtiles generated", path=str(PMTILES_PATH), size_mb=f"{size_mb:.1f}")
    print(f"\nPMTiles generated: {PMTILES_PATH}")
    print(f"File size: {size_mb:.1f} MB")


def deploy_tiles() -> None:
    """Copy PMTiles to frontend static directory."""
    if not PMTILES_PATH.exists():
        logger.error("pmtiles not found, run --tiles first")
        return

    STATIC_TILES_PATH.mkdir(parents=True, exist_ok=True)
    dest = STATIC_TILES_PATH / "cities.pmtiles"

    import shutil
    shutil.copy2(PMTILES_PATH, dest)

    logger.info("tiles deployed", dest=str(dest))
    print(f"\nTiles deployed to: {dest}")


async def main():
    parser = argparse.ArgumentParser(description="Generate map tiles")
    parser.add_argument("--export", action="store_true", help="Export GeoJSON from database")
    parser.add_argument("--tiles", action="store_true", help="Generate PMTiles")
    parser.add_argument("--deploy", action="store_true", help="Deploy to static directory")
    parser.add_argument("--all", action="store_true", help="Full pipeline")
    args = parser.parse_args()

    if args.all or args.export:
        await export_geojson()

    if args.all or args.tiles:
        generate_pmtiles()

    if args.all or args.deploy:
        deploy_tiles()

    if not any([args.export, args.tiles, args.deploy, args.all]):
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
