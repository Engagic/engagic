#!/usr/bin/env python3
"""
Restore ALL good quality summaries from backup, including short but useful ones.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
from scripts.summary_quality_checker import SummaryQualityChecker, SummaryQuality

BACKUP_DB = "data/engagic.db.backup-20251028-015213"
CURRENT_DB = "data/engagic.db"


def is_useful_summary(summary: str) -> bool:
    """
    Check if summary is useful even if short.

    A summary is useful if it:
    - Has no error patterns
    - Has actual content (not just processing messages)
    - Has some structure or substance
    """
    if not summary or len(summary) < 50:
        return False

    # Reject error patterns
    error_patterns = [
        "unable to process",
        "error occurred",
        "could not extract",
        "api rate limit",
        "request failed",
        "corrupted",
        "password-protected",
        "timeout",
    ]

    summary_lower = summary.lower()
    if any(pattern in summary_lower for pattern in error_patterns):
        return False

    # Check for substance (actual meeting content words)
    substance_indicators = [
        "agenda", "motion", "vote", "approved", "discussed",
        "council", "board", "committee", "public", "item",
        "budget", "project", "report", "presentation",
        "ordinance", "resolution", "contract", "agreement"
    ]

    has_substance = sum(1 for word in substance_indicators if word in summary_lower) >= 2

    return has_substance


def main():
    print("="*80)
    print("RESTORE ALL USEFUL SUMMARIES FROM BACKUP")
    print("="*80)
    print()

    checker = SummaryQualityChecker()
    backup_conn = sqlite3.connect(BACKUP_DB)
    current_conn = sqlite3.connect(CURRENT_DB)

    # Get all meetings with summaries from backup
    cursor = backup_conn.execute("""
        SELECT id, banana, title, date, packet_url, summary, processing_status
        FROM meetings WHERE summary IS NOT NULL
    """)
    meetings = cursor.fetchall()
    print(f"Backup has {len(meetings)} meetings with summaries")
    print("Checking quality...\n")

    # Filter for good quality + useful short ones
    good_meetings = []
    quality_stats = {}
    short_but_useful = 0

    for meeting in meetings:
        _, _, _, _, _, summary, _ = meeting
        result = checker.check_summary(summary)

        quality_stats[result.quality.value] = quality_stats.get(result.quality.value, 0) + 1

        # Accept GOOD quality
        if result.quality == SummaryQuality.GOOD:
            good_meetings.append(meeting)
        # Also accept too_short if it's actually useful
        elif result.quality == SummaryQuality.TOO_SHORT and is_useful_summary(summary):
            good_meetings.append(meeting)
            short_but_useful += 1

    # Show stats
    print("Quality breakdown:")
    for quality_type, count in sorted(quality_stats.items(), key=lambda x: -x[1]):
        pct = (count / len(meetings) * 100) if meetings else 0
        print(f"  {quality_type:20s}: {count:4d} ({pct:5.1f}%)")

    print("\nRestoring:")
    print(f"  - {len(good_meetings) - short_but_useful} GOOD quality summaries")
    print(f"  - {short_but_useful} short but useful summaries")
    print(f"  = {len(good_meetings)} total\n")

    if not good_meetings:
        print("No useful summaries to restore")
        return

    # Clear current database first (we're re-restoring)
    current_conn.execute("DELETE FROM meetings")
    current_conn.commit()

    # Restore all useful meetings
    for mid, banana, title, date, packet_url, summary, status in good_meetings:
        current_conn.execute("""
            INSERT INTO meetings (banana, title, date, packet_url, summary, processing_status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (banana, title, date, packet_url, summary, status))

    current_conn.commit()

    # Final stats
    cursor = current_conn.execute("SELECT COUNT(*), COUNT(CASE WHEN summary IS NOT NULL THEN 1 END) FROM meetings")
    total, with_summaries = cursor.fetchone()

    print(f"✓ Restored {len(good_meetings)} meetings with useful summaries")
    print("\nCurrent database:")
    print(f"  Total meetings: {total}")
    print(f"  With summaries: {with_summaries}")
    print()

    backup_conn.close()
    current_conn.close()


if __name__ == "__main__":
    main()
