#!/usr/bin/env python3
"""Reset processing queue - clear pending items for fresh processing runs

PostgreSQL version - uses async database

Use cases:
- Changed processing logic and need to requeue everything
- Want to clear stuck/failed jobs
- Need queue hygiene after pipeline changes
"""

import argparse
import asyncio
import sys
import os
from typing import Dict, Any, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.db_postgres import Database
from config import config


async def get_queue_stats_async(db: Database) -> Dict[str, Any]:
    """Get current queue statistics"""
    stats = await db.queue.get_queue_stats()

    # Get city breakdown
    async with db.pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                c.name,
                q.status,
                COUNT(*) as count
            FROM queue q
            JOIN cities c ON q.banana = c.banana
            GROUP BY c.name, q.status
            ORDER BY c.name, q.status
        """)

    city_breakdown = {}
    for row in rows:
        city = row['name']
        status = row['status']
        count = row['count']
        if city not in city_breakdown:
            city_breakdown[city] = {}
        city_breakdown[city][status] = count

    return {
        'status_counts': {
            'pending': stats.get('pending_count', 0),
            'processing': stats.get('processing_count', 0),
            'completed': stats.get('completed_count', 0),
            'failed': stats.get('failed_count', 0),
            'dead_letter': stats.get('dead_letter_count', 0),
        },
        'city_breakdown': city_breakdown,
        'total': sum([
            stats.get('pending_count', 0),
            stats.get('processing_count', 0),
            stats.get('completed_count', 0),
            stats.get('failed_count', 0),
            stats.get('dead_letter_count', 0),
        ])
    }


async def reset_queue_async(db: Database, status: Optional[str] = None) -> int:
    """Delete queue items by status

    Args:
        db: Database instance
        status: Status to delete (pending, completed, failed, dead_letter). If None, delete all.

    Returns:
        Number of items deleted
    """
    async with db.pool.acquire() as conn:
        if status:
            result = await conn.execute(
                "DELETE FROM queue WHERE status = $1",
                status
            )
        else:
            result = await conn.execute("DELETE FROM queue")

    # Parse result like "DELETE 42" -> 42
    deleted = int(result.split()[-1]) if result else 0
    return deleted


def get_queue_stats(dsn: Optional[str] = None) -> Dict[str, Any]:
    """Sync wrapper for get_queue_stats_async"""
    async def _run():
        db = await Database.create(dsn or config.get_postgres_dsn())
        try:
            return await get_queue_stats_async(db)
        finally:
            await db.close()

    return asyncio.run(_run())


def reset_queue(dsn: Optional[str] = None, status: Optional[str] = None) -> int:
    """Sync wrapper for reset_queue_async"""
    async def _run():
        db = await Database.create(dsn or config.get_postgres_dsn())
        try:
            return await reset_queue_async(db, status)
        finally:
            await db.close()

    return asyncio.run(_run())


def main():
    parser = argparse.ArgumentParser(
        description="Manage processing queue - view stats or reset"
    )
    parser.add_argument(
        "--dsn",
        help="PostgreSQL DSN (defaults to config)",
        default=None,
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show queue statistics",
    )
    parser.add_argument(
        "--reset",
        choices=["pending", "completed", "failed", "dead_letter", "all"],
        help="Reset queue items by status",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt",
    )

    args = parser.parse_args()

    if args.stats:
        # Show statistics
        stats = get_queue_stats(args.dsn)

        print("\n=== Queue Statistics ===")
        print(f"Total items: {stats['total']}")
        print("\nBy status:")
        for status, count in stats['status_counts'].items():
            if count > 0:
                print(f"  {status:12} {count:6}")

        if stats['city_breakdown']:
            print("\nBy city:")
            for city, status_counts in stats['city_breakdown'].items():
                total_city = sum(status_counts.values())
                print(f"\n  {city} ({total_city} items):")
                for status, count in status_counts.items():
                    print(f"    {status:12} {count:6}")

        return

    if args.reset:
        # Reset queue
        status = None if args.reset == "all" else args.reset

        # Get current stats
        stats = get_queue_stats(args.dsn)

        if status:
            count_to_delete = stats['status_counts'].get(status, 0)
            status_msg = f"'{status}' items"
        else:
            count_to_delete = stats['total']
            status_msg = "ALL items"

        if count_to_delete == 0:
            print(f"No {status_msg} to delete.")
            return

        # Confirmation
        if not args.yes:
            response = input(f"Delete {count_to_delete} {status_msg}? (yes/no): ")
            if response.lower() != "yes":
                print("Cancelled.")
                return

        # Execute reset
        deleted = reset_queue(args.dsn, status)
        print(f"Deleted {deleted} queue items")
        return

    # No action specified
    parser.print_help()


if __name__ == "__main__":
    main()
