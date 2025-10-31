#!/usr/bin/env python3
"""
Quick health check for all cities.

Shows summary statistics and flags potential issues.
"""

import os
import sys
import sqlite3
from collections import defaultdict
from typing import Dict, List, Tuple

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infocore.config import config

# Confidence: 9/10 - Simple SQL aggregation queries

DB_PATH = config.UNIFIED_DB_PATH


def get_city_stats(conn) -> Dict:
    """Get overall city statistics"""
    cursor = conn.execute("""
        SELECT
            COUNT(*) as total_cities,
            COUNT(DISTINCT vendor) as total_vendors,
            COUNT(CASE WHEN status = 'active' THEN 1 END) as active_cities,
            COUNT(CASE WHEN status != 'active' THEN 1 END) as inactive_cities
        FROM cities
    """)
    row = cursor.fetchone()

    return {
        "total_cities": row[0],
        "total_vendors": row[1],
        "active_cities": row[2],
        "inactive_cities": row[3],
    }


def get_vendor_breakdown(conn) -> List[Tuple[str, int, int]]:
    """Get city and meeting counts by vendor"""
    cursor = conn.execute("""
        SELECT
            c.vendor,
            COUNT(DISTINCT c.banana) as city_count,
            COUNT(m.id) as meeting_count
        FROM cities c
        LEFT JOIN meetings m ON c.banana = m.banana
        GROUP BY c.vendor
        ORDER BY city_count DESC
    """)
    return cursor.fetchall()


def get_cities_with_no_meetings(conn) -> List[Tuple[str, str, str, str]]:
    """Find cities with zero meetings"""
    cursor = conn.execute("""
        SELECT c.banana, c.name, c.state, c.vendor
        FROM cities c
        LEFT JOIN meetings m ON c.banana = m.banana
        WHERE c.status = 'active'
        GROUP BY c.banana
        HAVING COUNT(m.id) = 0
        ORDER BY c.vendor, c.name
    """)
    return cursor.fetchall()


def get_cities_with_most_meetings(conn, limit=10) -> List[Tuple[str, str, str, int]]:
    """Get top cities by meeting count"""
    cursor = conn.execute(
        """
        SELECT c.banana, c.name, c.state, COUNT(m.id) as meeting_count
        FROM cities c
        INNER JOIN meetings m ON c.banana = m.banana
        GROUP BY c.banana
        ORDER BY meeting_count DESC
        LIMIT ?
    """,
        (limit,),
    )
    return cursor.fetchall()


def get_recent_activity(conn) -> List[Tuple[str, str, int]]:
    """Get cities synced recently"""
    cursor = conn.execute("""
        SELECT c.name, c.state, COUNT(m.id) as meetings
        FROM cities c
        INNER JOIN meetings m ON c.banana = m.banana
        WHERE m.created_at > datetime('now', '-7 days')
        GROUP BY c.banana
        ORDER BY meetings DESC
        LIMIT 10
    """)
    return cursor.fetchall()


def get_processing_stats(conn) -> Dict:
    """Get AI processing statistics"""
    cursor = conn.execute("""
        SELECT
            COUNT(*) as total_meetings,
            COUNT(CASE WHEN processing_status = 'completed' THEN 1 END) as completed,
            COUNT(CASE WHEN processing_status = 'pending' THEN 1 END) as pending,
            COUNT(CASE WHEN processing_status = 'failed' THEN 1 END) as failed,
            COUNT(CASE WHEN summary IS NOT NULL THEN 1 END) as with_summaries
        FROM meetings
    """)
    row = cursor.fetchone()

    return {
        "total_meetings": row[0],
        "completed": row[1],
        "pending": row[2],
        "failed": row[3],
        "with_summaries": row[4],
    }


def detect_potential_corruption(conn) -> List[Dict]:
    """Detect potential data corruption issues"""
    issues = []

    # Check for meetings with packet URLs from wrong vendor domains
    cursor = conn.execute("""
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

    for banana, name, vendor, slug, packet_url in cursor:
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


def main():
    print("=" * 80)
    print("ENGAGIC HEALTH CHECK")
    print("=" * 80)
    print()

    conn = sqlite3.connect(DB_PATH)

    # Overall stats
    stats = get_city_stats(conn)
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
    for vendor, city_count, meeting_count in get_vendor_breakdown(conn):
        print(f"{vendor:<20} {city_count:<10} {meeting_count:<10}")
    print()

    # Processing stats
    proc_stats = get_processing_stats(conn)
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
    for banana, name, state, count in get_cities_with_most_meetings(conn):
        print(f"{name}, {state}: {count} meetings")
    print()

    # Cities with no meetings
    no_meetings = get_cities_with_no_meetings(conn)
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
    corruption_issues = detect_potential_corruption(conn)
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
    recent = get_recent_activity(conn)
    if recent:
        for name, state, meetings in recent:
            print(f"{name}, {state}: {meetings} meetings added")
    else:
        print("No recent activity")
    print()

    conn.close()

    print("=" * 80)
    print("HEALTH CHECK COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
