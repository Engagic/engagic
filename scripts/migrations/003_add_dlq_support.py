#!/usr/bin/env python3
"""
Migration 003: Add Dead Letter Queue Support

Adds:
- failed_at TIMESTAMP column
- 'dead_letter' status to CHECK constraint

Author: Phase 2 Foundation Fixes
Date: 2025-11-10
"""

import sqlite3
import sys
import os
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from config import config


def backup_table(conn: sqlite3.Connection, dry_run: bool = False):
    """Backup queue table before migration"""
    print("\n[Backup] Creating backup of queue table...")

    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM queue")
    count = cursor.fetchone()[0]
    print(f"[Backup] Found {count} jobs in queue")

    if not dry_run:
        # Create backup table with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"queue_backup_{timestamp}"

        cursor.execute(f"DROP TABLE IF EXISTS {backup_name}")
        cursor.execute(f"CREATE TABLE {backup_name} AS SELECT * FROM queue")
        conn.commit()

        cursor.execute(f"SELECT COUNT(*) FROM {backup_name}")
        backup_count = cursor.fetchone()[0]
        print(f"[Backup] Created {backup_name} with {backup_count} jobs")
        return backup_name
    else:
        print("[Backup] DRY RUN - would create backup table")
        return None


def migrate_queue_table(conn: sqlite3.Connection, dry_run: bool = False):
    """Migrate queue table to include DLQ support

    SQLite doesn't support modifying CHECK constraints, so we:
    1. Create new table with updated schema
    2. Copy all data
    3. Drop old table
    4. Rename new table

    Confidence: 9/10 - Standard SQLite migration pattern
    """
    print("\n[Migration] Adding DLQ support to queue table...")

    cursor = conn.cursor()

    # Check current schema
    cursor.execute("PRAGMA table_info(queue)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}

    has_failed_at = 'failed_at' in columns
    print(f"[Migration] Current schema has 'failed_at' column: {has_failed_at}")

    if not dry_run:
        # Create new table with updated schema
        cursor.execute("""
            CREATE TABLE queue_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_url TEXT NOT NULL UNIQUE,
                meeting_id TEXT,
                banana TEXT,
                status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'dead_letter')),
                priority INTEGER DEFAULT 0,
                retry_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                failed_at TIMESTAMP,
                error_message TEXT,
                processing_metadata TEXT,
                FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE,
                FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE
            )
        """)

        # Copy data from old table to new
        # Handle both cases: with and without failed_at column
        if has_failed_at:
            cursor.execute("""
                INSERT INTO queue_new
                SELECT * FROM queue
            """)
        else:
            cursor.execute("""
                INSERT INTO queue_new
                (id, source_url, meeting_id, banana, status, priority, retry_count,
                 created_at, started_at, completed_at, error_message, processing_metadata)
                SELECT
                    id, source_url, meeting_id, banana, status, priority, retry_count,
                    created_at, started_at, completed_at, error_message, processing_metadata
                FROM queue
            """)

        rows_copied = cursor.rowcount
        print(f"[Migration] Copied {rows_copied} jobs to new table")

        # Drop old table and rename new one
        cursor.execute("DROP TABLE queue")
        cursor.execute("ALTER TABLE queue_new RENAME TO queue")

        conn.commit()
        print("[Migration] Migration complete!")
    else:
        print("[Migration] DRY RUN - would create new table and migrate data")


def verify_migration(conn: sqlite3.Connection):
    """Verify migration was successful"""
    print("\n[Verification] Checking migration results...")

    cursor = conn.cursor()

    # Check schema
    cursor.execute("PRAGMA table_info(queue)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}

    has_failed_at = 'failed_at' in columns
    print(f"[Verification] Schema has 'failed_at' column: {has_failed_at}")

    # Check data integrity
    cursor.execute("SELECT COUNT(*) FROM queue")
    count = cursor.fetchone()[0]
    print(f"[Verification] Queue has {count} jobs")

    # Check status values
    cursor.execute("SELECT status, COUNT(*) FROM queue GROUP BY status")
    for row in cursor.fetchall():
        print(f"[Verification]   - {row[0]}: {row[1]} jobs")

    # Verify CHECK constraint by attempting to insert invalid status
    try:
        cursor.execute("""
            INSERT INTO queue (source_url, status)
            VALUES ('test_invalid_status', 'invalid')
        """)
        print("[Verification] ERROR - CHECK constraint not working!")
        return False
    except sqlite3.IntegrityError as e:
        if "CHECK constraint failed" in str(e):
            print("[Verification] CHECK constraint working correctly")
            conn.rollback()
        else:
            raise

    # Test dead_letter status is allowed
    try:
        cursor.execute("""
            INSERT INTO queue (source_url, status, failed_at)
            VALUES ('test_dlq_status', 'dead_letter', CURRENT_TIMESTAMP)
        """)
        cursor.execute("DELETE FROM queue WHERE source_url = 'test_dlq_status'")
        conn.commit()
        print("[Verification] 'dead_letter' status accepted correctly")
    except sqlite3.IntegrityError as e:
        print(f"[Verification] ERROR - 'dead_letter' status rejected: {e}")
        return False

    print("[Verification] All checks passed!")
    return True


def main():
    """Run migration"""
    import argparse

    parser = argparse.ArgumentParser(description="Add DLQ support to queue table")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    parser.add_argument(
        "--db-path",
        default=config.UNIFIED_DB_PATH,
        help=f"Database path (default: {config.UNIFIED_DB_PATH})"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Migration 003: Add Dead Letter Queue Support")
    print("=" * 60)
    print(f"Database: {args.db_path}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print()

    if not os.path.exists(args.db_path):
        print(f"ERROR: Database not found at {args.db_path}")
        return 1

    # Connect to database
    conn = sqlite3.connect(args.db_path)
    conn.row_factory = sqlite3.Row

    try:
        # Backup
        backup_name = backup_table(conn, dry_run=args.dry_run)

        # Migrate
        migrate_queue_table(conn, dry_run=args.dry_run)

        if not args.dry_run:
            # Verify
            success = verify_migration(conn)

            if success:
                print("\n" + "=" * 60)
                print("Migration completed successfully!")
                print("=" * 60)
                if backup_name:
                    print(f"\nBackup table: {backup_name}")
                    print("(Can be dropped after verifying everything works)")
                return 0
            else:
                print("\nERROR: Verification failed!")
                print(f"Restore from backup: {backup_name}")
                return 1
        else:
            print("\n" + "=" * 60)
            print("DRY RUN complete - no changes made")
            print("=" * 60)
            print("\nRun without --dry-run to apply migration")
            return 0

    except Exception as e:
        print(f"\nERROR during migration: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
