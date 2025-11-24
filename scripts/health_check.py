#!/usr/bin/env python3
"""
Quick health check for all cities.

Shows summary statistics and flags potential issues.

Migrated to async PostgreSQL.
"""

import os
import sys
import asyncio
from collections import defaultdict
from typing import Dict, List, Tuple

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_postgres import Database

# Confidence: 9/10 - Simple SQL aggregation queries


async def get_city_stats(db: Database) -> Dict:
    """Get overall city statistics"""
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                COUNT(*) as total_cities,
                COUNT(DISTINCT vendor) as total_vendors,
                COUNT(CASE WHEN status = 'active' THEN 1 END) as active_cities,
                COUNT(CASE WHEN status != 'active' THEN 1 END) as inactive_cities
            FROM cities
        """)

    return {
        "total_cities": row["total_cities"],
        "total_vendors": row["total_vendors"],
        "active_cities": row["active_cities"],
        "inactive_cities": row["inactive_cities"],
    }


async def get_vendor_breakdown(db: Database) -> List[Tuple[str, int, int]]:
    """Get city and meeting counts by vendor"""
    async with db.pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                c.vendor,
                COUNT(DISTINCT c.banana) as city_count,
                COUNT(m.id) as meeting_count
            FROM cities c
            LEFT JOIN meetings m ON c.banana = m.banana
            GROUP BY c.vendor
            ORDER BY city_count DESC
        """)
    return [(row["vendor"], row["city_count"], row["meeting_count"]) for row in rows]


async def get_cities_with_no_meetings(db: Database) -> List[Tuple[str, str, str, str]]:
    """Find cities with zero meetings"""
    async with db.pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT c.banana, c.name, c.state, c.vendor
            FROM cities c
            LEFT JOIN meetings m ON c.banana = m.banana
            WHERE c.status = 'active'
            GROUP BY c.banana, c.name, c.state, c.vendor
            HAVING COUNT(m.id) = 0
            ORDER BY c.vendor, c.name
        """)
    return [(row["banana"], row["name"], row["state"], row["vendor"]) for row in rows]


async def get_cities_with_most_meetings(db: Database, limit=10) -> List[Tuple[str, str, str, int]]:
    """Get top cities by meeting count"""
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT c.banana, c.name, c.state, COUNT(m.id) as meeting_count
            FROM cities c
            INNER JOIN meetings m ON c.banana = m.banana
            GROUP BY c.banana, c.name, c.state
            ORDER BY meeting_count DESC
            LIMIT $1
        """,
            limit,
        )
    return [(row["banana"], row["name"], row["state"], row["meeting_count"]) for row in rows]


async def get_recent_activity(db: Database) -> List[Tuple[str, str, int]]:
    """Get cities synced recently"""
    async with db.pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT c.name, c.state, COUNT(m.id) as meetings
            FROM cities c
            INNER JOIN meetings m ON c.banana = m.banana
            WHERE m.created_at > NOW() - INTERVAL '7 days'
            GROUP BY c.banana, c.name, c.state
            ORDER BY meetings DESC
            LIMIT 10
        """)
    return [(row["name"], row["state"], row["meetings"]) for row in rows]


async def get_processing_stats(db: Database) -> Dict:
    """Get AI processing statistics"""
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                COUNT(*) as total_meetings,
                COUNT(CASE WHEN processing_status = 'completed' THEN 1 END) as completed,
                COUNT(CASE WHEN processing_status = 'pending' THEN 1 END) as pending,
                COUNT(CASE WHEN processing_status = 'failed' THEN 1 END) as failed,
                COUNT(CASE WHEN summary IS NOT NULL THEN 1 END) as with_summaries
            FROM meetings
        """)

    return {
        "total_meetings": row["total_meetings"],
        "completed": row["completed"],
        "pending": row["pending"],
        "failed": row["failed"],
        "with_summaries": row["with_summaries"],
    }


async def detect_potential_corruption(db: Database) -> List[Dict]:
    """Detect potential data corruption issues"""
    issues = []

    async with db.pool.acquire() as conn:
        # Check for meetings with packet URLs from wrong vendor domains
        rows = await conn.fetch("""
            SELECT c.banana, c.name, c.vendor, c.slug, m.packet_url
            FROM cities c
            INNER JOIN meetings m ON c.banana = m.banana
            WHERE m.packet_url IS NOT NULL
            LIMIT 100
        """)

    vendor_patterns = {
        "primegov": ".primegov.com",
        "granicus": (".granicus.com", "s3.amazonaws.com"),
        "civicclerk": ".civicclerk.com",
        "novusagenda": ".novusagenda.com",
        "civicplus": ".civicplus.com",
        "civicweb": ".civicweb.net",
        "legistar": "legistar",
    }

    for row in rows:
        banana = row["banana"]
        name = row["name"]
        vendor = row["vendor"]
        packet_url = row["packet_url"]

        if vendor in vendor_patterns:
            patterns = vendor_patterns[vendor]
            if isinstance(patterns, str):
                patterns = (patterns,)

            if not any(p in packet_url.lower() for p in patterns):
                issues.append(
                    {
                        "banana": banana,
                        "name": name,
                        "vendor": vendor,
                        "packet_url": packet_url[:80],
                    }
                )

    return issues


async def main():
    print("=" * 80)
    print("ENGAGIC HEALTH CHECK (PostgreSQL)")
    print("=" * 80)
    print()

    # Create async database connection
    db = await Database.create()

    try:
        # Overall stats
        stats = await get_city_stats(db)
        print(f"Total Cities: {stats['total_cities']}")
        print(f"Active Cities: {stats['active_cities']}")
        print(f"Inactive Cities: {stats['inactive_cities']}")
        print(f"Unique Vendors: {stats['total_vendors']}")
        print()

        # Vendor breakdown
        print("=" * 80)
        print("CITIES & MEETINGS BY VENDOR")
        print("=" * 80)
        print(f"{'Vendor':<20} {'Cities':<10} {'Meetings':<10}")
        print("-" * 80)
        for vendor, city_count, meeting_count in await get_vendor_breakdown(db):
            print(f"{vendor:<20} {city_count:<10} {meeting_count:<10}")
        print()

        # Processing stats
        proc_stats = await get_processing_stats(db)
        print("=" * 80)
        print("AI PROCESSING STATUS")
        print("=" * 80)
        print(f"Total Meetings: {proc_stats['total_meetings']}")
        print(
            f"With Summaries: {proc_stats['with_summaries']} ({proc_stats['with_summaries'] / max(proc_stats['total_meetings'], 1) * 100:.1f}%)"
        )
        print(f"Completed: {proc_stats['completed']}")
        print(f"Pending: {proc_stats['pending']}")
        print(f"Failed: {proc_stats['failed']}")
        print()

        # Top cities
        print("=" * 80)
        print("TOP 10 CITIES BY MEETING COUNT")
        print("=" * 80)
        for banana, name, state, count in await get_cities_with_most_meetings(db):
            print(f"{name}, {state}: {count} meetings")
        print()

        # Cities with no meetings
        no_meetings = await get_cities_with_no_meetings(db)
        print("=" * 80)
        print(f"CITIES WITH NO MEETINGS ({len(no_meetings)} total)")
        print("=" * 80)
        if no_meetings:
            # Group by vendor for easier reading
            by_vendor = defaultdict(list)
            for banana, name, state, vendor in no_meetings:
                by_vendor[vendor].append(f"{name}, {state}")

            for vendor, cities in sorted(by_vendor.items()):
                print(f"\n{vendor.upper()} ({len(cities)} cities):")
                for city in cities[:10]:  # Show first 10
                    print(f"  - {city}")
                if len(cities) > 10:
                    print(f"  ... and {len(cities) - 10} more")
        print()

        # Potential corruption
        corruption_issues = await detect_potential_corruption(db)
        if corruption_issues:
            print("=" * 80)
            print(f"POTENTIAL CORRUPTION DETECTED ({len(corruption_issues)} issues)")
            print("=" * 80)
            for issue in corruption_issues[:20]:  # Show first 20
                print(f"{issue['name']} ({issue['vendor']})")
                print(f"  Packet URL: {issue['packet_url']}")
            if len(corruption_issues) > 20:
                print(f"  ... and {len(corruption_issues) - 20} more")
            print()

        # Recent activity
        print("=" * 80)
        print("RECENT ACTIVITY (Last 7 Days)")
        print("=" * 80)
        recent = await get_recent_activity(db)
        if recent:
            for name, state, meetings in recent:
                print(f"{name}, {state}: {meetings} meetings added")
        else:
            print("No recent activity")
        print()

    finally:
        await db.close()

    print("=" * 80)
    print("HEALTH CHECK COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
