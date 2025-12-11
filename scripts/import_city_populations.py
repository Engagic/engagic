#!/usr/bin/env python3
"""Import population data from cities.json into the cities table.

Matches cities by name+state, with special handling for NYC consolidation.

Usage:
    python scripts/import_city_populations.py --dry-run   # Preview changes
    python scripts/import_city_populations.py --import    # Apply changes
    python scripts/import_city_populations.py --status    # Show coverage
"""

import argparse
import asyncio
import json
import re
from pathlib import Path

import asyncpg

from config import config, get_logger

logger = get_logger(__name__).bind(component="population_import")

# Source data
CITIES_JSON = Path("/root/cities.json")

# NYC consolidated population (Census 2020 + estimates)
# The JSON has boroughs split incorrectly, so we use the official figure
NYC_POPULATION = 8_336_817

# Cities that should be consolidated into NYC
NYC_BOROUGHS = {"Staten Island", "Astoria"}  # Astoria is part of Queens

# Manual overrides for cities missing from source JSON (Census 2020 data)
MANUAL_POPULATIONS = {
    ("fremont", "CA"): 230_504,
    ("boise", "ID"): 235_684,
    ("chicago", "IL"): 2_746_388,
    ("staten island", "NY"): 495_747,  # For completeness, though it's a borough
}


def normalize_name(name: str) -> str:
    """Normalize city name for matching."""
    name = name.strip().lower()
    # Remove common suffixes
    name = re.sub(r"\s+(city|town|village|township)$", "", name)
    # Normalize spacing
    name = re.sub(r"\s+", " ", name)
    return name


async def load_source_data() -> dict[tuple[str, str], int]:
    """Load cities.json and build name+state -> population mapping."""
    with open(CITIES_JSON) as f:
        data = json.load(f)

    populations = {}
    for city in data:
        name = city["city_name"]
        state = city["state"]
        pop = city.get("population", 0)

        # Skip NYC boroughs - they'll be consolidated
        if state == "NY" and name in NYC_BOROUGHS:
            logger.debug("skipping NYC borough", name=name)
            continue

        key = (normalize_name(name), state)
        populations[key] = pop

    # Override NYC with consolidated population
    populations[("new york", "NY")] = NYC_POPULATION

    # Apply manual overrides for missing cities
    for key, pop in MANUAL_POPULATIONS.items():
        populations[key] = pop

    logger.info("loaded source data", cities=len(populations))
    return populations


async def get_db_cities(conn) -> list[dict]:
    """Get all cities from database."""
    rows = await conn.fetch("""
        SELECT banana, name, state, population
        FROM cities
        ORDER BY state, name
    """)
    return [dict(row) for row in rows]


async def match_populations(conn, populations: dict, dry_run: bool = True) -> dict:
    """Match cities and update populations."""
    db_cities = await get_db_cities(conn)

    matched = 0
    unmatched = []
    updates = []

    for city in db_cities:
        banana = city["banana"]
        name = city["name"]
        state = city["state"]
        current_pop = city["population"]

        # Skip NYC boroughs in DB - they should get NYC consolidated pop
        # Actually, Staten Island etc. in DB are separate entries
        # We'll match them individually but NYC itself gets the big number

        key = (normalize_name(name), state)
        pop = populations.get(key)

        if pop is not None:
            if current_pop != pop:
                updates.append((banana, name, state, pop, current_pop))
            matched += 1
        else:
            unmatched.append({"banana": banana, "name": name, "state": state})

    logger.info("matching complete", matched=matched, unmatched=len(unmatched))

    if updates:
        print(f"\nUpdates to apply: {len(updates)}")
        for banana, name, state, new_pop, old_pop in updates[:20]:
            old_str = f"{old_pop:,}" if old_pop else "NULL"
            print(f"  {name}, {state}: {old_str} -> {new_pop:,}")
        if len(updates) > 20:
            print(f"  ... and {len(updates) - 20} more")

    if unmatched:
        print(f"\nUnmatched cities: {len(unmatched)}")
        for city in unmatched[:15]:
            print(f"  {city['banana']}: {city['name']}, {city['state']}")
        if len(unmatched) > 15:
            print(f"  ... and {len(unmatched) - 15} more")

    if not dry_run and updates:
        print("\nApplying updates...")
        for banana, name, state, new_pop, _ in updates:
            await conn.execute(
                "UPDATE cities SET population = $1 WHERE banana = $2",
                new_pop, banana
            )
        logger.info("updates applied", count=len(updates))

    return {
        "matched": matched,
        "unmatched": len(unmatched),
        "updated": len(updates) if not dry_run else 0,
    }


async def report_status(conn) -> None:
    """Report population coverage status."""
    total = await conn.fetchval("SELECT COUNT(*) FROM cities")
    with_pop = await conn.fetchval("SELECT COUNT(*) FROM cities WHERE population IS NOT NULL")
    total_pop = await conn.fetchval("SELECT COALESCE(SUM(population), 0) FROM cities")

    print("\nPopulation Coverage:")
    print(f"  Total cities: {total}")
    print(f"  With population: {with_pop} ({100*with_pop/total:.1f}%)")
    print(f"  Total population: {total_pop:,}")

    # Top 10 by population
    print("\nTop 10 Cities by Population:")
    rows = await conn.fetch("""
        SELECT name, state, population
        FROM cities
        WHERE population IS NOT NULL
        ORDER BY population DESC
        LIMIT 10
    """)
    for row in rows:
        print(f"  {row['name']}, {row['state']}: {row['population']:,}")

    # Cities with data
    print("\nPopulation with Meeting Data:")
    pop_with_data = await conn.fetchval("""
        SELECT COALESCE(SUM(c.population), 0)
        FROM cities c
        WHERE c.population IS NOT NULL
          AND EXISTS (SELECT 1 FROM meetings m WHERE m.banana = c.banana)
    """)
    print(f"  {pop_with_data:,} people in cities with meeting data")


async def main():
    parser = argparse.ArgumentParser(description="Import city populations")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes only")
    parser.add_argument("--import", dest="do_import", action="store_true", help="Apply changes")
    parser.add_argument("--status", action="store_true", help="Report status")
    args = parser.parse_args()

    dsn = config.get_postgres_dsn()
    conn = await asyncpg.connect(dsn)

    try:
        if args.dry_run or args.do_import:
            populations = await load_source_data()
            await match_populations(conn, populations, dry_run=not args.do_import)

        if args.status or args.do_import:
            await report_status(conn)

        if not any([args.dry_run, args.do_import, args.status]):
            parser.print_help()

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
