#!/usr/bin/env python3
"""
Deliberation moderation CLI.

Usage:
    python scripts/moderate.py list                 List all pending comments
    python scripts/moderate.py review <delib_id>    Interactive review for one deliberation
    python scripts/moderate.py approve <comment_id> Approve a specific comment
    python scripts/moderate.py reject <comment_id>  Reject a specific comment

Run from project root: python scripts/moderate.py list
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.db_postgres import Database


async def list_all_pending():
    """List all pending comments across all deliberations."""
    db = await Database.create()
    try:
        # Query all pending comments with deliberation context
        async with db.pool.acquire() as conn:
            pending = await conn.fetch(
                """
                SELECT
                    c.id,
                    c.deliberation_id,
                    c.participant_number,
                    c.txt,
                    c.created_at,
                    d.topic,
                    m.matter_file,
                    m.title as matter_title
                FROM deliberation_comments c
                JOIN deliberations d ON d.id = c.deliberation_id
                LEFT JOIN city_matters m ON m.id = d.matter_id
                WHERE c.mod_status = 0
                ORDER BY c.created_at DESC
                """
            )

        if not pending:
            print("\nNo pending comments. Queue is clear.")
            return

        print(f"\n{'='*70}")
        print(f" PENDING COMMENTS: {len(pending)}")
        print(f"{'='*70}\n")

        for row in pending:
            print(f"Comment #{row['id']} | Deliberation: {row['deliberation_id'][:30]}...")
            if row['matter_file']:
                print(f"  Matter: {row['matter_file']} - {row['matter_title'][:50] if row['matter_title'] else 'Untitled'}...")
            print(f"  Participant {row['participant_number']} says:")
            print(f"  \"{row['txt']}\"")
            print(f"  Submitted: {row['created_at']}")
            print()

        print("To review: python scripts/moderate.py review <deliberation_id>")
        print("To approve: python scripts/moderate.py approve <comment_id>")
        print("To reject: python scripts/moderate.py reject <comment_id>")

    finally:
        await db.close()


async def review_deliberation(deliberation_id: str):
    """Interactive review for a single deliberation."""
    db = await Database.create()
    try:
        pending = await db.deliberation.get_pending_comments(deliberation_id)

        if not pending:
            print(f"\nNo pending comments for deliberation {deliberation_id}")
            return

        # Get deliberation context
        delib = await db.deliberation.get_deliberation(deliberation_id)
        if delib:
            print(f"\n{'='*70}")
            print(f" DELIBERATION: {delib.get('topic', 'Untitled')}")
            print(f" {len(pending)} pending comments")
            print(f"{'='*70}")

        print("\nCommands: [a]pprove, [r]eject, [s]kip, [q]uit\n")

        approved = 0
        rejected = 0

        for comment in pending:
            print(f"\n{'-'*50}")
            print(f"Comment #{comment['id']} by Participant {comment['participant_number']}")
            print(f"{'-'*50}")
            print(f"\n  \"{comment['txt']}\"\n")

            while True:
                try:
                    action = input("  Action [a/r/s/q]: ").strip().lower()
                except EOFError:
                    print("\nExiting.")
                    return

                if action == 'a':
                    await db.deliberation.moderate_comment(comment['id'], approve=True)
                    print("  -> APPROVED (user now trusted)")
                    approved += 1
                    break
                elif action == 'r':
                    await db.deliberation.moderate_comment(comment['id'], approve=False)
                    print("  -> REJECTED")
                    rejected += 1
                    break
                elif action == 's':
                    print("  -> Skipped")
                    break
                elif action == 'q':
                    print(f"\nSession: {approved} approved, {rejected} rejected")
                    return
                else:
                    print("  Invalid. Use: a (approve), r (reject), s (skip), q (quit)")

        print(f"\n{'='*50}")
        print(f"Review complete: {approved} approved, {rejected} rejected")
        print(f"{'='*50}")

    finally:
        await db.close()


async def approve_comment(comment_id: int):
    """Approve a specific comment by ID."""
    db = await Database.create()
    try:
        success = await db.deliberation.moderate_comment(comment_id, approve=True)
        if success:
            print(f"Comment #{comment_id} approved. User marked as trusted.")
        else:
            print(f"Failed to approve comment #{comment_id}. May not exist or already moderated.")
    finally:
        await db.close()


async def reject_comment(comment_id: int):
    """Reject a specific comment by ID."""
    db = await Database.create()
    try:
        success = await db.deliberation.moderate_comment(comment_id, approve=False)
        if success:
            print(f"Comment #{comment_id} rejected.")
        else:
            print(f"Failed to reject comment #{comment_id}. May not exist or already moderated.")
    finally:
        await db.close()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "list":
        asyncio.run(list_all_pending())

    elif cmd == "review":
        if len(sys.argv) < 3:
            print("Usage: python scripts/moderate.py review <deliberation_id>")
            sys.exit(1)
        asyncio.run(review_deliberation(sys.argv[2]))

    elif cmd == "approve":
        if len(sys.argv) < 3:
            print("Usage: python scripts/moderate.py approve <comment_id>")
            sys.exit(1)
        asyncio.run(approve_comment(int(sys.argv[2])))

    elif cmd == "reject":
        if len(sys.argv) < 3:
            print("Usage: python scripts/moderate.py reject <comment_id>")
            sys.exit(1)
        asyncio.run(reject_comment(int(sys.argv[2])))

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
