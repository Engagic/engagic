#!/usr/bin/env python3
"""Backfill missing matter titles from agenda items

Data migration script to fix matters that have NULL values for all identifier
fields (matter_file, matter_id, title). These matters cause ValidationError
when loaded, breaking city pages.

Solution: Populate title from the corresponding agenda item that references
the matter.
"""

import argparse
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.db_postgres import Database
from config import config
from config import get_logger

logger = get_logger(__name__).bind(component="backfill_matter_titles")


async def find_invalid_matters(db: Database) -> list:
    """Find matters missing all identifier fields"""
    async with db.pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, banana, matter_file, matter_id, title
            FROM city_matters
            WHERE matter_file IS NULL
              AND matter_id IS NULL
              AND (title IS NULL OR title = '')
        """)
    return [dict(row) for row in rows]


async def backfill_titles(db: Database, dry_run: bool = True) -> dict:
    """Backfill missing titles from agenda items

    Args:
        db: Database instance
        dry_run: If True, don't actually update, just report what would change

    Returns:
        Dict with counts: found, updated, no_item_found
    """
    invalid_matters = await find_invalid_matters(db)

    if not invalid_matters:
        return {"found": 0, "updated": 0, "no_item_found": 0}

    updated = 0
    no_item_found = 0

    async with db.pool.acquire() as conn:
        for matter in invalid_matters:
            matter_id = matter["id"]

            # Find corresponding item to get title
            item_row = await conn.fetchrow("""
                SELECT title FROM items
                WHERE matter_id = $1
                LIMIT 1
            """, matter_id)

            if item_row and item_row["title"]:
                title = item_row["title"]

                if dry_run:
                    logger.info(
                        "would update matter",
                        matter_id=matter_id,
                        banana=matter["banana"],
                        new_title=title[:50] + "..." if len(title) > 50 else title
                    )
                else:
                    await conn.execute("""
                        UPDATE city_matters
                        SET title = $2, updated_at = CURRENT_TIMESTAMP
                        WHERE id = $1
                    """, matter_id, title)
                    logger.info(
                        "updated matter",
                        matter_id=matter_id,
                        banana=matter["banana"],
                        new_title=title[:50] + "..." if len(title) > 50 else title
                    )
                updated += 1
            else:
                logger.warning(
                    "no item found for matter",
                    matter_id=matter_id,
                    banana=matter["banana"]
                )
                no_item_found += 1

    return {
        "found": len(invalid_matters),
        "updated": updated,
        "no_item_found": no_item_found
    }


def main():
    parser = argparse.ArgumentParser(
        description="Backfill missing matter titles from agenda items"
    )
    parser.add_argument(
        "--dsn",
        help="PostgreSQL DSN (defaults to config)",
        default=None,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without making changes (default)",
        default=True,
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually perform the updates",
    )
    parser.add_argument(
        "--stats-only",
        action="store_true",
        help="Only show statistics, don't preview individual updates",
    )

    args = parser.parse_args()

    dry_run = not args.execute

    async def _run():
        db = await Database.create(args.dsn or config.get_postgres_dsn())
        try:
            if args.stats_only:
                invalid = await find_invalid_matters(db)
                print(f"\nFound {len(invalid)} matters with missing identifiers")

                # Group by city
                by_city = {}
                for m in invalid:
                    banana = m["banana"]
                    by_city[banana] = by_city.get(banana, 0) + 1

                if by_city:
                    print("\nBy city:")
                    for banana, count in sorted(by_city.items(), key=lambda x: -x[1]):
                        print(f"  {banana}: {count}")
                return

            # Perform backfill
            if dry_run:
                print("\n=== DRY RUN (no changes will be made) ===\n")
            else:
                print("\n=== EXECUTING UPDATES ===\n")

            result = await backfill_titles(db, dry_run=dry_run)

            print("\n=== Results ===")
            print(f"Invalid matters found: {result['found']}")
            print(f"{'Would update' if dry_run else 'Updated'}: {result['updated']}")
            print(f"No matching item found: {result['no_item_found']}")

            if dry_run and result['updated'] > 0:
                print("\nRun with --execute to apply these changes")

        finally:
            await db.close()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
