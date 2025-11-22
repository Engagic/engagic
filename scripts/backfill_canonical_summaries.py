#!/usr/bin/env python3
"""
Backfill canonical_summary for matters that have item summaries but no canonical summary.

This handles matters where items were processed properly but the canonical_summary
at the city_matters level was never populated.
"""

import sqlite3

def backfill_canonical_summaries():
    """Backfill canonical_summary from existing item summaries"""

    # Use VPS db path
    db_path = "/root/engagic/data/engagic.db"
    print(f"Connecting to database: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Find matters where items have summaries but canonical_summary is NULL
    # CRITICAL: Join on composite matter_id to prevent cross-city collisions
    matters_to_backfill = conn.execute("""
        SELECT
            m.id,
            m.matter_file,
            m.banana,
            COUNT(i.id) as item_count
        FROM city_matters m
        JOIN items i ON i.matter_id = m.id
        WHERE (m.canonical_summary IS NULL OR m.canonical_summary = '')
        AND i.summary IS NOT NULL
        GROUP BY m.id
        HAVING COUNT(i.id) >= 1
    """).fetchall()

    print(f"\nFound {len(matters_to_backfill)} matters to backfill")

    backfilled_count = 0

    for matter in matters_to_backfill:
        matter_id = matter['id']

        # Get the first item with a summary as the representative summary
        # (This matches the logic where we pick a representative item)
        # CRITICAL: Query by composite matter_id to prevent cross-city collisions
        item = conn.execute("""
            SELECT summary, topics
            FROM items
            WHERE matter_id = ?
            AND summary IS NOT NULL
            ORDER BY sequence ASC
            LIMIT 1
        """, (matter_id,)).fetchone()

        if not item:
            continue

        canonical_summary = item['summary']
        canonical_topics = item['topics']

        # Update city_matters with canonical summary
        conn.execute("""
            UPDATE city_matters
            SET canonical_summary = ?,
                canonical_topics = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (canonical_summary, canonical_topics, matter_id))

        backfilled_count += 1

        if backfilled_count % 10 == 0:
            print(f"Backfilled {backfilled_count} matters...")

    conn.commit()
    conn.close()

    print(f"\n✓ Backfilled {backfilled_count} canonical summaries")
    print(f"✓ Random Policy will now have {backfilled_count + 54} matters to choose from")

if __name__ == "__main__":
    backfill_canonical_summaries()
