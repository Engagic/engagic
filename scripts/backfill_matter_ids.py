#!/usr/bin/env python3
"""
Backfill matter_ids for orphan items that have matter_file but no matter_id.

Creates city_matters entries and links items to them.

Usage:
    uv run scripts/backfill_matter_ids.py --dry-run  # Preview changes
    uv run scripts/backfill_matter_ids.py            # Apply changes
"""

import asyncio
import argparse
from datetime import datetime
from collections import defaultdict

from config import get_logger
from database.db_postgres import Database
from database.id_generation import generate_matter_id

logger = get_logger(__name__)


async def find_orphan_items(db: Database) -> list[dict]:
    """Find items with matter_file but no matter_id."""
    async with db.pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                i.id as item_id,
                i.meeting_id,
                i.matter_file,
                i.matter_type,
                i.title,
                i.attachments,
                m.banana,
                m.date as meeting_date
            FROM items i
            JOIN meetings m ON i.meeting_id = m.id
            WHERE i.matter_file IS NOT NULL
              AND i.matter_id IS NULL
            ORDER BY m.banana, i.matter_file
        """)
        return [dict(row) for row in rows]


async def backfill_matters(db: Database, dry_run: bool = True):
    """Backfill matter_ids for orphan items."""
    orphans = await find_orphan_items(db)

    if not orphans:
        logger.info("no orphan items found")
        return

    logger.info("found orphan items", count=len(orphans), dry_run=dry_run)

    # Group by banana + matter_file to find unique matters
    matters_to_create: dict[str, dict] = {}  # matter_id -> matter data
    items_to_update: list[tuple[str, str]] = []  # (item_id, matter_id)

    for orphan in orphans:
        banana = orphan['banana']
        matter_file = orphan['matter_file']

        # Generate deterministic matter_id
        matter_id = generate_matter_id(banana, matter_file=matter_file)

        if matter_id is None:
            logger.warning("could not generate matter_id",
                         item_id=orphan['item_id'],
                         matter_file=matter_file)
            continue

        items_to_update.append((orphan['item_id'], matter_id))

        # Track unique matters to create
        if matter_id not in matters_to_create:
            matters_to_create[matter_id] = {
                'id': matter_id,
                'banana': banana,
                'matter_file': matter_file,
                'matter_type': orphan['matter_type'],
                'title': orphan['title'],
                'attachments': orphan['attachments'],
                'first_seen': orphan['meeting_date'],
                'last_seen': orphan['meeting_date'],
            }
        else:
            # Update last_seen if this item is newer
            existing = matters_to_create[matter_id]
            if orphan['meeting_date'] and existing['last_seen']:
                if orphan['meeting_date'] > existing['last_seen']:
                    existing['last_seen'] = orphan['meeting_date']
                if orphan['meeting_date'] < existing['first_seen']:
                    existing['first_seen'] = orphan['meeting_date']

    # Summary by city
    by_city = defaultdict(int)
    for orphan in orphans:
        by_city[orphan['banana']] += 1

    logger.info("backfill summary",
                unique_matters=len(matters_to_create),
                items_to_update=len(items_to_update),
                cities_affected=len(by_city))

    for city, count in sorted(by_city.items(), key=lambda x: -x[1])[:10]:
        logger.info("city orphans", city=city, count=count)

    if dry_run:
        logger.info("DRY RUN - no changes made")
        logger.info("sample matters to create:")
        for matter_id, data in list(matters_to_create.items())[:5]:
            logger.info("  matter",
                       matter_id=matter_id,
                       matter_file=data['matter_file'],
                       banana=data['banana'],
                       matter_type=data['matter_type'])
        return

    # Apply changes
    logger.info("applying changes...")

    matters_created = 0
    matters_existing = 0
    items_updated = 0

    async with db.pool.acquire() as conn:
        # Check which matters already exist
        existing_matter_ids = set()
        if matters_to_create:
            rows = await conn.fetch("""
                SELECT id FROM city_matters WHERE id = ANY($1::text[])
            """, list(matters_to_create.keys()))
            existing_matter_ids = {row['id'] for row in rows}

        async with conn.transaction():
            # Create missing matters
            for matter_id, data in matters_to_create.items():
                if matter_id in existing_matter_ids:
                    matters_existing += 1
                    continue

                await conn.execute("""
                    INSERT INTO city_matters (
                        id, banana, matter_file, matter_type, title,
                        attachments, first_seen, last_seen, appearance_count
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 1)
                    ON CONFLICT (id) DO NOTHING
                """,
                    data['id'],
                    data['banana'],
                    data['matter_file'],
                    data['matter_type'],
                    data['title'],
                    data['attachments'],
                    data['first_seen'],
                    data['last_seen'],
                )
                matters_created += 1

            # Update items with matter_id
            for item_id, matter_id in items_to_update:
                await conn.execute("""
                    UPDATE items SET matter_id = $1 WHERE id = $2
                """, matter_id, item_id)
                items_updated += 1

    logger.info("backfill complete",
                matters_created=matters_created,
                matters_existing=matters_existing,
                items_updated=items_updated)


async def main():
    parser = argparse.ArgumentParser(description="Backfill matter_ids for orphan items")
    parser.add_argument("--dry-run", action="store_true",
                       help="Preview changes without applying them")
    args = parser.parse_args()

    db = await Database.create()

    try:
        await backfill_matters(db, dry_run=args.dry_run)
    finally:
        await db.pool.close()


if __name__ == "__main__":
    asyncio.run(main())
