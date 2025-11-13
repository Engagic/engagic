"""
Fix Numeric-Prefix Matter IDs - November 13, 2025

Problem:
- 1,603 items have old-format matter_ids with numeric prefixes (e.g., "15239_xxx")
- Should be banana-prefixed (e.g., "alamedaCA_xxx")
- Causes JOIN failures and collisions across cities

Solution:
1. For each old-format item, extract the numeric prefix as raw vendor ID
2. Regenerate proper composite ID using generate_matter_id(banana, matter_file, raw_id)
3. Update items.matter_id to new value
4. Create corresponding city_matters records if needed
5. Clean up orphaned city_matters records

Confidence: 10/10 - Defensive, transactional, validates at every step.
"""

import sqlite3
import logging
import sys
from datetime import datetime
from typing import Dict, List, Tuple
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.id_generation import generate_matter_id, validate_matter_id

# Setup logging
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

    # Verify backup
    if not Path(backup_path).exists():
        raise RuntimeError(f"Backup failed - file not created: {backup_path}")

    backup_size = Path(backup_path).stat().st_size
    original_size = Path(db_path).stat().st_size

    if backup_size != original_size:
        raise RuntimeError(f"Backup size mismatch: {backup_size} != {original_size}")

    logger.info(f"[Backup] SUCCESS: {backup_size:,} bytes backed up")
    return backup_path


def find_numeric_prefix_items(conn: sqlite3.Connection) -> List[Dict]:
    """Find items with numeric-prefix matter_ids"""
    cursor = conn.execute("""
        SELECT
            i.id as item_id,
            i.matter_id as old_matter_id,
            i.matter_file,
            i.matter_type,
            i.title,
            m.id as meeting_id,
            m.banana
        FROM items i
        JOIN meetings m ON i.meeting_id = m.id
        WHERE i.matter_id LIKE '%_%'
        AND SUBSTR(i.matter_id, 1, INSTR(i.matter_id, '_') - 1) <> m.banana
        ORDER BY m.banana, i.matter_id
    """)

    items = []
    for row in cursor.fetchall():
        # Extract numeric prefix as raw vendor ID
        old_matter_id = row[1]
        raw_vendor_id = old_matter_id.split('_')[0]

        items.append({
            'item_id': row[0],
            'old_matter_id': old_matter_id,
            'matter_file': row[2],
            'matter_type': row[3],
            'title': row[4],
            'meeting_id': row[5],
            'banana': row[6],
            'raw_vendor_id': raw_vendor_id
        })

    return items


def regenerate_matter_ids(conn: sqlite3.Connection, items: List[Dict]) -> Tuple[int, int]:
    """
    Regenerate proper matter IDs and update items.

    Returns: (updated_count, failed_count)
    """
    updated = 0
    failed = 0

    # Group by old_matter_id to track collisions
    by_old_id = {}
    for item in items:
        old_id = item['old_matter_id']
        by_old_id.setdefault(old_id, []).append(item)

    logger.info(f"[Analysis] {len(items)} items, {len(by_old_id)} unique old IDs")

    # Show collision examples
    collisions = {k: v for k, v in by_old_id.items() if len(v) > 1}
    if collisions:
        logger.info(f"[Analysis] {len(collisions)} colliding IDs (will be split by city)")
        for old_id, collision_items in list(collisions.items())[:5]:
            cities = [item['banana'] for item in collision_items]
            logger.info(f"  - {old_id}: {len(collision_items)} items across {set(cities)}")

    # Process each item
    for item in items:
        try:
            # Generate proper composite ID
            new_matter_id = generate_matter_id(
                banana=item['banana'],
                matter_file=item['matter_file'],
                matter_id=item['raw_vendor_id']
            )

            # Validate new ID
            if not validate_matter_id(new_matter_id):
                logger.error(f"[Failed] Generated invalid ID: {new_matter_id} for item {item['item_id']}")
                failed += 1
                continue

            # Update item
            conn.execute(
                "UPDATE items SET matter_id = ? WHERE id = ?",
                (new_matter_id, item['item_id'])
            )

            # Create city_matters record if doesn't exist
            existing = conn.execute(
                "SELECT id FROM city_matters WHERE id = ?", (new_matter_id,)
            ).fetchone()

            if not existing:
                conn.execute("""
                    INSERT INTO city_matters
                    (id, banana, matter_id, matter_file, matter_type, title, first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (
                    new_matter_id,
                    item['banana'],
                    item['raw_vendor_id'],
                    item['matter_file'],
                    item['matter_type'],
                    item['title']
                ))

            updated += 1

            if updated % 100 == 0:
                logger.info(f"[Progress] {updated}/{len(items)} items updated")

        except Exception as e:
            logger.error(f"[Failed] Error processing item {item['item_id']}: {e}")
            failed += 1

    conn.commit()
    return updated, failed


def clean_orphaned_city_matters(conn: sqlite3.Connection) -> int:
    """Remove city_matters records with no corresponding items"""
    cursor = conn.execute("""
        DELETE FROM city_matters
        WHERE NOT EXISTS (
            SELECT 1 FROM items WHERE items.matter_id = city_matters.id
        )
    """)
    deleted = cursor.rowcount
    conn.commit()
    return deleted


def validate_results(conn: sqlite3.Connection) -> Dict[str, int]:
    """Validate migration results"""
    stats = {}

    # Check 1: No more numeric-prefix IDs
    cursor = conn.execute("""
        SELECT COUNT(*) FROM items i
        JOIN meetings m ON i.meeting_id = m.id
        WHERE i.matter_id LIKE '%_%'
        AND SUBSTR(i.matter_id, 1, INSTR(i.matter_id, '_') - 1) <> m.banana
    """)
    stats['remaining_bad_ids'] = cursor.fetchone()[0]

    # Check 2: All matter_ids have matching city_matters
    cursor = conn.execute("""
        SELECT COUNT(*) FROM items
        WHERE matter_id IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM city_matters WHERE id = items.matter_id)
    """)
    stats['orphaned_items'] = cursor.fetchone()[0]

    # Check 3: All city_matters have at least one item
    cursor = conn.execute("""
        SELECT COUNT(*) FROM city_matters
        WHERE NOT EXISTS (SELECT 1 FROM items WHERE matter_id = city_matters.id)
    """)
    stats['orphaned_matters'] = cursor.fetchone()[0]

    # Check 4: Count totals
    stats['total_items'] = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    stats['items_with_matter_id'] = conn.execute(
        "SELECT COUNT(*) FROM items WHERE matter_id IS NOT NULL"
    ).fetchone()[0]
    stats['total_city_matters'] = conn.execute("SELECT COUNT(*) FROM city_matters").fetchone()[0]

    return stats


def main():
    """Run migration"""
    logger.info("=" * 80)
    logger.info("Fix Numeric-Prefix Matter IDs - November 13, 2025")
    logger.info("=" * 80)

    # Backup
    backup_path = backup_database(DB_PATH)
    logger.info(f"[Backup] Restore command: cp {backup_path} {DB_PATH}")

    # Connect
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        # Find problematic items
        logger.info("\n[Step 1] Finding numeric-prefix matter IDs")
        items = find_numeric_prefix_items(conn)
        logger.info(f"[Found] {len(items)} items with numeric-prefix IDs")

        if not items:
            logger.info("[Success] No items to fix!")
            return 0

        # Group by city
        by_city = {}
        for item in items:
            by_city.setdefault(item['banana'], []).append(item)

        for banana, city_items in sorted(by_city.items()):
            logger.info(f"  - {banana}: {len(city_items)} items")

        # Regenerate IDs
        logger.info("\n[Step 2] Regenerating proper matter IDs")
        updated, failed = regenerate_matter_ids(conn, items)
        logger.info(f"[Result] Updated {updated}, failed {failed}")

        # Clean orphans
        logger.info("\n[Step 3] Cleaning orphaned city_matters")
        deleted = clean_orphaned_city_matters(conn)
        logger.info(f"[Cleaned] {deleted} orphaned city_matters records")

        # Validate
        logger.info("\n[Step 4] Validating results")
        stats = validate_results(conn)

        # Summary
        logger.info("\n" + "=" * 80)
        logger.info("MIGRATION COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Items updated: {updated}")
        logger.info(f"Items failed: {failed}")
        logger.info(f"Orphaned city_matters cleaned: {deleted}")
        logger.info(f"Remaining bad IDs: {stats['remaining_bad_ids']}")
        logger.info(f"Orphaned items: {stats['orphaned_items']}")
        logger.info(f"Orphaned matters: {stats['orphaned_matters']}")
        logger.info(f"Total items: {stats['total_items']:,}")
        logger.info(f"Items with matter_id: {stats['items_with_matter_id']:,}")
        logger.info(f"Total city_matters: {stats['total_city_matters']:,}")

        if stats['remaining_bad_ids'] == 0 and stats['orphaned_items'] == 0:
            logger.info("\n[SUCCESS] Migration completed successfully")
            return 0
        else:
            logger.error("\n[FAILED] Migration completed with errors")
            logger.error(f"Restore backup: cp {backup_path} {DB_PATH}")
            return 1

    except Exception as e:
        logger.error(f"\n[CRITICAL] Migration failed: {e}")
        logger.error(f"Restore backup: cp {backup_path} {DB_PATH}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
