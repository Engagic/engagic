"""
Database Migration: Add Participation Column to Meetings Table

Run this on VPS to add the participation column to existing production databases.

Usage:
    uv run scripts/migrate_add_participation.py

This migration:
1. Adds 'participation' TEXT column to meetings table
2. Safe: uses ALTER TABLE IF NOT EXISTS pattern (idempotent)
3. Does not modify existing data
"""

import sys
import os
import sqlite3
import logging

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import config

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
    """Add participation column to meetings table"""
    logger.info(f"Migrating database: {db_path}")

    if not os.path.exists(db_path):
        logger.error(f"Database not found: {db_path}")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if column already exists
        if check_column_exists(cursor, "meetings", "participation"):
            logger.info("Column 'participation' already exists in meetings table - skipping")
            conn.close()
            return True

        # Add participation column
        logger.info("Adding 'participation' column to meetings table...")
        cursor.execute("ALTER TABLE meetings ADD COLUMN participation TEXT")
        conn.commit()

        # Verify column was added
        if check_column_exists(cursor, "meetings", "participation"):
            logger.info("Successfully added 'participation' column")
        else:
            logger.error("Failed to add 'participation' column")
            conn.close()
            return False

        # Get stats
        cursor.execute("SELECT COUNT(*) FROM meetings")
        total_meetings = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM meetings WHERE participation IS NOT NULL")
        meetings_with_participation = cursor.fetchone()[0]

        logger.info(f"  Total meetings: {total_meetings}")
        logger.info(f"  Meetings with participation: {meetings_with_participation}")

        conn.close()
        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False


def main():
    """Run migration on all databases"""
    logger.info("=" * 60)
    logger.info("Participation Info Migration - Add Participation Column")
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
        logger.info("3. Participation info will be extracted during future processing")
        return 0
    else:
        logger.error("\n" + "=" * 60)
        logger.error("Migration failed")
        logger.error("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
