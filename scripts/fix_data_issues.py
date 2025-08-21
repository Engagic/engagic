#!/usr/bin/env python3
"""
Fix critical data issues in engagic databases
"""

import sys
import os
import sqlite3
import re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.core.config import Config


def fix_duplicate_city_slugs():
    """Fix duplicate city_slugs by making them unique"""
    config = Config()
    conn = sqlite3.connect(config.LOCATIONS_DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("\n=== FIXING DUPLICATE CITY_SLUGS ===")
    
    # Find all duplicate city_slugs
    cursor.execute("""
        SELECT city_slug, COUNT(*) as count, GROUP_CONCAT(id) as ids,
               GROUP_CONCAT(city_name || ',' || state) as cities
        FROM cities
        WHERE city_slug IS NOT NULL
        GROUP BY city_slug
        HAVING count > 1
        ORDER BY count DESC
    """)
    
    duplicates = cursor.fetchall()
    total_fixed = 0
    
    for dup in duplicates:
        city_slug = dup['city_slug']
        ids = dup['ids'].split(',')
        
        print(f"\nFixing '{city_slug}' used by {dup['count']} cities")
        
        # For each duplicate, create a unique slug
        for i, (city_id, city_info) in enumerate(zip(ids, dup['cities'].split(','))):
            if ',' in city_info:
                parts = city_info.rsplit(',', 1)
                city_name = parts[0]
                state = parts[1] if len(parts) > 1 else ''
            else:
                city_name = city_info
                state = ''
            
            if i == 0:
                # Keep first one as-is if it matches the pattern
                if state and city_slug.endswith(state.lower()):
                    print(f"  Keeping: {city_name}, {state} -> {city_slug}")
                    continue
            
            # Generate new unique slug
            # Remove special characters and spaces, append state
            base_slug = re.sub(r'[^a-zA-Z0-9]', '', city_name).lower()
            new_slug = f"{base_slug}-{state.lower()}" if state else base_slug
            
            # Make sure it's unique
            cursor.execute("SELECT COUNT(*) FROM cities WHERE city_slug = ?", (new_slug,))
            if cursor.fetchone()[0] > 0:
                # Add a number suffix if needed
                for suffix in range(2, 100):
                    test_slug = f"{new_slug}{suffix}"
                    cursor.execute("SELECT COUNT(*) FROM cities WHERE city_slug = ?", (test_slug,))
                    if cursor.fetchone()[0] == 0:
                        new_slug = test_slug
                        break
            
            print(f"  Updating: {city_name}, {state} -> {new_slug}")
            cursor.execute(
                "UPDATE cities SET city_slug = ? WHERE id = ?",
                (new_slug, city_id)
            )
            total_fixed += 1
    
    conn.commit()
    print(f"\nFixed {total_fixed} duplicate city_slugs")
    conn.close()
    return total_fixed


def fix_wrong_city_slug_patterns():
    """Fix city_slugs that have wrong patterns like 'miamifl' or 'austintexas'"""
    config = Config()
    conn = sqlite3.connect(config.LOCATIONS_DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("\n=== FIXING WRONG CITY_SLUG PATTERNS ===")
    
    # Fix slugs that end with state names
    wrong_patterns = [
        ('florida', 'fl'),
        ('texas', 'tx'),
        ('california', 'ca'),
        ('newyork', 'ny'),
        ('ohio', 'oh'),
        ('illinois', 'il')
    ]
    
    total_fixed = 0
    
    for state_name, state_code in wrong_patterns:
        cursor.execute(
            "SELECT id, city_name, state, city_slug FROM cities WHERE city_slug LIKE ?",
            (f'%{state_name}',)
        )
        cities = cursor.fetchall()
        
        for city in cities:
            # Generate correct slug
            base_slug = re.sub(r'[^a-zA-Z0-9]', '', city['city_name']).lower()
            new_slug = f"{base_slug}-{city['state'].lower()}"
            
            # Check uniqueness
            cursor.execute("SELECT COUNT(*) FROM cities WHERE city_slug = ? AND id != ?", 
                         (new_slug, city['id']))
            if cursor.fetchone()[0] > 0:
                for suffix in range(2, 100):
                    test_slug = f"{new_slug}{suffix}"
                    cursor.execute("SELECT COUNT(*) FROM cities WHERE city_slug = ?", (test_slug,))
                    if cursor.fetchone()[0] == 0:
                        new_slug = test_slug
                        break
            
            print(f"  {city['city_name']}, {city['state']}: '{city['city_slug']}' -> '{new_slug}'")
            cursor.execute("UPDATE cities SET city_slug = ? WHERE id = ?", (new_slug, city['id']))
            total_fixed += 1
    
    # Fix specific wrong patterns
    specific_fixes = [
        ('tampabaywater', 'tampa-fl'),
        ('miamifl', 'miami-fl'),
        ('palmbayflorida', None),  # Will generate unique ones
        ('springfieldohio', None),  # Will generate unique ones
    ]
    
    for old_slug, new_slug in specific_fixes:
        cursor.execute(
            "SELECT id, city_name, state FROM cities WHERE city_slug = ?",
            (old_slug,)
        )
        cities = cursor.fetchall()
        
        for i, city in enumerate(cities):
            if new_slug is None:
                # Generate unique slug
                base_slug = re.sub(r'[^a-zA-Z0-9]', '', city['city_name']).lower()
                final_slug = f"{base_slug}-{city['state'].lower()}"
            else:
                final_slug = new_slug if i == 0 else f"{new_slug}{i+1}"
            
            # Check uniqueness
            cursor.execute("SELECT COUNT(*) FROM cities WHERE city_slug = ? AND id != ?", 
                         (final_slug, city['id']))
            if cursor.fetchone()[0] > 0:
                for suffix in range(2, 100):
                    test_slug = f"{final_slug}{suffix}"
                    cursor.execute("SELECT COUNT(*) FROM cities WHERE city_slug = ?", (test_slug,))
                    if cursor.fetchone()[0] == 0:
                        final_slug = test_slug
                        break
            
            print(f"  {city['city_name']}, {city['state']}: '{old_slug}' -> '{final_slug}'")
            cursor.execute("UPDATE cities SET city_slug = ? WHERE id = ?", (final_slug, city['id']))
            total_fixed += 1
    
    conn.commit()
    print(f"\nFixed {total_fixed} wrong city_slug patterns")
    conn.close()
    return total_fixed


def fix_invalid_meeting_dates():
    """Fix invalid meeting dates"""
    config = Config()
    conn = sqlite3.connect(config.MEETINGS_DB_PATH)
    cursor = conn.cursor()
    
    print("\n=== FIXING INVALID MEETING DATES ===")
    
    # Set invalid dates to NULL so they can be re-fetched
    cursor.execute("""
        UPDATE meetings 
        SET meeting_date = NULL 
        WHERE meeting_date LIKE '%In Progress%' 
           OR meeting_date LIKE '%Windows Media Player%'
           OR meeting_date LIKE '9999%' 
           OR meeting_date > '2026-12-31'
    """)
    
    fixed_count = cursor.rowcount
    conn.commit()
    
    print(f"Set {fixed_count} invalid meeting dates to NULL (will be re-fetched)")
    conn.close()
    return fixed_count


def clean_garbage_city_requests():
    """Remove garbage city requests from analytics"""
    config = Config()
    conn = sqlite3.connect(config.ANALYTICS_DB_PATH)
    cursor = conn.cursor()
    
    print("\n=== CLEANING GARBAGE CITY REQUESTS ===")
    
    # Delete obvious garbage
    garbage_patterns = [
        "state = 'UNKNOWN'",
        "LENGTH(city_name) < 3",
        "city_name IN ('Hello', 'Oops', 'Test', 'test')",
        "city_name LIKE '%[0-9]%'",
        "city_name LIKE 'Akkeb%'",
        "city_name = 'Ca'",
        "city_name = 'Carmelin'",
        "city_name = 'Massachusets'",
        "city_name = 'California'",
        "city_name = 'Last Vegas'",
        "city_name LIKE '%oops%'",
    ]
    
    total_deleted = 0
    for pattern in garbage_patterns:
        cursor.execute(f"DELETE FROM city_requests WHERE {pattern}")
        deleted = cursor.rowcount
        if deleted > 0:
            print(f"  Deleted {deleted} requests matching: {pattern}")
            total_deleted += deleted
    
    # Fix misspellings
    fixes = [
        ("UPDATE city_requests SET city_name = 'Somerville' WHERE city_name = 'Sommerville'", "Sommerville -> Somerville"),
        ("UPDATE city_requests SET city_name = 'Las Vegas' WHERE city_name = 'Last Vegas'", "Last Vegas -> Las Vegas"),
        ("UPDATE city_requests SET city_name = 'Lynnwood' WHERE city_name LIKE 'Lynnw%'", "Lynnwood variations"),
        ("UPDATE city_requests SET city_name = 'Apple Valley', state = 'CA' WHERE city_name LIKE 'Applevalley%'", "Applevalleyca -> Apple Valley, CA"),
        ("UPDATE city_requests SET city_name = 'Clovis', state = 'CA' WHERE city_name = 'Clovisca'", "Clovisca -> Clovis, CA"),
        ("UPDATE city_requests SET state = 'NY' WHERE city_name = 'New York City' AND state = 'UNKNOWN'", "New York City state"),
    ]
    
    for query, description in fixes:
        cursor.execute(query)
        if cursor.rowcount > 0:
            print(f"  Fixed {cursor.rowcount}: {description}")
    
    conn.commit()
    print(f"\nCleaned {total_deleted} garbage city requests")
    conn.close()
    return total_deleted


def verify_fixes():
    """Verify all fixes were applied correctly"""
    config = Config()
    
    print("\n=== VERIFYING FIXES ===")
    
    # Check for remaining duplicate city_slugs
    conn = sqlite3.connect(config.LOCATIONS_DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT city_slug, COUNT(*) as count
        FROM cities
        WHERE city_slug IS NOT NULL
        GROUP BY city_slug
        HAVING count > 1
    """)
    
    duplicates = cursor.fetchall()
    if duplicates:
        print(f"⚠️  Still have {len(duplicates)} duplicate city_slugs!")
        for dup in duplicates[:5]:
            print(f"    {dup[0]}: {dup[1]} cities")
    else:
        print("✓ No duplicate city_slugs")
    
    # Check for wrong patterns
    cursor.execute("""
        SELECT COUNT(*) FROM cities 
        WHERE city_slug LIKE '%florida' 
           OR city_slug LIKE '%texas'
           OR city_slug LIKE '%california'
           OR city_slug = 'tampabaywater'
           OR city_slug = 'miamifl'
    """)
    
    wrong_count = cursor.fetchone()[0]
    if wrong_count > 0:
        print(f"⚠️  Still have {wrong_count} cities with wrong slug patterns")
    else:
        print("✓ No wrong city_slug patterns")
    
    conn.close()
    
    # Check for invalid meeting dates
    conn = sqlite3.connect(config.MEETINGS_DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT COUNT(*) FROM meetings 
        WHERE meeting_date LIKE '%In Progress%' 
           OR meeting_date LIKE '9999%' 
           OR meeting_date > '2026-12-31'
    """)
    
    invalid_dates = cursor.fetchone()[0]
    if invalid_dates > 0:
        print(f"⚠️  Still have {invalid_dates} invalid meeting dates")
    else:
        print("✓ No invalid meeting dates")
    
    conn.close()
    
    # Check garbage city requests
    conn = sqlite3.connect(config.ANALYTICS_DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM city_requests WHERE state = 'UNKNOWN'")
    unknown_state = cursor.fetchone()[0]
    
    if unknown_state > 0:
        print(f"⚠️  Still have {unknown_state} city requests with UNKNOWN state")
    else:
        print("✓ No garbage city requests")
    
    conn.close()


def main():
    print("=" * 60)
    print("FIXING CRITICAL DATA ISSUES IN ENGAGIC DATABASES")
    print("=" * 60)
    
    # Create backups first
    config = Config()
    import shutil
    from datetime import datetime
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(config.DB_DIR, "backups_before_fix")
    os.makedirs(backup_dir, exist_ok=True)
    
    print("\n=== CREATING BACKUPS ===")
    for name, path in [
        ("locations", config.LOCATIONS_DB_PATH),
        ("meetings", config.MEETINGS_DB_PATH),
        ("analytics", config.ANALYTICS_DB_PATH)
    ]:
        if os.path.exists(path):
            backup_path = os.path.join(backup_dir, f"{name}_{timestamp}.db")
            shutil.copy2(path, backup_path)
            print(f"  Backed up {name} to {backup_path}")
    
    # Run fixes
    try:
        fix_duplicate_city_slugs()
        fix_wrong_city_slug_patterns()
        fix_invalid_meeting_dates()
        clean_garbage_city_requests()
        verify_fixes()
        
        print("\n" + "=" * 60)
        print("✓ ALL FIXES COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        print("Backups are available in:", backup_dir)
        raise


if __name__ == "__main__":
    main()