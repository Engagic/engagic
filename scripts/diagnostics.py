#!/usr/bin/env python3
"""
Database Diagnostics - Orphan Detection and Integrity Checks

Run on VPS to identify orphaned records and data integrity issues.
Results help prioritize cleanup and prevent future orphans.

Usage:
    python scripts/diagnostics.py              # Run all checks
    python scripts/diagnostics.py --fix        # Run with optional cleanup (dry-run first)
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.db_postgres import Database
from config import get_logger

logger = get_logger(__name__).bind(component="diagnostics")


async def check_orphaned_matters(db: Database) -> dict:
    """Find matters with no items referencing them."""
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                cm.id,
                cm.banana,
                cm.matter_file,
                cm.matter_id,
                cm.title,
                cm.canonical_summary IS NOT NULL as has_summary,
                cm.appearance_count,
                cm.created_at
            FROM city_matters cm
            LEFT JOIN items i ON i.matter_id = cm.id
            WHERE i.id IS NULL
            ORDER BY cm.created_at DESC
            LIMIT 100
            """
        )

        orphans = [dict(row) for row in rows]

        # Get total count
        total = await conn.fetchval(
            """
            SELECT COUNT(*) FROM city_matters cm
            LEFT JOIN items i ON i.matter_id = cm.id
            WHERE i.id IS NULL
            """
        )

        return {
            "name": "orphaned_matters",
            "description": "Matters with no items referencing them",
            "count": total,
            "samples": orphans[:10],
            "severity": "HIGH" if total > 0 else "OK"
        }


async def check_orphaned_happening_items(db: Database) -> dict:
    """Find happening_items referencing deleted meetings."""
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT h.*, m.id IS NULL as meeting_missing, i.id IS NULL as item_missing
            FROM happening_items h
            LEFT JOIN meetings m ON m.id = h.meeting_id
            LEFT JOIN items i ON i.id = h.item_id
            WHERE m.id IS NULL OR i.id IS NULL
            LIMIT 100
            """
        )

        orphans = [dict(row) for row in rows]

        total = await conn.fetchval(
            """
            SELECT COUNT(*) FROM happening_items h
            LEFT JOIN meetings m ON m.id = h.meeting_id
            LEFT JOIN items i ON i.id = h.item_id
            WHERE m.id IS NULL OR i.id IS NULL
            """
        )

        return {
            "name": "orphaned_happening_items",
            "description": "Happening items with missing meeting or item references",
            "count": total,
            "samples": orphans[:10],
            "severity": "MEDIUM" if total > 0 else "OK"
        }


async def check_orphaned_queue_jobs(db: Database) -> dict:
    """Find queue jobs referencing deleted meetings."""
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT q.id, q.source_url, q.meeting_id, q.banana, q.job_type,
                   q.status, q.created_at, q.error_message
            FROM queue q
            LEFT JOIN meetings m ON m.id = q.meeting_id
            WHERE m.id IS NULL AND q.meeting_id IS NOT NULL
            LIMIT 100
            """
        )

        orphans = [dict(row) for row in rows]

        total = await conn.fetchval(
            """
            SELECT COUNT(*) FROM queue q
            LEFT JOIN meetings m ON m.id = q.meeting_id
            WHERE m.id IS NULL AND q.meeting_id IS NOT NULL
            """
        )

        return {
            "name": "orphaned_queue_jobs",
            "description": "Queue jobs referencing non-existent meetings",
            "count": total,
            "samples": orphans[:10],
            "severity": "HIGH" if total > 0 else "OK"
        }


async def check_summary_desync(db: Database) -> dict:
    """Find items with summaries where matter has no canonical_summary."""
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                i.id as item_id,
                i.matter_id,
                i.title,
                LEFT(i.summary, 100) as item_summary_preview,
                cm.canonical_summary IS NULL as matter_missing_summary
            FROM items i
            JOIN city_matters cm ON cm.id = i.matter_id
            WHERE i.summary IS NOT NULL AND cm.canonical_summary IS NULL
            LIMIT 100
            """
        )

        desynced = [dict(row) for row in rows]

        total = await conn.fetchval(
            """
            SELECT COUNT(*) FROM items i
            JOIN city_matters cm ON cm.id = i.matter_id
            WHERE i.summary IS NOT NULL AND cm.canonical_summary IS NULL
            """
        )

        return {
            "name": "summary_desync",
            "description": "Items have summary but matter lacks canonical_summary",
            "count": total,
            "samples": desynced[:10],
            "severity": "MEDIUM" if total > 0 else "OK"
        }


async def check_duplicate_matters_by_file(db: Database) -> dict:
    """Find potential duplicate matters (same matter_file, different IDs)."""
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                cm.banana,
                cm.matter_file,
                COUNT(*) as duplicate_count,
                array_agg(cm.id) as matter_ids
            FROM city_matters cm
            WHERE cm.matter_file IS NOT NULL
            GROUP BY cm.banana, cm.matter_file
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC
            LIMIT 50
            """
        )

        duplicates = [dict(row) for row in rows]

        total = len(duplicates)

        return {
            "name": "duplicate_matters_by_file",
            "description": "Same matter_file appearing with different IDs (ID drift)",
            "count": total,
            "samples": duplicates[:10],
            "severity": "CRITICAL" if total > 0 else "OK"
        }


async def check_items_missing_meetings(db: Database) -> dict:
    """Find items whose meeting_id doesn't exist (should never happen with FK)."""
    async with db.pool.acquire() as conn:
        # This should always be 0 due to FK constraint, but check anyway
        total = await conn.fetchval(
            """
            SELECT COUNT(*) FROM items i
            LEFT JOIN meetings m ON m.id = i.meeting_id
            WHERE m.id IS NULL
            """
        )

        return {
            "name": "items_missing_meetings",
            "description": "Items referencing non-existent meetings (FK violation)",
            "count": total,
            "samples": [],
            "severity": "CRITICAL" if total > 0 else "OK"
        }


async def check_matter_appearances_integrity(db: Database) -> dict:
    """Check matter_appearances for broken references."""
    async with db.pool.acquire() as conn:
        broken_matters = await conn.fetchval(
            """
            SELECT COUNT(*) FROM matter_appearances ma
            LEFT JOIN city_matters cm ON cm.id = ma.matter_id
            WHERE cm.id IS NULL
            """
        )

        broken_meetings = await conn.fetchval(
            """
            SELECT COUNT(*) FROM matter_appearances ma
            LEFT JOIN meetings m ON m.id = ma.meeting_id
            WHERE m.id IS NULL
            """
        )

        broken_items = await conn.fetchval(
            """
            SELECT COUNT(*) FROM matter_appearances ma
            LEFT JOIN items i ON i.id = ma.item_id
            WHERE i.id IS NULL
            """
        )

        total = broken_matters + broken_meetings + broken_items

        return {
            "name": "matter_appearances_integrity",
            "description": "Matter appearances with broken FK references",
            "count": total,
            "details": {
                "broken_matter_refs": broken_matters,
                "broken_meeting_refs": broken_meetings,
                "broken_item_refs": broken_items
            },
            "severity": "HIGH" if total > 0 else "OK"
        }


async def check_alert_matches_integrity(db: Database) -> dict:
    """Check alert_matches for orphaned alerts."""
    async with db.pool.acquire() as conn:
        orphaned = await conn.fetchval(
            """
            SELECT COUNT(*) FROM userland.alert_matches am
            LEFT JOIN userland.alerts a ON a.id = am.alert_id
            WHERE a.id IS NULL
            """
        )

        return {
            "name": "orphaned_alert_matches",
            "description": "Alert matches referencing deleted alerts",
            "count": orphaned,
            "samples": [],
            "severity": "MEDIUM" if orphaned > 0 else "OK"
        }


async def get_database_stats(db: Database) -> dict:
    """Get overall database statistics for context."""
    async with db.pool.acquire() as conn:
        stats = {}

        for table in ["cities", "meetings", "items", "city_matters", "queue", "happening_items"]:
            count = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
            stats[table] = count

        # Userland tables
        for table in ["users", "alerts", "alert_matches"]:
            count = await conn.fetchval(f"SELECT COUNT(*) FROM userland.{table}")
            stats[f"userland.{table}"] = count

        return stats


async def run_all_checks(db: Database) -> list:
    """Run all diagnostic checks and return results."""
    checks = [
        check_orphaned_matters,
        check_orphaned_happening_items,
        check_orphaned_queue_jobs,
        check_summary_desync,
        check_duplicate_matters_by_file,
        check_items_missing_meetings,
        check_matter_appearances_integrity,
        check_alert_matches_integrity,
    ]

    results = []
    for check in checks:
        try:
            result = await check(db)
            results.append(result)
            logger.info(
                "check_completed",
                check=result["name"],
                count=result["count"],
                severity=result["severity"]
            )
        except Exception as e:
            logger.error("check_failed", check=check.__name__, error=str(e))
            results.append({
                "name": check.__name__,
                "error": str(e),
                "severity": "ERROR"
            })

    return results


def print_report(results: list, stats: dict):
    """Print formatted diagnostic report."""
    print("\n" + "=" * 70)
    print("DATABASE DIAGNOSTICS REPORT")
    print("=" * 70)

    print("\n--- Database Statistics ---")
    for table, count in sorted(stats.items()):
        print(f"  {table}: {count:,}")

    print("\n--- Integrity Checks ---")

    critical = []
    high = []
    medium = []
    ok = []
    errors = []

    for result in results:
        severity = result.get("severity", "UNKNOWN")
        if severity == "CRITICAL":
            critical.append(result)
        elif severity == "HIGH":
            high.append(result)
        elif severity == "MEDIUM":
            medium.append(result)
        elif severity == "OK":
            ok.append(result)
        else:
            errors.append(result)

    def print_result(result):
        name = result.get("name", "unknown")
        desc = result.get("description", "")
        count = result.get("count", 0)
        severity = result.get("severity", "UNKNOWN")

        icon = {"CRITICAL": "[X]", "HIGH": "[!]", "MEDIUM": "[~]", "OK": "[v]", "ERROR": "[?]"}.get(severity, "[?]")

        print(f"\n  {icon} {name}")
        print(f"      {desc}")
        print(f"      Count: {count:,} | Severity: {severity}")

        if result.get("details"):
            for k, v in result["details"].items():
                print(f"        - {k}: {v}")

        if result.get("samples") and count > 0:
            print(f"      Samples (first {len(result['samples'])}):")
            for sample in result["samples"][:3]:
                # Truncate long values
                sample_str = str(sample)
                if len(sample_str) > 120:
                    sample_str = sample_str[:117] + "..."
                print(f"        {sample_str}")

        if result.get("error"):
            print(f"      ERROR: {result['error']}")

    if critical:
        print("\n  CRITICAL ISSUES:")
        for r in critical:
            print_result(r)

    if high:
        print("\n  HIGH PRIORITY:")
        for r in high:
            print_result(r)

    if medium:
        print("\n  MEDIUM PRIORITY:")
        for r in medium:
            print_result(r)

    if errors:
        print("\n  ERRORS:")
        for r in errors:
            print_result(r)

    print("\n  PASSED:")
    for r in ok:
        print(f"    [v] {r.get('name')}")

    # Summary
    total_issues = sum(r.get("count", 0) for r in results if r.get("severity") not in ("OK", "ERROR"))

    print("\n" + "=" * 70)
    print(f"SUMMARY: {len(critical)} critical, {len(high)} high, {len(medium)} medium, {len(ok)} ok")
    print(f"TOTAL ISSUES: {total_issues:,}")
    print("=" * 70 + "\n")


async def main():
    """Run diagnostics."""
    import argparse

    parser = argparse.ArgumentParser(description="Database diagnostics")
    parser.add_argument("--fix", action="store_true", help="Attempt to fix issues (dry-run first)")
    args = parser.parse_args()

    logger.info("starting database diagnostics")

    db = await Database.create()

    try:
        stats = await get_database_stats(db)
        results = await run_all_checks(db)
        print_report(results, stats)

        if args.fix:
            print("\n[--fix mode not yet implemented. Review results first.]\n")

    finally:
        await db.pool.close()


if __name__ == "__main__":
    asyncio.run(main())
