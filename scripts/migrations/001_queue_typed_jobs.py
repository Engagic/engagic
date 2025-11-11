"""
Migration: Add typed job support to queue table

Adds job_type and payload columns to enable type-safe job dispatching.
Migrates existing source_url-based jobs to typed format.

Schema changes:
- Add job_type TEXT (meeting | matter)
- Add payload TEXT (JSON)
- Keep source_url for backward compatibility (temporarily)
"""

import sqlite3
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate(db_path: str):
    """Run migration on database"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        logger.info("Starting migration: 001_queue_typed_jobs")

        # Step 1: Add new columns (nullable for now)
        logger.info("Adding job_type and payload columns...")
        cursor.execute("""
            ALTER TABLE queue
            ADD COLUMN job_type TEXT
        """)
        cursor.execute("""
            ALTER TABLE queue
            ADD COLUMN payload TEXT
        """)
        conn.commit()

        # Step 2: Migrate existing data
        logger.info("Migrating existing queue entries...")

        # Get all existing queue entries
        cursor.execute("SELECT id, source_url, meeting_id, processing_metadata FROM queue")
        rows = cursor.fetchall()

        migrated = 0
        for row in rows:
            queue_id = row["id"]
            source_url = row["source_url"]
            meeting_id = row["meeting_id"]
            processing_metadata = row["processing_metadata"]

            # Determine job type and build payload
            if source_url.startswith("matters://"):
                # Matter job
                job_type = "matter"
                matter_id = source_url.replace("matters://", "")

                # Extract item_ids from processing_metadata
                metadata = json.loads(processing_metadata) if processing_metadata else {}
                item_ids = metadata.get("item_ids", [])

                payload = {
                    "matter_id": matter_id,
                    "meeting_id": meeting_id,
                    "item_ids": item_ids
                }
            else:
                # Meeting job
                job_type = "meeting"
                payload = {
                    "meeting_id": meeting_id,
                    "source_url": source_url
                }

            # Update row with typed data
            cursor.execute("""
                UPDATE queue
                SET job_type = ?, payload = ?
                WHERE id = ?
            """, (job_type, json.dumps(payload), queue_id))

            migrated += 1

        conn.commit()
        logger.info(f"Migrated {migrated} queue entries")

        # Step 3: Verify migration
        cursor.execute("SELECT COUNT(*) as count FROM queue WHERE job_type IS NULL OR payload IS NULL")
        unmigrated = cursor.fetchone()["count"]

        if unmigrated > 0:
            raise Exception(f"Migration incomplete: {unmigrated} rows still have NULL job_type or payload")

        logger.info("Migration verification passed")

        # Step 4: Add NOT NULL constraints (SQLite doesn't support ALTER COLUMN, so we note this)
        logger.info("Note: SQLite doesn't support ALTER COLUMN to add NOT NULL constraints")
        logger.info("New inserts must include job_type and payload (enforced in application code)")

        logger.info("Migration completed successfully!")

        # Print summary
        cursor.execute("SELECT job_type, COUNT(*) as count FROM queue GROUP BY job_type")
        summary = cursor.fetchall()
        logger.info("Queue job type distribution:")
        for row in summary:
            logger.info(f"  {row['job_type']}: {row['count']}")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def rollback(db_path: str):
    """Rollback migration (drop added columns)"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        logger.info("Rolling back migration: 001_queue_typed_jobs")

        # SQLite doesn't support DROP COLUMN directly
        # Need to recreate table without the columns
        logger.info("Note: SQLite rollback requires table recreation")
        logger.info("This is a destructive operation - backup recommended")

        # For now, just set the columns to NULL
        cursor.execute("UPDATE queue SET job_type = NULL, payload = NULL")
        conn.commit()

        logger.info("Rollback completed (set job_type and payload to NULL)")
        logger.info("To fully remove columns, recreate the table")

    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python 001_queue_typed_jobs.py <database_path> [rollback]")
        sys.exit(1)

    db_path = sys.argv[1]
    is_rollback = len(sys.argv) > 2 and sys.argv[2] == "rollback"

    if not Path(db_path).exists():
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)

    if is_rollback:
        rollback(db_path)
    else:
        migrate(db_path)
