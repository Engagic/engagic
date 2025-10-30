"""
Database Migration: Add Topics Column to Meetings Table

Run this on VPS to add the topics column to existing production databases.

Usage:
    python scripts/migrate_add_topics.py

This migration:
1. Adds 'topics' TEXT column to meetings table
2. Safe: uses ALTER TABLE IF NOT EXISTS pattern (idempotent)
3. Does not modify existing data
"""

import sys
import os
import sqlite3
import logging

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infocore.config import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("migration")


def check_column_exists(cursor, table: str, column: str) -> bool:
    """Check if a column exists in a table"""
    cursor.execute(f"PRAGMA table_info({table})")
    columns = cursor.fetchall()
    return any(col[1] == column for col in columns)


def migrate_database(db_path: str):
    """Add topics column to meetings table"""
    logger.info(f"Migrating database: {db_path}")

    if not os.path.exists(db_path):
        logger.error(f"Database not found: {db_path}")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if column already exists
        if check_column_exists(cursor, "meetings", "topics"):
            logger.info("Column 'topics' already exists in meetings table - skipping")
            conn.close()
            return True

        # Add topics column
        logger.info("Adding 'topics' column to meetings table...")
        cursor.execute("ALTER TABLE meetings ADD COLUMN topics TEXT")
        conn.commit()

        # Verify column was added
        if check_column_exists(cursor, "meetings", "topics"):
            logger.info("Successfully added 'topics' column")
        else:
            logger.error("Failed to add 'topics' column")
            conn.close()
            return False

        # Get stats
        cursor.execute("SELECT COUNT(*) FROM meetings")
        total_meetings = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM meetings WHERE topics IS NOT NULL")
        meetings_with_topics = cursor.fetchone()[0]

        logger.info(f"  Total meetings: {total_meetings}")
        logger.info(f"  Meetings with topics: {meetings_with_topics}")

        conn.close()
        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False


def main():
    """Run migration on all databases"""
    logger.info("=" * 60)
    logger.info("Topic Extraction Migration - Add Topics Column")
    logger.info("=" * 60)

    # Get database path from config
    db_path = config.UNIFIED_DB_PATH

    logger.info(f"\nDatabase path: {db_path}")

    # Run migration
    success = migrate_database(db_path)

    if success:
        logger.info("\n" + "=" * 60)
        logger.info("Migration completed successfully")
        logger.info("=" * 60)
        logger.info("\nNext steps:")
        logger.info("1. Restart the API: systemctl restart engagic-api")
        logger.info("2. Restart the daemon: systemctl restart engagic-daemon")
        logger.info("3. Process meetings to populate topics")
        logger.info("   python jobs/conductor.py --process-all-unprocessed --batch-size 20")
        return 0
    else:
        logger.error("\n" + "=" * 60)
        logger.error("Migration failed")
        logger.error("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
