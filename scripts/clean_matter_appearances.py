"""
Clean Orphaned Matter Appearances - November 13, 2025

Problem:
- 2,590 matter_appearances reference non-existent city_matters (old UUID format)
- 1,785 matter_appearances reference non-existent items
- 1,784 records orphaned on BOTH foreign keys
- Total: 4,081 records, only 1,490 valid

Root Cause:
- matter_appearances table contains pre-migration UUIDs
- city_matters migrated to composite IDs on Nov 11-12
- Foreign keys broke for all pre-migration records

Solution:
- Delete all orphaned matter_appearances records
- System will regenerate them during processing as needed
- Preserve 1,490 valid records

Confidence: 10/10 - Simple delete, no data transformation needed
"""

import sqlite3
import logging
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

DB_PATH = "/root/engagic/data/engagic.db"


def backup_database(db_path: str) -> str:
    """Create timestamped backup of database"""
    timestamp = int(datetime.now().timestamp())
    backup_path = f"{db_path}.backup_{timestamp}"

    logger.info(f"[Backup] Creating backup at {backup_path}")

    import shutil
    shutil.copy2(db_path, backup_path)

    if not Path(backup_path).exists():
        raise RuntimeError(f"Backup failed - file not created: {backup_path}")

    backup_size = Path(backup_path).stat().st_size
    original_size = Path(db_path).stat().st_size

    if backup_size != original_size:
        raise RuntimeError(f"Backup size mismatch: {backup_size} != {original_size}")

    logger.info(f"[Backup] SUCCESS: {backup_size:,} bytes backed up")
    return backup_path


def analyze_orphans(conn: sqlite3.Connection) -> dict:
    """Analyze orphaned matter_appearances records"""
    stats = {}

    # Total records
    stats['total'] = conn.execute("SELECT COUNT(*) FROM matter_appearances").fetchone()[0]

    # Orphaned by matter_id
    stats['orphaned_by_matter'] = conn.execute("""
        SELECT COUNT(*) FROM matter_appearances ma
        WHERE NOT EXISTS (SELECT 1 FROM city_matters cm WHERE cm.id = ma.matter_id)
    """).fetchone()[0]

    # Orphaned by item_id
    stats['orphaned_by_item'] = conn.execute("""
        SELECT COUNT(*) FROM matter_appearances ma
        WHERE NOT EXISTS (SELECT 1 FROM items i WHERE i.id = ma.item_id)
    """).fetchone()[0]

    # Orphaned by both
    stats['orphaned_by_both'] = conn.execute("""
        SELECT COUNT(*) FROM matter_appearances ma
        WHERE NOT EXISTS (SELECT 1 FROM city_matters cm WHERE cm.id = ma.matter_id)
        AND NOT EXISTS (SELECT 1 FROM items i WHERE i.id = ma.item_id)
    """).fetchone()[0]

    # Valid records
    stats['valid'] = conn.execute("""
        SELECT COUNT(*) FROM matter_appearances ma
        WHERE EXISTS (SELECT 1 FROM city_matters cm WHERE cm.id = ma.matter_id)
        AND EXISTS (SELECT 1 FROM items i WHERE i.id = ma.item_id)
    """).fetchone()[0]

    # Total orphaned (any FK broken)
    stats['total_orphaned'] = conn.execute("""
        SELECT COUNT(*) FROM matter_appearances ma
        WHERE NOT EXISTS (SELECT 1 FROM city_matters cm WHERE cm.id = ma.matter_id)
        OR NOT EXISTS (SELECT 1 FROM items i WHERE i.id = ma.item_id)
    """).fetchone()[0]

    return stats


def delete_orphaned_records(conn: sqlite3.Connection) -> int:
    """Delete all orphaned matter_appearances records"""
    cursor = conn.execute("""
        DELETE FROM matter_appearances
        WHERE NOT EXISTS (SELECT 1 FROM city_matters cm WHERE cm.id = matter_id)
        OR NOT EXISTS (SELECT 1 FROM items i WHERE i.id = item_id)
    """)
    deleted = cursor.rowcount
    conn.commit()
    return deleted


def main():
    """Run cleanup"""
    logger.info("=" * 80)
    logger.info("Clean Orphaned Matter Appearances - November 13, 2025")
    logger.info("=" * 80)

    # Backup
    backup_path = backup_database(DB_PATH)
    logger.info(f"[Backup] Restore command: cp {backup_path} {DB_PATH}")

    # Connect
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        # Analyze before
        logger.info("\n[Step 1] Analyzing orphaned records")
        before_stats = analyze_orphans(conn)
        logger.info(f"[Analysis] Total records: {before_stats['total']:,}")
        logger.info(f"[Analysis] Valid records: {before_stats['valid']:,}")
        logger.info(f"[Analysis] Orphaned by matter_id: {before_stats['orphaned_by_matter']:,}")
        logger.info(f"[Analysis] Orphaned by item_id: {before_stats['orphaned_by_item']:,}")
        logger.info(f"[Analysis] Orphaned by both: {before_stats['orphaned_by_both']:,}")
        logger.info(f"[Analysis] Total orphaned: {before_stats['total_orphaned']:,}")

        if before_stats['total_orphaned'] == 0:
            logger.info("[Success] No orphaned records found!")
            return 0

        # Delete orphaned records
        logger.info("\n[Step 2] Deleting orphaned records")
        deleted = delete_orphaned_records(conn)
        logger.info(f"[Deleted] {deleted:,} orphaned records")

        # Analyze after
        logger.info("\n[Step 3] Validating cleanup")
        after_stats = analyze_orphans(conn)
        logger.info(f"[Validation] Remaining records: {after_stats['total']:,}")
        logger.info(f"[Validation] Valid records: {after_stats['valid']:,}")
        logger.info(f"[Validation] Orphaned records: {after_stats['total_orphaned']:,}")

        # Summary
        logger.info("\n" + "=" * 80)
        logger.info("CLEANUP COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Records before: {before_stats['total']:,}")
        logger.info(f"Records deleted: {deleted:,}")
        logger.info(f"Records remaining: {after_stats['total']:,}")
        logger.info(f"Orphans remaining: {after_stats['total_orphaned']:,}")

        if after_stats['total_orphaned'] == 0 and after_stats['valid'] == after_stats['total']:
            logger.info("\n[SUCCESS] All orphaned records cleaned up")
            logger.info("System will regenerate matter_appearances during next processing cycle")
            return 0
        else:
            logger.error("\n[FAILED] Cleanup completed with errors")
            logger.error(f"Restore backup: cp {backup_path} {DB_PATH}")
            return 1

    except Exception as e:
        logger.error(f"\n[CRITICAL] Cleanup failed: {e}")
        logger.error(f"Restore backup: cp {backup_path} {DB_PATH}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
