#!/usr/bin/env python3
"""
Nuke Queue - Clear all items from processing queue

DANGER: This deletes ALL queue items (pending, processing, completed, failed).
Use when you want to start fresh or clear out duplicates.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.db import UnifiedDatabase
from config import config


def nuke_queue():
    """Clear entire processing queue and show what was cleared"""
    db = UnifiedDatabase(config.UNIFIED_DB_PATH)

    print("\nDanger Zone: Nuking Processing Queue")
    print("=" * 50)

    # Get current stats
    stats = db.get_queue_stats()
    print("\nCurrent queue status:")
    print(f"  Pending:    {stats.get('pending_count', 0)}")
    print(f"  Processing: {stats.get('processing_count', 0)}")
    print(f"  Completed:  {stats.get('completed_count', 0)}")
    print(f"  Failed:     {stats.get('failed_count', 0)}")

    total = sum([
        stats.get('pending_count', 0),
        stats.get('processing_count', 0),
        stats.get('completed_count', 0),
        stats.get('failed_count', 0),
    ])

    if total == 0:
        print("\nQueue is already empty. Nothing to do.")
        return

    # Confirm
    print(f"\nThis will DELETE {total} queue items.")
    confirm = input("Type 'yes' to confirm: ")

    if confirm.lower() != 'yes':
        print("Aborted.")
        return

    # Nuke it
    cleared = db.clear_queue()
    print(f"\nCleared {sum(cleared.values())} items:")
    for status, count in cleared.items():
        if count > 0:
            print(f"  {status}: {count}")

    print("\nQueue nuked successfully.")
    db.close()


if __name__ == "__main__":
    nuke_queue()
