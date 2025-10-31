#!/usr/bin/env python3
"""
Database migration: packet_url → agenda_url for HTML agendas

Semantic clarification:
- agenda_url: HTML page to view (item-based meetings)
- packet_url: PDF file to download (monolithic meetings)
- Rule: ONE OR THE OTHER, never both

Migration logic:
1. Meetings with items → packet_url becomes agenda_url
2. Meetings without items → keep packet_url
3. Add agenda_url column to schema
"""

import sqlite3
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = Path("/root/engagic/data/engagic.db")


def migrate():
    """Migrate packet_url to agenda_url for item-based meetings"""

    if not DB_PATH.exists():
        logger.error(f"Database not found: {DB_PATH}")
        return False

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Step 1: Add agenda_url column if it doesn't exist
        logger.info("Adding agenda_url column to meetings table...")
        try:
            cursor.execute("ALTER TABLE meetings ADD COLUMN agenda_url TEXT")
            conn.commit()
            logger.info("✓ Added agenda_url column")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logger.info("✓ agenda_url column already exists")
            else:
                raise

        # Step 2: Get meetings with items (these should use agenda_url)
        cursor.execute("""
            SELECT DISTINCT m.id, m.packet_url
            FROM meetings m
            JOIN items i ON m.id = i.meeting_id
            WHERE m.packet_url IS NOT NULL
        """)
        meetings_with_items = cursor.fetchall()

        logger.info(f"Found {len(meetings_with_items)} meetings with items that need migration")

        # Step 3: Migrate packet_url → agenda_url for item-based meetings
        migrated = 0
        for meeting_id, packet_url in meetings_with_items:
            cursor.execute("""
                UPDATE meetings
                SET agenda_url = ?, packet_url = NULL
                WHERE id = ?
            """, (packet_url, meeting_id))
            migrated += 1

        conn.commit()
        logger.info(f"✓ Migrated {migrated} meetings: packet_url → agenda_url")

        # Step 4: Report final state
        cursor.execute("SELECT COUNT(*) FROM meetings WHERE agenda_url IS NOT NULL")
        agenda_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM meetings WHERE packet_url IS NOT NULL")
        packet_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM meetings WHERE agenda_url IS NOT NULL AND packet_url IS NOT NULL")
        both_count = cursor.fetchone()[0]

        logger.info("\n" + "="*60)
        logger.info("MIGRATION COMPLETE")
        logger.info("="*60)
        logger.info(f"Meetings with agenda_url: {agenda_count}")
        logger.info(f"Meetings with packet_url: {packet_count}")
        logger.info(f"Meetings with BOTH (should be 0): {both_count}")
        logger.info("="*60)

        if both_count > 0:
            logger.error("ERROR: Some meetings have both agenda_url and packet_url!")
            return False

        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    success = migrate()
    exit(0 if success else 1)
