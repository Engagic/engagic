#!/usr/bin/env python3
"""
Fix JSONB Data Migration Issue

Problem: Migration script stored JSON as TEXT strings in JSONB columns
Solution: Re-cast all JSONB columns from TEXT strings to proper JSONB

Usage:
    ENGAGIC_USE_POSTGRES=true python scripts/fix_jsonb_data.py

This script:
1. Checks how many rows need fixing
2. Re-casts TEXT strings to proper JSONB
3. Verifies the fix
4. Reports results
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_postgres import Database
from config import config, get_logger

logger = get_logger(__name__)


async def check_text_strings(db: Database) -> dict:
    """Check how many TEXT strings exist in JSONB columns"""
    async with db.pool.acquire() as conn:
        counts = {}

        # Check meetings.participation
        counts['meetings.participation'] = await conn.fetchval("""
            SELECT COUNT(*) FROM meetings
            WHERE participation IS NOT NULL
              AND jsonb_typeof(participation) IS NULL
        """)

        # Check items.attachments
        counts['items.attachments'] = await conn.fetchval("""
            SELECT COUNT(*) FROM items
            WHERE attachments IS NOT NULL
              AND jsonb_typeof(attachments) IS NULL
        """)

        # Check items.sponsors
        counts['items.sponsors'] = await conn.fetchval("""
            SELECT COUNT(*) FROM items
            WHERE sponsors IS NOT NULL
              AND jsonb_typeof(sponsors) IS NULL
        """)

        # Check city_matters.attachments
        counts['city_matters.attachments'] = await conn.fetchval("""
            SELECT COUNT(*) FROM city_matters
            WHERE attachments IS NOT NULL
              AND jsonb_typeof(attachments) IS NULL
        """)

        # Check city_matters.sponsors
        counts['city_matters.sponsors'] = await conn.fetchval("""
            SELECT COUNT(*) FROM city_matters
            WHERE sponsors IS NOT NULL
              AND jsonb_typeof(sponsors) IS NULL
        """)

        # Check city_matters.metadata
        counts['city_matters.metadata'] = await conn.fetchval("""
            SELECT COUNT(*) FROM city_matters
            WHERE metadata IS NOT NULL
              AND jsonb_typeof(metadata) IS NULL
        """)

        # Check queue.payload
        counts['queue.payload'] = await conn.fetchval("""
            SELECT COUNT(*) FROM queue
            WHERE payload IS NOT NULL
              AND jsonb_typeof(payload) IS NULL
        """)

        # Check queue.processing_metadata
        counts['queue.processing_metadata'] = await conn.fetchval("""
            SELECT COUNT(*) FROM queue
            WHERE processing_metadata IS NOT NULL
              AND jsonb_typeof(processing_metadata) IS NULL
        """)

        return counts


async def fix_jsonb_data(db: Database) -> dict:
    """Re-cast all TEXT strings to proper JSONB"""
    results = {}

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            # Fix meetings.participation
            result = await conn.execute("""
                UPDATE meetings
                SET participation = participation::jsonb
                WHERE participation IS NOT NULL
                  AND jsonb_typeof(participation) IS NULL
            """)
            results['meetings.participation'] = int(result.split()[-1])

            # Fix items.attachments
            result = await conn.execute("""
                UPDATE items
                SET attachments = attachments::jsonb
                WHERE attachments IS NOT NULL
                  AND jsonb_typeof(attachments) IS NULL
            """)
            results['items.attachments'] = int(result.split()[-1])

            # Fix items.sponsors
            result = await conn.execute("""
                UPDATE items
                SET sponsors = sponsors::jsonb
                WHERE sponsors IS NOT NULL
                  AND jsonb_typeof(sponsors) IS NULL
            """)
            results['items.sponsors'] = int(result.split()[-1])

            # Fix city_matters.attachments
            result = await conn.execute("""
                UPDATE city_matters
                SET attachments = attachments::jsonb
                WHERE attachments IS NOT NULL
                  AND jsonb_typeof(attachments) IS NULL
            """)
            results['city_matters.attachments'] = int(result.split()[-1])

            # Fix city_matters.sponsors
            result = await conn.execute("""
                UPDATE city_matters
                SET sponsors = sponsors::jsonb
                WHERE sponsors IS NOT NULL
                  AND jsonb_typeof(sponsors) IS NULL
            """)
            results['city_matters.sponsors'] = int(result.split()[-1])

            # Fix city_matters.metadata
            result = await conn.execute("""
                UPDATE city_matters
                SET metadata = metadata::jsonb
                WHERE metadata IS NOT NULL
                  AND jsonb_typeof(metadata) IS NULL
            """)
            results['city_matters.metadata'] = int(result.split()[-1])

            # Fix queue.payload
            result = await conn.execute("""
                UPDATE queue
                SET payload = payload::jsonb
                WHERE payload IS NOT NULL
                  AND jsonb_typeof(payload) IS NULL
            """)
            results['queue.payload'] = int(result.split()[-1])

            # Fix queue.processing_metadata
            result = await conn.execute("""
                UPDATE queue
                SET processing_metadata = processing_metadata::jsonb
                WHERE processing_metadata IS NOT NULL
                  AND jsonb_typeof(processing_metadata) IS NULL
            """)
            results['queue.processing_metadata'] = int(result.split()[-1])

    return results


async def main():
    """Main execution"""
    print("\n" + "="*80)
    print("JSONB Data Fix Script")
    print("="*80 + "\n")

    # Verify PostgreSQL is enabled
    if not config.USE_POSTGRES:
        print("❌ ENGAGIC_USE_POSTGRES is not set to 'true'")
        print("Set environment variable: export ENGAGIC_USE_POSTGRES=true")
        sys.exit(1)

    # Initialize database
    db = await Database.create()

    try:
        # Step 1: Check current state
        print("Checking for TEXT strings in JSONB columns...")
        before_counts = await check_text_strings(db)

        total_before = sum(before_counts.values())

        if total_before == 0:
            print("\n✅ All JSONB data is already properly formatted!")
            print("No fixes needed.\n")
            sys.exit(0)

        print("\nFound TEXT strings in JSONB columns:")
        for column, count in before_counts.items():
            if count > 0:
                print(f"  {column}: {count} rows")

        print(f"\nTotal rows to fix: {total_before}")

        # Confirm before proceeding
        response = input("\nProceed with fix? (y/N): ")
        if response.lower() != 'y':
            print("Aborted.")
            sys.exit(0)

        # Step 2: Apply fixes
        print("\nApplying fixes...")
        results = await fix_jsonb_data(db)

        total_fixed = sum(results.values())
        print(f"\n✅ Fixed {total_fixed} rows")

        for column, count in results.items():
            if count > 0:
                print(f"  {column}: {count} rows updated")

        # Step 3: Verify
        print("\nVerifying fix...")
        after_counts = await check_text_strings(db)

        total_after = sum(after_counts.values())

        if total_after == 0:
            print("\n✅ ALL JSONB DATA FIXED!")
            print("No TEXT strings remaining in JSONB columns.")
            print("\nNext step: Restart API to clear error logs:")
            print("  systemctl restart engagic-api")
        else:
            print(f"\n⚠️  WARNING: {total_after} TEXT strings still remain:")
            for column, count in after_counts.items():
                if count > 0:
                    print(f"  {column}: {count} rows")
            sys.exit(1)

    finally:
        await db.close()

    print("\n" + "="*80)
    print("Fix complete!")
    print("="*80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
