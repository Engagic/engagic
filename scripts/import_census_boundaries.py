#!/usr/bin/env python3
"""Import Census TIGER/Line Place boundaries into cities.geom

Downloads Census PLACE shapefiles and matches them to our cities table.

Usage:
    python scripts/import_census_boundaries.py --download   # Download shapefiles
    python scripts/import_census_boundaries.py --import     # Import to staging table
    python scripts/import_census_boundaries.py --match      # Match to cities
    python scripts/import_census_boundaries.py --all        # Full pipeline

Requirements:
    - PostGIS extension enabled
    - ogr2ogr (gdal-bin package)
    - wget
"""

import argparse
import asyncio
import os
import subprocess
import re
from pathlib import Path

import asyncpg

from config import config, get_logger

logger = get_logger(__name__).bind(component="census_import")

# Census TIGER/Line FTP base URL
TIGER_BASE_URL = "https://www2.census.gov/geo/tiger/TIGER2023/PLACE"

# State FIPS codes
STATE_FIPS = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06",
    "CO": "08", "CT": "09", "DE": "10", "FL": "12", "GA": "13",
    "HI": "15", "ID": "16", "IL": "17", "IN": "18", "IA": "19",
    "KS": "20", "KY": "21", "LA": "22", "ME": "23", "MD": "24",
    "MA": "25", "MI": "26", "MN": "27", "MS": "28", "MO": "29",
    "MT": "30", "NE": "31", "NV": "32", "NH": "33", "NJ": "34",
    "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39",
    "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45",
    "SD": "46", "TN": "47", "TX": "48", "UT": "49", "VT": "50",
    "VA": "51", "WA": "53", "WV": "54", "WI": "55", "WY": "56",
    "DC": "11", "PR": "72",
}

# Reverse lookup
FIPS_TO_STATE = {v: k for k, v in STATE_FIPS.items()}

# Data directory
DATA_DIR = Path("/opt/engagic/data/census")


def get_states_we_track() -> set[str]:
    """Get unique states from our cities table."""
    # This will be populated from the database
    return set(STATE_FIPS.keys())


async def download_shapefiles(states: set[str] | None = None) -> None:
    """Download Census PLACE shapefiles for specified states."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if states is None:
        # Get states we actually track from the database
        dsn = config.get_postgres_dsn()
        conn = await asyncpg.connect(dsn)
        try:
            rows = await conn.fetch("SELECT DISTINCT state FROM cities")
            states = {row["state"] for row in rows}
        finally:
            await conn.close()

    logger.info("downloading shapefiles", states=sorted(states))

    for state in sorted(states):
        fips = STATE_FIPS.get(state)
        if not fips:
            logger.warning("unknown state FIPS", state=state)
            continue

        filename = f"tl_2023_{fips}_place.zip"
        url = f"{TIGER_BASE_URL}/{filename}"
        dest = DATA_DIR / filename

        if dest.exists():
            logger.debug("shapefile exists, skipping", state=state)
            continue

        logger.info("downloading", state=state, url=url)
        result = subprocess.run(
            ["wget", "-q", "-O", str(dest), url],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.error("download failed", state=state, stderr=result.stderr)
            dest.unlink(missing_ok=True)

    logger.info("download complete")


async def import_to_staging() -> None:
    """Import shapefiles to census_places staging table using ogr2ogr."""
    dsn = config.get_postgres_dsn()

    # Build ogr2ogr connection string
    # Parse DSN to get components
    conn = await asyncpg.connect(dsn)
    try:
        # Drop and recreate staging table
        await conn.execute("DROP TABLE IF EXISTS census_places CASCADE")
        logger.info("dropped existing census_places table")
    finally:
        await conn.close()

    # ogr2ogr connection string format
    pg_conn = f"PG:{dsn}"

    # Find all downloaded shapefiles
    shapefiles = sorted(DATA_DIR.glob("tl_2023_*_place.zip"))
    if not shapefiles:
        logger.error("no shapefiles found", directory=str(DATA_DIR))
        return

    logger.info("importing shapefiles", count=len(shapefiles))

    for i, shapefile in enumerate(shapefiles):
        # Extract state FIPS from filename
        match = re.search(r"tl_2023_(\d{2})_place\.zip", shapefile.name)
        if not match:
            continue

        state_fips = match.group(1)
        state = FIPS_TO_STATE.get(state_fips, "??")

        # ogr2ogr reads directly from zip
        vsi_path = f"/vsizip/{shapefile}"

        # First shapefile creates table, subsequent ones append
        mode = "-overwrite" if i == 0 else "-append"

        logger.info("importing", state=state, shapefile=shapefile.name)

        result = subprocess.run(
            [
                "ogr2ogr",
                "-f", "PostgreSQL",
                pg_conn,
                vsi_path,
                "-nln", "census_places",
                "-nlt", "MULTIPOLYGON",
                "-t_srs", "EPSG:4326",
                mode,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.error("ogr2ogr failed", state=state, stderr=result.stderr)

    # Create index on staging table
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_census_places_name
            ON census_places (UPPER(name))
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_census_places_statefp
            ON census_places (statefp)
        """)

        # Get count
        count = await conn.fetchval("SELECT COUNT(*) FROM census_places")
        logger.info("import complete", total_places=count)
    finally:
        await conn.close()


def normalize_city_name(name: str) -> str:
    """Normalize city name for matching.

    Handles common variations:
    - Fort/Ft.
    - Saint/St.
    - Township/Twp
    - City suffix
    """
    name = name.strip().upper()

    # Expand abbreviations
    name = re.sub(r"\bFT\.?\b", "FORT", name)
    name = re.sub(r"\bST\.?\b", "SAINT", name)
    name = re.sub(r"\bMT\.?\b", "MOUNT", name)
    name = re.sub(r"\bTWP\.?\b", "TOWNSHIP", name)

    # Remove common suffixes for matching
    name = re.sub(r"\s+(CITY|TOWN|VILLAGE|CDP)$", "", name)

    return name


async def match_cities() -> None:
    """Match our cities to Census places and populate geom column."""
    dsn = config.get_postgres_dsn()
    conn = await asyncpg.connect(dsn)

    try:
        # Get our cities without geometry
        cities = await conn.fetch("""
            SELECT banana, name, state
            FROM cities
            WHERE geom IS NULL
            ORDER BY state, name
        """)

        logger.info("matching cities", total=len(cities))

        matched = 0
        unmatched = []

        for city in cities:
            banana = city["banana"]
            name = city["name"]
            state = city["state"]
            state_fips = STATE_FIPS.get(state)

            if not state_fips:
                logger.warning("unknown state", banana=banana, state=state)
                unmatched.append({"banana": banana, "reason": "unknown_state"})
                continue

            # Try exact match first
            place = await conn.fetchrow("""
                SELECT geom
                FROM census_places
                WHERE UPPER(name) = $1 AND statefp = $2
            """, name.upper(), state_fips)

            # Try normalized match if exact fails
            if not place:
                normalized = normalize_city_name(name)
                place = await conn.fetchrow("""
                    SELECT geom
                    FROM census_places
                    WHERE UPPER(name) LIKE $1 AND statefp = $2
                """, f"%{normalized}%", state_fips)

            # Try with city suffix
            if not place:
                place = await conn.fetchrow("""
                    SELECT geom
                    FROM census_places
                    WHERE (UPPER(name) = $1 OR UPPER(name) = $2)
                      AND statefp = $3
                """, f"{name.upper()} CITY", f"{name.upper()} TOWN", state_fips)

            if place:
                await conn.execute("""
                    UPDATE cities SET geom = $1 WHERE banana = $2
                """, place["geom"], banana)
                matched += 1
                logger.debug("matched", banana=banana, name=name)
            else:
                unmatched.append({"banana": banana, "name": name, "state": state})
                logger.warning("no match", banana=banana, name=name, state=state)

        logger.info("matching complete", matched=matched, unmatched=len(unmatched))

        # Report unmatched for manual review
        if unmatched:
            logger.info("unmatched cities require manual review:")
            for city in unmatched[:20]:  # First 20
                print(f"  {city.get('banana', '?')}: {city.get('name', '?')}, {city.get('state', '?')}")
            if len(unmatched) > 20:
                print(f"  ... and {len(unmatched) - 20} more")

    finally:
        await conn.close()


async def report_status() -> None:
    """Report geometry coverage status."""
    dsn = config.get_postgres_dsn()
    conn = await asyncpg.connect(dsn)

    try:
        total = await conn.fetchval("SELECT COUNT(*) FROM cities")
        with_geom = await conn.fetchval("SELECT COUNT(*) FROM cities WHERE geom IS NOT NULL")
        without_geom = await conn.fetchval("SELECT COUNT(*) FROM cities WHERE geom IS NULL")

        print(f"\nGeometry Coverage:")
        print(f"  Total cities: {total}")
        print(f"  With geometry: {with_geom} ({100*with_geom/total:.1f}%)")
        print(f"  Without geometry: {without_geom}")

        # By state
        print(f"\nBy State (top 10 missing):")
        rows = await conn.fetch("""
            SELECT state, COUNT(*) as total,
                   COUNT(*) FILTER (WHERE geom IS NOT NULL) as with_geom
            FROM cities
            GROUP BY state
            HAVING COUNT(*) FILTER (WHERE geom IS NULL) > 0
            ORDER BY COUNT(*) FILTER (WHERE geom IS NULL) DESC
            LIMIT 10
        """)
        for row in rows:
            missing = row["total"] - row["with_geom"]
            print(f"  {row['state']}: {missing} missing of {row['total']}")

    finally:
        await conn.close()


async def main():
    parser = argparse.ArgumentParser(description="Import Census TIGER boundaries")
    parser.add_argument("--download", action="store_true", help="Download shapefiles")
    parser.add_argument("--import", dest="import_", action="store_true", help="Import to staging")
    parser.add_argument("--match", action="store_true", help="Match to cities")
    parser.add_argument("--status", action="store_true", help="Report status")
    parser.add_argument("--all", action="store_true", help="Full pipeline")
    args = parser.parse_args()

    if args.all or args.download:
        await download_shapefiles()

    if args.all or args.import_:
        await import_to_staging()

    if args.all or args.match:
        await match_cities()

    if args.status or args.all:
        await report_status()

    if not any([args.download, args.import_, args.match, args.status, args.all]):
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
