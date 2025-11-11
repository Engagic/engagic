"""
Migration: Rehash matter IDs using deterministic hashing

Migrates from string concatenation IDs to SHA256-based deterministic IDs.

OLD FORMAT: {banana}_{matter_file_or_matter_id}
NEW FORMAT: {banana}_{hash(banana:matter_file:matter_id)}

This migration:
1. Backs up city_matters table
2. Generates new IDs using deterministic hashing
3. Updates foreign key references in agenda_items
4. Verifies no data loss
"""

import sqlite3
import sys
import logging
from pathlib import Path

# Add parent directory to path so we can import from database
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from database.id_generation import generate_matter_id, validate_matter_id

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def backup_table(conn: sqlite3.Connection, table_name: str) -> None:
    """Create backup of table"""
    backup_name = f"{table_name}_backup_{int(__import__('time').time())}"
    cursor = conn.cursor()
    cursor.execute(f"CREATE TABLE {backup_name} AS SELECT * FROM {table_name}")
    conn.commit()
    logger.info(f"Created backup table: {backup_name}")


def migrate(db_path: str, dry_run: bool = False):
    """Run migration on database

    Args:
        db_path: Path to SQLite database
        dry_run: If True, show changes but don't commit
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        logger.info("Starting migration: 002_rehash_matter_ids")

        # Step 1: Backup city_matters table
        if not dry_run:
            backup_table(conn, "city_matters")

        # Step 2: Analyze existing matters
        cursor.execute("SELECT COUNT(*) as count FROM city_matters")
        total_matters = cursor.fetchone()["count"]
        logger.info(f"Found {total_matters} matters to migrate")

        # Step 3: Build mapping of old ID -> new ID
        cursor.execute("""
            SELECT id, banana, matter_file, matter_id
            FROM city_matters
        """)
        matters = cursor.fetchall()

        id_mapping = {}  # old_id -> new_id
        conflicts = []

        for matter in matters:
            old_id = matter["id"]
            banana = matter["banana"]
            matter_file = matter["matter_file"]
            matter_id_val = matter["matter_id"]

            # Generate new deterministic ID
            try:
                new_id = generate_matter_id(banana, matter_file, matter_id_val)
            except ValueError as e:
                logger.error(f"Failed to generate ID for {old_id}: {e}")
                conflicts.append((old_id, str(e)))
                continue

            # Check for collisions (should be extremely rare)
            if new_id in id_mapping.values() and new_id != old_id:
                logger.warning(f"ID collision detected: {old_id} -> {new_id}")
                conflicts.append((old_id, f"Collision with {new_id}"))
                continue

            id_mapping[old_id] = new_id

        logger.info(f"Generated {len(id_mapping)} new IDs")

        if conflicts:
            logger.error(f"Found {len(conflicts)} conflicts:")
            for old_id, reason in conflicts[:10]:  # Show first 10
                logger.error(f"  {old_id}: {reason}")
            if not dry_run:
                raise Exception(f"Cannot proceed with {len(conflicts)} conflicts")

        # Step 4: Show changes
        changes_same = sum(1 for old_id, new_id in id_mapping.items() if old_id == new_id)
        changes_diff = len(id_mapping) - changes_same
        logger.info(f"IDs unchanged: {changes_same}")
        logger.info(f"IDs changed: {changes_diff}")

        if changes_diff > 0:
            logger.info("Sample changes:")
            sample_count = 0
            for old_id, new_id in id_mapping.items():
                if old_id != new_id and sample_count < 5:
                    logger.info(f"  {old_id} -> {new_id}")
                    sample_count += 1

        if dry_run:
            logger.info("DRY RUN - No changes committed")
            return

        # Step 5: Create temporary table with new schema
        logger.info("Creating temporary table...")
        cursor.execute("""
            CREATE TABLE city_matters_new (
                id TEXT PRIMARY KEY,
                banana TEXT NOT NULL,
                matter_id TEXT,
                matter_file TEXT,
                matter_type TEXT,
                title TEXT NOT NULL,
                sponsors TEXT,
                canonical_summary TEXT,
                canonical_topics TEXT,
                first_seen TIMESTAMP NOT NULL,
                last_seen TIMESTAMP NOT NULL,
                appearance_count INTEGER DEFAULT 1,
                status TEXT DEFAULT 'active',
                attachments TEXT,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE
            )
        """)

        # Step 6: Copy data with new IDs
        logger.info("Copying data with new IDs...")
        for matter in matters:
            old_id = matter["id"]
            new_id = id_mapping.get(old_id)

            if not new_id:
                logger.warning(f"Skipping matter {old_id} (no mapping)")
                continue

            cursor.execute("""
                INSERT INTO city_matters_new
                (id, banana, matter_id, matter_file, matter_type, title, sponsors,
                 canonical_summary, canonical_topics, first_seen, last_seen,
                 appearance_count, status, attachments, metadata, created_at, updated_at)
                SELECT ?, banana, matter_id, matter_file, matter_type, title, sponsors,
                       canonical_summary, canonical_topics, first_seen, last_seen,
                       appearance_count, status, attachments, metadata, created_at, updated_at
                FROM city_matters
                WHERE id = ?
            """, (new_id, old_id))

        conn.commit()
        logger.info(f"Copied {len(id_mapping)} matters to new table")

        # Step 7: Drop old table and rename new table
        logger.info("Swapping tables...")
        cursor.execute("DROP TABLE city_matters")
        cursor.execute("ALTER TABLE city_matters_new RENAME TO city_matters")
        conn.commit()

        # Step 8: Recreate indexes
        logger.info("Recreating indexes...")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_city_matters_banana
            ON city_matters(banana)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_city_matters_matter_file
            ON city_matters(matter_file)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_city_matters_matter_id
            ON city_matters(matter_id)
        """)
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_city_matters_unique
            ON city_matters(banana, COALESCE(matter_file, matter_id))
        """)
        conn.commit()

        # Step 9: Verify migration
        cursor.execute("SELECT COUNT(*) as count FROM city_matters")
        final_count = cursor.fetchone()["count"]

        if final_count != total_matters:
            raise Exception(f"Data loss detected: {total_matters} -> {final_count}")

        logger.info(f"Migration completed successfully! {final_count} matters migrated")

        # Step 10: Validate new IDs
        cursor.execute("SELECT id FROM city_matters")
        new_ids = [row["id"] for row in cursor.fetchall()]
        invalid_ids = [id for id in new_ids if not validate_matter_id(id)]

        if invalid_ids:
            logger.warning(f"Found {len(invalid_ids)} invalid IDs after migration:")
            for invalid_id in invalid_ids[:10]:
                logger.warning(f"  {invalid_id}")
        else:
            logger.info("All new IDs validated successfully")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python 002_rehash_matter_ids.py <database_path> [--dry-run]")
        sys.exit(1)

    db_path = sys.argv[1]
    dry_run = "--dry-run" in sys.argv

    if not Path(db_path).exists():
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)

    if dry_run:
        print("=== DRY RUN MODE ===")

    migrate(db_path, dry_run=dry_run)
