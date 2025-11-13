#!/usr/bin/env python3
"""
Backfill missing city_matters records from orphaned items.

Context:
A schema constraint error caused 1,600 matters to fail during sync operations
on November 11-12, 2025. Items were stored with matter_id references, but
the corresponding city_matters records were never created due to NOT NULL
constraint violations on first_seen/last_seen columns.

This script reconstructs city_matters records from the available item data.

Usage:
    uv run scripts/backfill_orphaned_matters.py [--dry-run]
"""

import argparse
import hashlib
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_db_path() -> Path:
    """Get production database path."""
    return Path("/root/engagic/data/engagic.db")


def compute_attachment_hash(attachments_json: str | None) -> str | None:
    """Compute hash of attachments for change detection."""
    if not attachments_json:
        return None

    try:
        attachments = json.loads(attachments_json)
        if not attachments:
            return None

        # Sort by URL to ensure consistent hashing
        sorted_urls = sorted([att.get('url', '') for att in attachments])
        combined = '|'.join(sorted_urls)
        return hashlib.sha256(combined.encode()).hexdigest()[:16]
    except (json.JSONDecodeError, TypeError):
        return None


def find_orphaned_matters(conn: sqlite3.Connection) -> list[dict]:
    """
    Query all orphaned matters (items with matter_id but no city_matters record).

    Returns aggregated data needed to reconstruct city_matters records.
    """
    query = """
        SELECT
            i.matter_id,
            m.banana,
            MAX(i.matter_file) as matter_file,
            MAX(i.matter_type) as matter_type,
            MAX(i.title) as title,
            MAX(i.sponsors) as sponsors,
            MAX(i.attachments) as attachments,
            MIN(m.date) as first_seen,
            MAX(m.date) as last_seen,
            COUNT(DISTINCT i.meeting_id) as appearance_count,
            GROUP_CONCAT(i.id || ':' || i.meeting_id, '|') as item_meeting_pairs
        FROM items i
        JOIN meetings m ON i.meeting_id = m.id
        WHERE i.matter_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM city_matters cm WHERE cm.id = i.matter_id
          )
        GROUP BY i.matter_id
        ORDER BY m.banana, first_seen
    """

    cursor = conn.execute(query)
    columns = [desc[0] for desc in cursor.description]

    results = []
    for row in cursor.fetchall():
        matter_dict = dict(zip(columns, row))
        results.append(matter_dict)

    return results


def backfill_matter(conn: sqlite3.Connection, matter: dict, dry_run: bool = False) -> None:
    """
    Create city_matters record and matter_appearances for an orphaned matter.
    """
    matter_id = matter['matter_id']
    banana = matter['banana']

    # Compute attachment hash for change detection
    attachment_hash = compute_attachment_hash(matter['attachments'])
    backfilled_at = datetime.now().isoformat()
    metadata = json.dumps({
        'attachment_hash': attachment_hash,
        'backfilled': True,
        'backfilled_at': backfilled_at
    }) if attachment_hash else json.dumps({'backfilled': True, 'backfilled_at': backfilled_at})

    if dry_run:
        logger.info(
            f"[DRY RUN] Would create city_matters: "
            f"matter_id={matter_id[:16]}... "
            f"banana={banana} "
            f"title={matter['title'][:50]}... "
            f"appearances={matter['appearance_count']}"
        )
    else:
        # Insert into city_matters
        conn.execute("""
            INSERT INTO city_matters (
                id, banana, matter_file, matter_id, matter_type,
                title, canonical_summary, canonical_topics,
                attachments, metadata,
                first_seen, last_seen, sponsors, appearance_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            matter_id,                    # id (composite)
            banana,                       # banana
            matter['matter_file'],        # matter_file (official public ID)
            matter_id,                    # matter_id (backend ID, same as composite)
            matter['matter_type'],        # matter_type
            matter['title'],              # title
            None,                         # canonical_summary (processor will fill)
            None,                         # canonical_topics (processor will fill)
            matter['attachments'],        # attachments JSON
            metadata,                     # metadata JSON
            matter['first_seen'],         # first_seen
            matter['last_seen'],          # last_seen
            matter['sponsors'],           # sponsors JSON
            matter['appearance_count']    # appearance_count
        ))

        # Create matter_appearances for each item/meeting pair
        item_meeting_pairs = matter['item_meeting_pairs'].split('|')
        for pair in item_meeting_pairs:
            item_id, meeting_id = pair.split(':')

            # Get meeting date for appeared_at
            cursor = conn.execute(
                "SELECT date FROM meetings WHERE id = ?",
                (meeting_id,)
            )
            meeting_date = cursor.fetchone()[0]

            conn.execute("""
                INSERT INTO matter_appearances (
                    matter_id, meeting_id, item_id, appeared_at
                ) VALUES (?, ?, ?, ?)
            """, (
                matter_id,
                meeting_id,  # Keep as string
                item_id,     # Keep as string
                meeting_date
            ))

        logger.info(
            f"[Backfilled] matter_id={matter_id[:16]}... "
            f"banana={banana} "
            f"appearances={matter['appearance_count']} "
            f"title={matter['title'][:50]}..."
        )


def verify_backfill(conn: sqlite3.Connection) -> dict:
    """
    Verify backfill success by counting orphaned matters and checking data integrity.
    """
    # Count remaining orphans
    cursor = conn.execute("""
        SELECT COUNT(DISTINCT i.matter_id)
        FROM items i
        WHERE i.matter_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM city_matters cm WHERE cm.id = i.matter_id
          )
    """)
    orphan_count = cursor.fetchone()[0]

    # Count total matters
    cursor = conn.execute("SELECT COUNT(*) FROM city_matters")
    total_matters = cursor.fetchone()[0]

    # Count total appearances
    cursor = conn.execute("SELECT COUNT(*) FROM matter_appearances")
    total_appearances = cursor.fetchone()[0]

    # Count items with matter_id
    cursor = conn.execute("SELECT COUNT(*) FROM items WHERE matter_id IS NOT NULL")
    items_with_matter = cursor.fetchone()[0]

    return {
        'orphan_count': orphan_count,
        'total_matters': total_matters,
        'total_appearances': total_appearances,
        'items_with_matter': items_with_matter
    }


def main():
    parser = argparse.ArgumentParser(description='Backfill orphaned matter records')
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )
    args = parser.parse_args()

    db_path = get_db_path()
    if not db_path.exists():
        logger.error(f"Database not found: {db_path}")
        return 1

    logger.info(f"Connecting to database: {db_path}")
    conn = sqlite3.connect(str(db_path))

    try:
        # Initial verification
        logger.info("Running pre-backfill verification...")
        pre_stats = verify_backfill(conn)
        logger.info(
            f"Pre-backfill state: "
            f"{pre_stats['orphan_count']} orphaned matters, "
            f"{pre_stats['total_matters']} total city_matters, "
            f"{pre_stats['total_appearances']} appearances, "
            f"{pre_stats['items_with_matter']} items with matter_id"
        )

        if pre_stats['orphan_count'] == 0:
            logger.info("No orphaned matters found. Nothing to backfill.")
            return 0

        # Find orphaned matters
        logger.info(f"Finding orphaned matters...")
        orphaned_matters = find_orphaned_matters(conn)
        logger.info(f"Found {len(orphaned_matters)} orphaned matters to backfill")

        if args.dry_run:
            logger.info("DRY RUN MODE - No changes will be made")

            # Show summary by city
            city_counts = {}
            for matter in orphaned_matters:
                banana = matter['banana']
                city_counts[banana] = city_counts.get(banana, 0) + 1

            logger.info(f"\nOrphaned matters by city:")
            for banana, count in sorted(city_counts.items(), key=lambda x: x[1], reverse=True):
                logger.info(f"  {banana}: {count} matters")

            # Show a few examples
            logger.info(f"\nExample orphaned matters:")
            for matter in orphaned_matters[:5]:
                logger.info(
                    f"  {matter['banana']}: {matter['title'][:60]}... "
                    f"({matter['appearance_count']} appearances)"
                )

        # Backfill each matter
        backfilled_count = 0
        for matter in orphaned_matters:
            try:
                backfill_matter(conn, matter, dry_run=args.dry_run)
                backfilled_count += 1
            except Exception as e:
                logger.error(
                    f"Failed to backfill matter {matter['matter_id']}: {e}",
                    exc_info=True
                )

        if not args.dry_run:
            conn.commit()
            logger.info(f"Successfully backfilled {backfilled_count} matters")

            # Post-backfill verification
            logger.info("Running post-backfill verification...")
            post_stats = verify_backfill(conn)
            logger.info(
                f"Post-backfill state: "
                f"{post_stats['orphan_count']} orphaned matters, "
                f"{post_stats['total_matters']} total city_matters "
                f"(+{post_stats['total_matters'] - pre_stats['total_matters']}), "
                f"{post_stats['total_appearances']} appearances "
                f"(+{post_stats['total_appearances'] - pre_stats['total_appearances']})"
            )

            if post_stats['orphan_count'] == 0:
                logger.info("SUCCESS: All orphaned matters have been backfilled")
            else:
                logger.warning(
                    f"WARNING: {post_stats['orphan_count']} orphaned matters remain"
                )
        else:
            logger.info(f"DRY RUN: Would have backfilled {backfilled_count} matters")

        return 0

    except Exception as e:
        logger.error(f"Backfill failed: {e}", exc_info=True)
        conn.rollback()
        return 1
    finally:
        conn.close()


if __name__ == '__main__':
    exit(main())
