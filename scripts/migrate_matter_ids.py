#!/usr/bin/env python3
"""
Migration: Recalculate matter IDs using strict hierarchy

This migration:
1. Recalculates all matter IDs using the new logic (matter_file alone when present)
2. Merges duplicates (multiple old IDs that now map to the same new ID)
3. Updates all FK references
4. Cleans up orphaned records

Run with --dry-run first to see what would change.
"""

import asyncio
import sys
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from database.db_postgres import Database
from database.id_generation import generate_matter_id
from config import get_logger

logger = get_logger(__name__).bind(component="migrate_matter_ids")


@dataclass
class MatterRecord:
    id: str
    banana: str
    matter_file: Optional[str]
    matter_id: Optional[str]
    title: Optional[str]
    canonical_summary: Optional[str]
    created_at: any
    item_count: int


async def get_all_matters(db: Database) -> list[MatterRecord]:
    """Fetch all matters with item counts."""
    async with db.pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                cm.id,
                cm.banana,
                cm.matter_file,
                cm.matter_id,
                cm.title,
                cm.canonical_summary,
                cm.created_at,
                (SELECT COUNT(*) FROM items i WHERE i.matter_id = cm.id) as item_count
            FROM city_matters cm
            ORDER BY cm.banana, cm.matter_file, cm.created_at
        """)
        return [MatterRecord(**dict(row)) for row in rows]


def compute_new_id(matter: MatterRecord) -> Optional[str]:
    """Compute new ID using updated generation logic."""
    return generate_matter_id(
        banana=matter.banana,
        matter_file=matter.matter_file,
        matter_id=matter.matter_id,
        title=matter.title
    )


async def run_migration(db: Database, dry_run: bool = True):
    """Execute the migration."""

    logger.info("fetching all matters")
    matters = await get_all_matters(db)
    logger.info("found matters", count=len(matters))

    # Group by new ID
    new_id_groups: dict[str, list[MatterRecord]] = defaultdict(list)
    no_id_matters = []

    for matter in matters:
        new_id = compute_new_id(matter)
        if new_id is None:
            no_id_matters.append(matter)
        else:
            new_id_groups[new_id].append(matter)

    # Find matters that need ID changes
    id_changes = []  # (old_id, new_id, is_merge_source)
    merges = []  # (source_ids, target_id, target_record)
    unchanged = 0

    for new_id, group in new_id_groups.items():
        if len(group) == 1:
            matter = group[0]
            if matter.id != new_id:
                id_changes.append((matter.id, new_id, False))
            else:
                unchanged += 1
        else:
            # Multiple old IDs map to same new ID - need to merge
            # Pick canonical: prefer one with summary, then most items, then oldest
            group.sort(key=lambda m: (
                m.canonical_summary is None,  # has summary first
                -m.item_count,  # most items first
                m.created_at  # oldest first
            ))
            canonical = group[0]
            sources = group[1:]

            merges.append((
                [s.id for s in sources],
                new_id,
                canonical
            ))

            # The canonical record may need ID change
            if canonical.id != new_id:
                id_changes.append((canonical.id, new_id, False))

            # Source records will be deleted after reference update
            for source in sources:
                id_changes.append((source.id, new_id, True))  # merge source

    # Report
    print("\n" + "=" * 70)
    print("MATTER ID MIGRATION PLAN")
    print("=" * 70)
    print(f"\nTotal matters: {len(matters)}")
    print(f"Unchanged: {unchanged}")
    print(f"ID changes needed: {len([c for c in id_changes if not c[2]])}")
    print(f"Merges needed: {len(merges)} (affecting {sum(len(m[0]) for m in merges)} duplicate records)")
    print(f"Matters with no computable ID: {len(no_id_matters)}")

    if merges:
        print("\n--- MERGES ---")
        for source_ids, target_id, canonical in merges[:10]:
            print(f"\n  Merge {len(source_ids) + 1} records -> {target_id}")
            print(f"    Canonical: {canonical.id} (items={canonical.item_count}, has_summary={canonical.canonical_summary is not None})")
            for sid in source_ids:
                print(f"    Delete: {sid}")
        if len(merges) > 10:
            print(f"\n  ... and {len(merges) - 10} more merges")

    if no_id_matters:
        print("\n--- NO ID COMPUTABLE (will be orphaned) ---")
        for m in no_id_matters[:5]:
            print(f"  {m.id}: file={m.matter_file}, mid={m.matter_id}, title={m.title[:50] if m.title else None}...")
        if len(no_id_matters) > 5:
            print(f"  ... and {len(no_id_matters) - 5} more")

    if dry_run:
        print("\n[DRY RUN - no changes made]")
        print("Run with --execute to apply changes")
        return

    # Execute migration
    print("\n--- EXECUTING MIGRATION ---")

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            # Step 1: Create temp mapping table
            await conn.execute("""
                CREATE TEMP TABLE matter_id_map (
                    old_id TEXT PRIMARY KEY,
                    new_id TEXT NOT NULL,
                    is_merge_source BOOLEAN DEFAULT FALSE
                )
            """)

            # Step 2: Insert mappings
            for old_id, new_id, is_merge in id_changes:
                await conn.execute(
                    "INSERT INTO matter_id_map (old_id, new_id, is_merge_source) VALUES ($1, $2, $3)",
                    old_id, new_id, is_merge
                )

            logger.info("created mapping table", mappings=len(id_changes))

            # Step 3: Drop FK constraints temporarily
            # They're not deferrable, so we drop and recreate
            fk_constraints = [
                ("items", "items_matter_id_fkey", "matter_id", "city_matters(id)"),
                ("matter_appearances", "matter_appearances_matter_id_fkey", "matter_id", "city_matters(id)"),
                ("matter_topics", "matter_topics_matter_id_fkey", "matter_id", "city_matters(id)"),
                ("deliberations", "deliberations_matter_id_fkey", "matter_id", "city_matters(id)"),
                ("sponsorships", "sponsorships_matter_id_fkey", "matter_id", "city_matters(id)"),
                ("votes", "votes_matter_id_fkey", "matter_id", "city_matters(id)"),
            ]

            for table, constraint, _, _ in fk_constraints:
                await conn.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint}")
            logger.info("dropped FK constraints")

            # Step 4: Update city_matters IDs first (non-merge sources only)
            # This creates the target IDs that FKs will point to
            result = await conn.execute("""
                UPDATE city_matters cm
                SET id = m.new_id
                FROM matter_id_map m
                WHERE cm.id = m.old_id AND m.is_merge_source = FALSE
            """)
            updated = int(result.split()[-1])
            logger.info("updated matter IDs", count=updated)

            # Step 5: Handle junction tables for merge sources
            # Delete records from junction tables where merge would create duplicates
            junction_tables = [
                "matter_topics",  # (matter_id, topic) is unique
                "matter_appearances",  # (matter_id, meeting_id, item_id) likely unique
            ]

            for table in junction_tables:
                # Delete merge source records that would conflict
                result = await conn.execute(f"""
                    DELETE FROM {table}
                    WHERE matter_id IN (
                        SELECT old_id FROM matter_id_map WHERE is_merge_source = TRUE
                    )
                """)
                count = int(result.split()[-1])
                if count > 0:
                    logger.info("deleted merge source junction records", table=table, count=count)

            # Step 6: Update references in all FK tables
            # Now pointing to the new canonical IDs
            fk_tables = [
                ("items", "matter_id"),
                ("matter_appearances", "matter_id"),
                ("matter_topics", "matter_id"),
                ("deliberations", "matter_id"),
                ("sponsorships", "matter_id"),
                ("votes", "matter_id"),
            ]

            for table, column in fk_tables:
                result = await conn.execute(f"""
                    UPDATE {table} t
                    SET {column} = m.new_id
                    FROM matter_id_map m
                    WHERE t.{column} = m.old_id
                """)
                count = int(result.split()[-1])
                if count > 0:
                    logger.info("updated FK references", table=table, count=count)

            # Step 6: Delete merge source records (duplicates)
            result = await conn.execute("""
                DELETE FROM city_matters
                WHERE id IN (SELECT old_id FROM matter_id_map WHERE is_merge_source = TRUE)
            """)
            deleted = int(result.split()[-1])
            logger.info("deleted duplicate matters", count=deleted)

            # Step 7: Clean up orphaned matters (no items, no summary)
            result = await conn.execute("""
                DELETE FROM city_matters cm
                WHERE NOT EXISTS (SELECT 1 FROM items i WHERE i.matter_id = cm.id)
                AND cm.canonical_summary IS NULL
            """)
            orphans_deleted = int(result.split()[-1])
            logger.info("deleted orphaned matters", count=orphans_deleted)

            # Step 8: Recreate FK constraints
            for table, constraint, column, ref in fk_constraints:
                await conn.execute(f"""
                    ALTER TABLE {table}
                    ADD CONSTRAINT {constraint}
                    FOREIGN KEY ({column}) REFERENCES {ref}
                    ON DELETE SET NULL
                """)
            logger.info("recreated FK constraints")

    print("\nMigration complete:")
    print(f"  - Updated {updated} matter IDs")
    print(f"  - Deleted {deleted} duplicate matters")
    print(f"  - Deleted {orphans_deleted} orphaned matters")


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Migrate matter IDs to new format")
    parser.add_argument("--execute", action="store_true", help="Actually execute (default is dry-run)")
    args = parser.parse_args()

    db = await Database.create()

    try:
        await run_migration(db, dry_run=not args.execute)
    finally:
        await db.pool.close()


if __name__ == "__main__":
    asyncio.run(main())
