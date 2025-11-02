#!/usr/bin/env python3
"""
Database migration: queue.packet_url → queue.source_url

Semantic clarification:
- source_url can be agenda_url, packet_url, OR items:// synthetic URL
- Reflects agenda-first, item-level architecture
- Priority: agenda_url > packet_url > items://

Migration logic:
1. Rename packet_url column to source_url in queue table
2. Update UNIQUE constraint and indices
"""

import sqlite3
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = Path("/root/engagic/data/engagic.db")


def migrate():
    """Rename packet_url to source_url in queue table"""

    if not DB_PATH.exists():
        logger.error(f"Database not found: {DB_PATH}")
        return False

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Step 1: Check if already migrated
        cursor.execute("PRAGMA table_info(queue)")
        columns = {row[1]: row for row in cursor.fetchall()}

        if 'source_url' in columns:
            logger.info("Migration already applied: source_url column exists")
            return True

        if 'packet_url' not in columns:
            logger.error("ERROR: packet_url column not found - database state unknown")
            return False

        logger.info("Starting migration: packet_url → source_url in queue table")

        # Step 2: Get current queue stats before migration
        cursor.execute("SELECT status, COUNT(*) FROM queue GROUP BY status")
        stats_before = dict(cursor.fetchall())
        total_before = sum(stats_before.values())
        logger.info(f"Queue contains {total_before} items before migration")

        # Step 3: Rename column using ALTER TABLE
        # SQLite 3.25.0+ supports RENAME COLUMN
        logger.info("Renaming column...")
        cursor.execute("ALTER TABLE queue RENAME COLUMN packet_url TO source_url")
        conn.commit()
        logger.info("Column renamed successfully")

        # Step 4: Verify migration
        cursor.execute("PRAGMA table_info(queue)")
        columns_after = {row[1]: row for row in cursor.fetchall()}

        if 'source_url' not in columns_after:
            logger.error("ERROR: source_url column not found after migration")
            return False

        if 'packet_url' in columns_after:
            logger.error("ERROR: packet_url column still exists after migration")
            return False

        # Step 5: Verify data integrity
        cursor.execute("SELECT status, COUNT(*) FROM queue GROUP BY status")
        stats_after = dict(cursor.fetchall())
        total_after = sum(stats_after.values())

        if total_before != total_after:
            logger.error(f"ERROR: Row count mismatch - before: {total_before}, after: {total_after}")
            return False

        logger.info("\n" + "="*60)
        logger.info("MIGRATION COMPLETE")
        logger.info("="*60)
        logger.info(f"Total queue items: {total_after}")
        logger.info(f"Column renamed: packet_url → source_url")
        logger.info("="*60)

        return True

    except sqlite3.OperationalError as e:
        if "no such column" in str(e).lower() or "rename" in str(e).lower():
            logger.error(f"SQLite version may not support RENAME COLUMN: {e}")
            logger.error("This requires SQLite 3.25.0 or later")
        else:
            logger.error(f"Migration failed: {e}")
        conn.rollback()
        return False
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def rollback():
    """Rollback: Rename source_url back to packet_url"""
    if not DB_PATH.exists():
        logger.error(f"Database not found: {DB_PATH}")
        return False

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA table_info(queue)")
        columns = {row[1]: row for row in cursor.fetchall()}

        if 'packet_url' in columns:
            logger.info("Already rolled back: packet_url column exists")
            return True

        logger.info("Rolling back: source_url → packet_url")
        cursor.execute("ALTER TABLE queue RENAME COLUMN source_url TO packet_url")
        conn.commit()
        logger.info("Rollback successful")
        return True

    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        success = rollback()
    else:
        success = migrate()

    exit(0 if success else 1)
