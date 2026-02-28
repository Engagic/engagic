#!/usr/bin/env python3
"""Generate PMTiles from city geometries for map visualization.

Exports city boundaries from PostGIS to GeoJSON, then runs tippecanoe
to generate PMTiles file for MapLibre GL JS.

Usage:
    python scripts/generate_tiles.py --export    # Export to GeoJSON
    python scripts/generate_tiles.py --tiles     # Generate PMTiles
    python scripts/generate_tiles.py --upload    # Upload PMTiles to R2
    python scripts/generate_tiles.py --all       # Full pipeline

Requirements:
    - tippecanoe (brew install tippecanoe or build from source)
    - ogr2ogr (gdal-bin package)
"""

import argparse
import asyncio
import json
import os
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
    """Export cities with geometry to GeoJSON using ogr2ogr for reliable geometry handling."""
    dsn = config.get_postgres_dsn()
    conn = await asyncpg.connect(dsn)

    try:
        # Get meeting stats for each city
        stats_rows = await conn.fetch("""
            SELECT
                banana,
                COUNT(*) as meeting_count,
                COUNT(*) FILTER (WHERE summary IS NOT NULL) as summarized_count
            FROM meetings
            GROUP BY banana
        """)
        meeting_stats = {row["banana"]: dict(row) for row in stats_rows}

        # Count cities with geometry
        count = await conn.fetchval("SELECT COUNT(*) FROM cities WHERE geom IS NOT NULL")
        logger.info("exporting cities via ogr2ogr", count=count)

    finally:
        await conn.close()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Use ogr2ogr to export directly from PostGIS - handles geometry correctly
    pg_conn = f"PG:{dsn}"
    sql = """
        SELECT
            banana,
            name,
            state,
            status,
            vendor,
            population,
            geom
        FROM cities
        WHERE geom IS NOT NULL
        ORDER BY state, name
    """

    result = subprocess.run(
        [
            "ogr2ogr",
            "-f", "GeoJSON",
            str(GEOJSON_PATH),
            pg_conn,
            "-sql", sql,
            "-lco", "RFC7946=YES",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        logger.error("ogr2ogr export failed", stderr=result.stderr)
        print(f"Error: {result.stderr}")
        return

    # Post-process to add meeting stats
    with open(GEOJSON_PATH) as f:
        geojson = json.load(f)

    for feature in geojson["features"]:
        props = feature["properties"]
        banana = props["banana"]
        stats = meeting_stats.get(banana, {"meeting_count": 0, "summarized_count": 0})

        props["meeting_count"] = stats.get("meeting_count", 0)
        props["summarized_count"] = stats.get("summarized_count", 0)
        props["has_data"] = props["meeting_count"] > 0
        props["has_summaries"] = props["summarized_count"] > 0

    geojson["generated_at"] = datetime.now(tz=None).isoformat() + "Z"

    with open(GEOJSON_PATH, "w") as f:
        json.dump(geojson, f)

    logger.info("geojson exported", path=str(GEOJSON_PATH), features=len(geojson["features"]))

    # Summary stats
    with_data = sum(1 for f in geojson["features"] if f["properties"]["has_data"])
    with_summaries = sum(1 for f in geojson["features"] if f["properties"]["has_summaries"])
    total_pop = sum(f["properties"].get("population") or 0 for f in geojson["features"])
    pop_with_data = sum(
        f["properties"].get("population") or 0
        for f in geojson["features"]
        if f["properties"]["has_data"]
    )
    print("\nExport Summary:")
    print(f"  Total cities with geometry: {len(geojson['features'])}")
    print(f"  Cities with meeting data: {with_data}")
    print(f"  Cities with summaries: {with_summaries}")
    print(f"  Total population: {total_pop:,}")
    print(f"  Population with data: {pop_with_data:,}")


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


FRONTEND_DIR = Path("/opt/engagic/frontend")


def upload_r2() -> None:
    """Upload PMTiles to Cloudflare R2 via wrangler CLI."""
    if not PMTILES_PATH.exists():
        logger.error("pmtiles not found, run --tiles first")
        return

    # Load token from .llm_secrets if not already in environment
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token:
        secrets_path = Path("/opt/engagic/.llm_secrets")
        if secrets_path.exists():
            for line in secrets_path.read_text().splitlines():
                if line.startswith("CLOUDFLARE_API_TOKEN="):
                    token = line.split("=", 1)[1]
                    break
    if not token:
        logger.error("CLOUDFLARE_API_TOKEN not found in environment or .llm_secrets")
        print("Error: set CLOUDFLARE_API_TOKEN or add it to .llm_secrets")
        return

    env = {**os.environ, "CLOUDFLARE_API_TOKEN": token}

    size_mb = PMTILES_PATH.stat().st_size / (1024 * 1024)
    logger.info("uploading to R2", file=str(PMTILES_PATH), size_mb=f"{size_mb:.1f}")
    print(f"\nUploading {size_mb:.1f} MB to R2 bucket engagic-tiles...")

    result = subprocess.run(
        [
            "npx", "wrangler", "r2", "object", "put",
            "engagic-tiles/cities.pmtiles",
            f"--file={PMTILES_PATH}",
            "--content-type=application/octet-stream",
        ],
        capture_output=True,
        text=True,
        cwd=FRONTEND_DIR,
        env=env,
    )

    if result.returncode != 0:
        logger.error("R2 upload failed", stderr=result.stderr)
        print(f"Error: {result.stderr}")
        return

    logger.info("R2 upload complete")
    print("R2 upload complete: engagic-tiles/cities.pmtiles")


async def main():
    parser = argparse.ArgumentParser(description="Generate map tiles")
    parser.add_argument("--export", action="store_true", help="Export GeoJSON from database")
    parser.add_argument("--tiles", action="store_true", help="Generate PMTiles")
    parser.add_argument("--deploy", action="store_true", help="Deploy to static directory")
    parser.add_argument("--upload", action="store_true", help="Upload PMTiles to Cloudflare R2")
    parser.add_argument("--all", action="store_true", help="Full pipeline")
    args = parser.parse_args()

    if args.all or args.export:
        await export_geojson()

    if args.all or args.tiles:
        generate_pmtiles()

    if args.all or args.deploy:
        deploy_tiles()

    if args.all or args.upload:
        upload_r2()

    if not any([args.export, args.tiles, args.deploy, args.upload, args.all]):
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
