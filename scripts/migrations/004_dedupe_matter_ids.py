"""
Migration 004: Deduplicate Matter IDs

Fixes dual ID generation bug where matters were created with both:
- Literal IDs: {banana}_{matter_file} (e.g., mountainviewCA_205649)
- Hashed IDs: {banana}_{hash} (e.g., mountainviewCA_46dabe9585577ebd)

Strategy:
1. Find all duplicate matter records (same banana+matter_file+matter_id)
2. For each duplicate pair:
   - Keep the hashed ID (canonical)
   - Copy canonical_summary from literal ID if present
   - Delete the literal ID version

Run with --dry-run to preview changes without applying them.

Usage:
    python scripts/migrations/004_dedupe_matter_ids.py [--dry-run]
"""

import sqlite3
import sys
import os
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from database.id_generation import validate_matter_id
from config import Config

config = Config()


def find_duplicates(conn: sqlite3.Connection) -> list:
    """Find all duplicate matter records

    Returns:
        List of tuples: (banana, matter_file, matter_id, literal_id, hashed_id, literal_has_summary, hashed_has_summary)
    """
    cursor = conn.cursor()

    # Find matters that appear more than once with same banana+matter_file+matter_id
    cursor.execute("""
        SELECT
            banana,
            matter_file,
            matter_id,
            GROUP_CONCAT(id) as ids,
            GROUP_CONCAT(CASE WHEN LENGTH(canonical_summary) > 0 THEN '1' ELSE '0' END) as has_summaries
        FROM city_matters
        WHERE matter_file IS NOT NULL AND matter_id IS NOT NULL
        GROUP BY banana, matter_file, matter_id
        HAVING COUNT(*) > 1
    """)

    duplicates = []
    for row in cursor.fetchall():
        banana, matter_file, matter_id_str, ids_str, summaries_str = row
        ids = ids_str.split(',')
        has_summaries = summaries_str.split(',')

        # Identify which is literal vs hashed
        literal_id = None
        hashed_id = None
        literal_has_summary = False
        hashed_has_summary = False

        for i, id_val in enumerate(ids):
            if validate_matter_id(id_val):
                # This is the hashed version
                hashed_id = id_val
                hashed_has_summary = has_summaries[i] == '1'
            else:
                # This is the literal version
                literal_id = id_val
                literal_has_summary = has_summaries[i] == '1'

        if literal_id and hashed_id:
            duplicates.append((
                banana,
                matter_file,
                matter_id_str,
                literal_id,
                hashed_id,
                literal_has_summary,
                hashed_has_summary
            ))

    return duplicates


def merge_matter(conn: sqlite3.Connection, banana: str, matter_file: str, matter_id_str: str,
                 literal_id: str, hashed_id: str, literal_has_summary: bool,
                 hashed_has_summary: bool, dry_run: bool = False) -> bool:
    """Merge duplicate matter records, keeping the hashed version

    Args:
        conn: Database connection
        banana: City identifier
        matter_file: Matter file identifier
        matter_id_str: Matter ID
        literal_id: Literal ID to delete
        hashed_id: Hashed ID to keep
        literal_has_summary: Whether literal version has summary
        hashed_has_summary: Whether hashed version has summary
        dry_run: If True, don't actually modify database

    Returns:
        True if merge successful
    """
    cursor = conn.cursor()

    # Get both records
    cursor.execute("SELECT * FROM city_matters WHERE id = ?", (literal_id,))
    literal_record = cursor.fetchone()

    cursor.execute("SELECT * FROM city_matters WHERE id = ?", (hashed_id,))
    hashed_record = cursor.fetchone()

    if not literal_record or not hashed_record:
        print("  ERROR: Could not find both records")
        return False

    # If literal has summary but hashed doesn't, copy it
    if literal_has_summary and not hashed_has_summary:
        cursor.execute("""
            SELECT canonical_summary, canonical_topics
            FROM city_matters
            WHERE id = ?
        """, (literal_id,))
        literal_summary, literal_topics = cursor.fetchone()

        print(f"  → Copying summary from {literal_id} to {hashed_id}")

        if not dry_run:
            cursor.execute("""
                UPDATE city_matters
                SET canonical_summary = ?,
                    canonical_topics = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (literal_summary, literal_topics, hashed_id))

    # Delete the literal version
    print(f"  → Deleting duplicate {literal_id}")

    if not dry_run:
        cursor.execute("DELETE FROM city_matters WHERE id = ?", (literal_id,))

    return True


def main():
    dry_run = '--dry-run' in sys.argv

    if dry_run:
        print("=" * 60)
        print("DRY RUN MODE - No changes will be applied")
        print("=" * 60)
        print()

    db_path = config.UNIFIED_DB_PATH

    if not os.path.exists(db_path):
        print(f"ERROR: Database not found at {db_path}")
        sys.exit(1)

    # Backup database first
    if not dry_run:
        backup_path = f"{db_path}.before-dedupe-{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        print(f"Creating backup: {backup_path}")
        os.system(f"cp {db_path} {backup_path}")
        print()

    # Connect to database
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        # Find duplicates
        print("Scanning for duplicate matters...")
        duplicates = find_duplicates(conn)

        print(f"Found {len(duplicates)} duplicate matter pairs")
        print()

        if not duplicates:
            print("No duplicates found - nothing to do!")
            return

        # Process each duplicate
        success_count = 0
        for dup in duplicates:
            banana, matter_file, matter_id_str, literal_id, hashed_id, literal_has_summary, hashed_has_summary = dup

            print(f"Matter: {banana} / {matter_file} / {matter_id_str}")
            print(f"  Literal ID: {literal_id} (summary: {literal_has_summary})")
            print(f"  Hashed ID:  {hashed_id} (summary: {hashed_has_summary})")

            if merge_matter(conn, banana, matter_file, matter_id_str, literal_id, hashed_id,
                           literal_has_summary, hashed_has_summary, dry_run):
                success_count += 1

            print()

        if not dry_run:
            conn.commit()
            print(f"✅ Successfully merged {success_count}/{len(duplicates)} duplicate pairs")
        else:
            print(f"DRY RUN: Would merge {success_count}/{len(duplicates)} duplicate pairs")

        # Verify uniqueness
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as total,
                   COUNT(DISTINCT banana || ':' || COALESCE(matter_file, '') || ':' || COALESCE(matter_id, '')) as unique_keys
            FROM city_matters
        """)
        total, unique = cursor.fetchone()

        print()
        print(f"Final state: {total} total matters, {unique} unique keys")

        if total == unique:
            print("✅ All matters are unique!")
        else:
            print(f"⚠️  Still have {total - unique} duplicates remaining")

    finally:
        conn.close()


if __name__ == '__main__':
    main()
