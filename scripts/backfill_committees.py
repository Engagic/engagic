"""Backfill committees table from existing meeting titles

One-time script to populate the committees table by extracting unique
committee names from meetings.title field.

Usage:
    uv run scripts/backfill_committees.py
"""

import asyncio
import sys
sys.path.insert(0, '/opt/engagic')

from database.db_postgres import Database
from config import get_logger

logger = get_logger(__name__)


def is_committee_title(title: str) -> bool:
    """Filter to committee-like titles"""
    if not title:
        return False
    title_lower = title.lower()
    return (
        'committee' in title_lower or
        'council' in title_lower or
        'commission' in title_lower or
        'board' in title_lower or
        'task force' in title_lower or
        'subcommittee' in title_lower
    )


async def backfill_committees():
    """Extract committees from meeting titles and insert into committees table"""
    db = await Database.create()

    try:
        # Get distinct meeting titles per banana
        rows = await db.pool.fetch('''
            SELECT DISTINCT banana, title
            FROM meetings
            WHERE title IS NOT NULL
            ORDER BY banana, title
        ''')

        print(f"Found {len(rows)} unique meeting titles")

        created = 0
        skipped = 0
        by_city = {}

        for row in rows:
            banana = row['banana']
            title = row['title']

            # Skip non-committee meetings
            if not is_committee_title(title):
                skipped += 1
                continue

            committee = await db.committees.find_or_create_committee(
                banana=banana,
                name=title,
                description=None
            )

            # Track by city
            if banana not in by_city:
                by_city[banana] = 0
            by_city[banana] += 1
            created += 1

        print(f"\nCreated {created} committees, skipped {skipped} non-committee titles")
        print("\nCommittees by city:")
        for banana, count in sorted(by_city.items(), key=lambda x: -x[1])[:20]:
            print(f"  {banana}: {count}")

    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(backfill_committees())
