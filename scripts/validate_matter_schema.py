#!/usr/bin/env python3
"""
Validate Matter Tracking Schema - Post-Fix Verification

Checks that matter tracking architecture is properly configured:
1. All required tables exist
2. FK constraints are in place
3. Indices created correctly
4. Sample data validates properly

Run after database creation or migration to verify schema integrity.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import ENGAGIC_UNIFIED_DB
from database.db import UnifiedDatabase
from database.id_generation import generate_matter_id, validate_matter_id


def validate_schema(db_path: str) -> bool:
    """
    Validate matter tracking schema integrity.

    Returns:
        True if all checks pass, False otherwise
    """
    print(f"Validating schema at {db_path}")
    print("=" * 60)

    try:
        db = UnifiedDatabase(db_path)
        conn = db.conn
        all_passed = True

        # Check 1: Required tables exist
        print("\n✓ Check 1: Required Tables")
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cursor.fetchall()]

        required_tables = ['cities', 'meetings', 'items', 'city_matters', 'matter_appearances']
        for table in required_tables:
            if table in tables:
                print(f"  ✓ {table}")
            else:
                print(f"  ✗ {table} MISSING")
                all_passed = False

        # Check 2: FK constraints on items table
        print("\n✓ Check 2: Foreign Key Constraints")
        cursor = conn.execute("PRAGMA foreign_key_list(items)")
        fks = cursor.fetchall()

        # Expected FKs: meeting_id → meetings, matter_id → city_matters
        fk_targets = {fk[2]: fk[3] for fk in fks}  # {table: column}

        if fk_targets.get('meetings') == 'id':
            print("  ✓ items.meeting_id → meetings.id")
        else:
            print("  ✗ items.meeting_id FK MISSING")
            all_passed = False

        if fk_targets.get('city_matters') == 'id':
            print("  ✓ items.matter_id → city_matters.id")
        else:
            print("  ✗ items.matter_id FK MISSING")
            all_passed = False

        # Check 3: Matter table indices
        print("\n✓ Check 3: Matter Indices")
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' ORDER BY name")
        indices = [row[0] for row in cursor.fetchall()]

        required_indices = [
            'idx_city_matters_banana',
            'idx_city_matters_matter_file',
            'idx_matter_appearances_matter',
            'idx_matter_appearances_meeting',
            'idx_matter_appearances_item',
        ]

        for index in required_indices:
            if index in indices:
                print(f"  ✓ {index}")
            else:
                print(f"  ✗ {index} MISSING")
                all_passed = False

        # Check 4: ID generation and validation
        print("\n✓ Check 4: ID Generation & Validation")

        # Test deterministic generation
        test_id_1 = generate_matter_id("testCA", matter_file="BL2025-1098")
        test_id_2 = generate_matter_id("testCA", matter_file="BL2025-1098")

        if test_id_1 == test_id_2:
            print(f"  ✓ Deterministic hashing: {test_id_1}")
        else:
            print(f"  ✗ Hash mismatch: {test_id_1} != {test_id_2}")
            all_passed = False

        # Test format validation
        if validate_matter_id(test_id_1):
            print("  ✓ Valid format")
        else:
            print("  ✗ Invalid format")
            all_passed = False

        # Test invalid formats
        invalid_ids = ["raw_uuid", "no_underscore", "testCA_TOOSHORT", "testCA_not-hex-chars"]
        for invalid_id in invalid_ids:
            if not validate_matter_id(invalid_id):
                print(f"  ✓ Rejected invalid: {invalid_id}")
            else:
                print(f"  ✗ Accepted invalid: {invalid_id}")
                all_passed = False

        # Check 5: Data integrity (if data exists)
        print("\n✓ Check 5: Data Integrity")
        cursor = conn.execute("SELECT COUNT(*) FROM items WHERE matter_id IS NOT NULL")
        items_with_matters = cursor.fetchone()[0]

        if items_with_matters > 0:
            # Check for orphaned items
            cursor = conn.execute("""
                SELECT COUNT(*) FROM items i
                WHERE i.matter_id IS NOT NULL
                  AND NOT EXISTS (SELECT 1 FROM city_matters cm WHERE cm.id = i.matter_id)
            """)
            orphaned = cursor.fetchone()[0]

            if orphaned == 0:
                print(f"  ✓ No orphaned items ({items_with_matters} items with matters)")
            else:
                print(f"  ✗ {orphaned} orphaned items (out of {items_with_matters})")
                all_passed = False

            # Check ID format in actual data
            cursor = conn.execute("SELECT DISTINCT matter_id FROM items WHERE matter_id IS NOT NULL LIMIT 10")
            sample_ids = [row[0] for row in cursor.fetchall()]

            format_valid = all(validate_matter_id(mid) for mid in sample_ids)
            if format_valid:
                print("  ✓ All matter_ids use composite hash format")
            else:
                print("  ✗ Some matter_ids have invalid format")
                all_passed = False
        else:
            print("  ⚠ No items with matters yet (fresh database)")

        # Summary
        print("\n" + "=" * 60)
        if all_passed:
            print("✓ ALL CHECKS PASSED - Schema is correct")
            return True
        else:
            print("✗ SOME CHECKS FAILED - Review errors above")
            return False

    except Exception as e:
        print(f"\n✗ VALIDATION ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    db_path = ENGAGIC_UNIFIED_DB

    if len(sys.argv) > 1:
        db_path = sys.argv[1]

    success = validate_schema(db_path)
    sys.exit(0 if success else 1)
