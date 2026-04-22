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

    # Coverage taxonomy (mirrors /api/city-coverage in server/routes/monitoring.py):
    #   matter     - city_matters.canonical_summary (deepest, post-2026-04-11 refactor)
    #   item       - items.summary for items NOT rolled up to a canonical matter summary
    #   monolithic - legacy meetings.summary (whole-meeting summaries)
    #   synced     - meetings exist but nothing summarized yet
    #   pending    - jurisdiction has geometry but no meetings
    try:
        stats_rows = await conn.fetch("""
            WITH
                matter_counts AS (
                    SELECT banana, COUNT(*) AS cnt
                    FROM city_matters
                    WHERE canonical_summary IS NOT NULL AND canonical_summary != ''
                    GROUP BY banana
                ),
                item_counts AS (
                    SELECT m.banana, COUNT(*) AS cnt
                    FROM items i
                    JOIN meetings m ON i.meeting_id = m.id
                    WHERE i.summary IS NOT NULL AND i.summary != ''
                      AND (i.matter_id IS NULL OR i.matter_id NOT IN (
                          SELECT id FROM city_matters
                          WHERE canonical_summary IS NOT NULL AND canonical_summary != ''
                      ))
                    GROUP BY m.banana
                ),
                meeting_counts AS (
                    SELECT banana, COUNT(*) AS cnt
                    FROM meetings
                    WHERE summary IS NOT NULL AND summary != ''
                    GROUP BY banana
                ),
                synced_counts AS (
                    SELECT banana, COUNT(*) AS cnt
                    FROM meetings
                    WHERE title IS NOT NULL AND title != ''
                      AND date IS NOT NULL
                    GROUP BY banana
                )
            SELECT
                c.banana,
                CASE
                    WHEN COALESCE(mc.cnt, 0) > 0 THEN 'matter'
                    WHEN COALESCE(ic.cnt, 0) > 0 THEN 'item'
                    WHEN COALESCE(mtg.cnt, 0) > 0 THEN 'monolithic'
                    WHEN COALESCE(sc.cnt, 0) > 0 THEN 'synced'
                    ELSE 'pending'
                END AS coverage_type,
                CASE
                    WHEN COALESCE(mc.cnt, 0) > 0 THEN mc.cnt + COALESCE(ic.cnt, 0)
                    WHEN COALESCE(ic.cnt, 0) > 0 THEN ic.cnt
                    WHEN COALESCE(mtg.cnt, 0) > 0 THEN mtg.cnt
                    WHEN COALESCE(sc.cnt, 0) > 0 THEN sc.cnt
                    ELSE 0
                END AS summary_count
            FROM jurisdictions c
            LEFT JOIN matter_counts mc ON c.banana = mc.banana
            LEFT JOIN item_counts ic ON c.banana = ic.banana
            LEFT JOIN meeting_counts mtg ON c.banana = mtg.banana
            LEFT JOIN synced_counts sc ON c.banana = sc.banana
            WHERE c.geom IS NOT NULL
        """)
        coverage = {
            row["banana"]: {"coverage_type": row["coverage_type"], "summary_count": row["summary_count"]}
            for row in stats_rows
        }

        logger.info("exporting cities via ogr2ogr", count=len(coverage))

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
        FROM jurisdictions
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

    # Post-process: bake coverage_type + summary_count into each feature
    with open(GEOJSON_PATH) as f:
        geojson = json.load(f)

    for feature in geojson["features"]:
        props = feature["properties"]
        row = coverage.get(props["banana"], {"coverage_type": "pending", "summary_count": 0})
        props["coverage_type"] = row["coverage_type"]
        props["summary_count"] = row["summary_count"]

    geojson["generated_at"] = datetime.now(tz=None).isoformat() + "Z"

    with open(GEOJSON_PATH, "w") as f:
        json.dump(geojson, f)

    logger.info("geojson exported", path=str(GEOJSON_PATH), features=len(geojson["features"]))

    # Summary stats by tier
    tier_counts: dict[str, int] = {}
    for f in geojson["features"]:
        t = f["properties"]["coverage_type"]
        tier_counts[t] = tier_counts.get(t, 0) + 1
    total_pop = sum(f["properties"].get("population") or 0 for f in geojson["features"])
    pop_covered = sum(
        f["properties"].get("population") or 0
        for f in geojson["features"]
        if f["properties"]["coverage_type"] != "pending"
    )
    print("\nExport Summary:")
    print(f"  Total cities with geometry: {len(geojson['features'])}")
    for tier in ("matter", "item", "monolithic", "synced", "pending"):
        print(f"  {tier}: {tier_counts.get(tier, 0)}")
    print(f"  Total population: {total_pop:,}")
    print(f"  Population with data: {pop_covered:,}")


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

    # Load credentials from .llm_secrets if not already in environment.
    # CLOUDFLARE_ACCOUNT_ID skips wrangler's /memberships lookup, which requires
    # User:Read scope the R2-only token doesn't have.
    cf_vars: dict[str, str | None] = {
        "CLOUDFLARE_API_TOKEN": os.environ.get("CLOUDFLARE_API_TOKEN"),
        "CLOUDFLARE_ACCOUNT_ID": os.environ.get("CLOUDFLARE_ACCOUNT_ID"),
    }

    secrets_path = Path("/opt/engagic/.llm_secrets")
    if secrets_path.exists():
        for line in secrets_path.read_text().splitlines():
            for key in cf_vars:
                if not cf_vars[key] and line.startswith(f"{key}="):
                    cf_vars[key] = line.split("=", 1)[1].strip()

    if not cf_vars["CLOUDFLARE_API_TOKEN"]:
        logger.error("CLOUDFLARE_API_TOKEN not found in environment or .llm_secrets")
        print("Error: set CLOUDFLARE_API_TOKEN or add it to .llm_secrets")
        return
    if not cf_vars["CLOUDFLARE_ACCOUNT_ID"]:
        logger.error("CLOUDFLARE_ACCOUNT_ID not found -- wrangler will fail on /memberships lookup")
        print("Error: set CLOUDFLARE_ACCOUNT_ID in .llm_secrets")
        return

    env = {**os.environ, **{k: v for k, v in cf_vars.items() if v}}

    size_mb = PMTILES_PATH.stat().st_size / (1024 * 1024)
    logger.info("uploading to R2", file=str(PMTILES_PATH), size_mb=f"{size_mb:.1f}")
    print(f"\nUploading {size_mb:.1f} MB to R2 bucket engagic-tiles...")

    # --remote is REQUIRED on wrangler v4+; without it, the object goes into
    # local simulated R2 state and never reaches production.
    result = subprocess.run(
        [
            "npx", "wrangler", "r2", "object", "put",
            "engagic-tiles/cities.pmtiles",
            f"--file={PMTILES_PATH}",
            "--content-type=application/octet-stream",
            "--remote",
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
