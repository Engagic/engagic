#!/usr/bin/env python3
"""Reset processing queue - clear pending items for fresh processing runs

Use cases:
- Changed processing logic and need to requeue everything
- Want to clear stuck/failed jobs
- Need queue hygiene after pipeline changes
"""

import argparse
import sqlite3
from typing import Dict, Any


def get_queue_stats(db_path: str) -> Dict[str, Any]:
    """Get current queue statistics"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Overall status counts
    cursor.execute("SELECT status, COUNT(*) FROM queue GROUP BY status")
    status_counts = dict(cursor.fetchall())

    # Breakdown by city and status
    cursor.execute("""
        SELECT
            c.name,
            q.status,
            COUNT(*) as count
        FROM queue q
        JOIN cities c ON q.banana = c.banana
        GROUP BY c.banana, q.status
        ORDER BY c.name, q.status
    """)

    city_breakdown = {}
    for city, status, count in cursor.fetchall():
        if city not in city_breakdown:
            city_breakdown[city] = {}
        city_breakdown[city][status] = count

    conn.close()

    return {
        'status_counts': status_counts,
        'city_breakdown': city_breakdown,
        'total': sum(status_counts.values())
    }


def reset_queue(db_path: str, status: str = None) -> int:
    """Delete queue items by status

    Args:
        db_path: Path to database
        status: Status to delete (pending, completed, failed). If None, delete all.

    Returns:
        Number of items deleted
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if status:
        cursor.execute("DELETE FROM queue WHERE status = ?", (status,))
    else:
        cursor.execute("DELETE FROM queue")

    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    return deleted


def main():
    parser = argparse.ArgumentParser(
        description="Manage processing queue - view stats or reset"
    )
    parser.add_argument(
        '--db',
        default='/root/engagic/data/engagic.db',
        help='Path to database (default: /root/engagic/data/engagic.db)'
    )
    parser.add_argument(
        '--stats',
        action='store_true',
        help='Show queue statistics (default action)'
    )
    parser.add_argument(
        '--reset',
        choices=['pending', 'completed', 'failed', 'all'],
        help='Delete queue items by status'
    )
    parser.add_argument(
        '--confirm',
        action='store_true',
        help='Required for --reset operations'
    )

    args = parser.parse_args()

    # Default to stats if no action specified
    if not args.reset:
        args.stats = True

    # Show stats
    if args.stats:
        stats = get_queue_stats(args.db)

        print("=" * 80)
        print("QUEUE STATISTICS")
        print("=" * 80)
        print()

        print("Overall Status:")
        print("-" * 40)
        for status, count in sorted(stats['status_counts'].items()):
            print(f"  {status:<15} {count:>6}")
        print(f"  {'TOTAL':<15} {stats['total']:>6}")
        print()

        print("Breakdown by City:")
        print("-" * 80)
        print(f"{'City':<25} {'Pending':<10} {'Completed':<12} {'Failed':<10}")
        print("-" * 80)

        for city in sorted(stats['city_breakdown'].keys()):
            city_stats = stats['city_breakdown'][city]
            pending = city_stats.get('pending', 0)
            completed = city_stats.get('completed', 0)
            failed = city_stats.get('failed', 0)
            print(f"{city:<25} {pending:<10} {completed:<12} {failed:<10}")

        print("=" * 80)

    # Reset queue
    if args.reset:
        if not args.confirm:
            print()
            print("ERROR: --reset requires --confirm flag")
            print()
            stats = get_queue_stats(args.db)
            status_to_delete = args.reset if args.reset != 'all' else None

            if status_to_delete:
                count = stats['status_counts'].get(status_to_delete, 0)
                print(f"Would delete {count} items with status '{status_to_delete}'")
            else:
                print(f"Would delete ALL {stats['total']} items from queue")

            print()
            print("Re-run with --confirm to proceed:")
            print(f"  python scripts/reset_queue.py --reset {args.reset} --confirm")
            print()
            return 1

        # Perform deletion
        status_to_delete = None if args.reset == 'all' else args.reset
        deleted = reset_queue(args.db, status_to_delete)

        print()
        print(f"Deleted {deleted} items from queue")
        print()

        # Show new stats
        new_stats = get_queue_stats(args.db)
        print(f"Remaining items: {new_stats['total']}")
        print()

    return 0


if __name__ == '__main__':
    exit(main())
