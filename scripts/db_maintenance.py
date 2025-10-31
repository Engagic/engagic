#!/usr/bin/env python3
"""
Database maintenance utilities for engagic
Cleanup, optimization, and health checks
"""

import sys
import os
import sqlite3
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.db import DatabaseManager
from config import Config


class DatabaseMaintenance:
    def __init__(self):
        config = Config()
        self.db = DatabaseManager(
            locations_db_path=config.LOCATIONS_DB_PATH,
            meetings_db_path=config.MEETINGS_DB_PATH,
            analytics_db_path=config.ANALYTICS_DB_PATH,
        )
        self.config = config

    def vacuum_databases(self):
        """Vacuum all databases to reclaim space and optimize"""
        print("\n=== VACUUM DATABASES ===")

        databases = [
            ("Locations", self.config.LOCATIONS_DB_PATH),
            ("Meetings", self.config.MEETINGS_DB_PATH),
            ("Analytics", self.config.ANALYTICS_DB_PATH),
        ]

        for name, path in databases:
            try:
                # Get size before
                size_before = os.path.getsize(path) / (1024 * 1024)  # MB

                conn = sqlite3.connect(path)
                conn.execute("VACUUM")
                conn.close()

                # Get size after
                size_after = os.path.getsize(path) / (1024 * 1024)  # MB
                saved = size_before - size_after

                print(
                    f"{name:12} - Before: {size_before:.2f}MB, After: {size_after:.2f}MB, Saved: {saved:.2f}MB"
                )

            except Exception as e:
                print(f"Error vacuuming {name}: {e}")

    def analyze_databases(self):
        """Run ANALYZE on all databases to update statistics"""
        print("\n=== ANALYZE DATABASES ===")

        databases = [
            ("Locations", self.db.locations),
            ("Meetings", self.db.meetings),
            ("Analytics", self.db.analytics),
        ]

        for name, db_obj in databases:
            try:
                with db_obj.get_connection() as conn:
                    conn.execute("ANALYZE")
                print(f"{name:12} - Statistics updated")
            except Exception as e:
                print(f"Error analyzing {name}: {e}")

    def check_integrity(self):
        """Check database integrity"""
        print("\n=== DATABASE INTEGRITY CHECK ===")

        databases = [
            ("Locations", self.config.LOCATIONS_DB_PATH),
            ("Meetings", self.config.MEETINGS_DB_PATH),
            ("Analytics", self.config.ANALYTICS_DB_PATH),
        ]

        all_ok = True
        for name, path in databases:
            try:
                conn = sqlite3.connect(path)
                result = conn.execute("PRAGMA integrity_check").fetchone()
                conn.close()

                if result[0] == "ok":
                    print(f"{name:12} - ✓ OK")
                else:
                    print(f"{name:12} - ✗ CORRUPTED: {result[0]}")
                    all_ok = False

            except Exception as e:
                print(f"{name:12} - ✗ ERROR: {e}")
                all_ok = False

        return all_ok

    def clean_old_analytics(self, days=30):
        """Clean old analytics data"""
        print(f"\n=== CLEAN ANALYTICS (older than {days} days) ===")

        cutoff_date = datetime.now() - timedelta(days=days)

        with self.db.analytics.get_connection() as conn:
            cursor = conn.cursor()

            # Count before
            cursor.execute("SELECT COUNT(*) FROM usage_metrics")
            metrics_before = cursor.fetchone()[0]

            # Delete old metrics
            cursor.execute(
                "DELETE FROM usage_metrics WHERE created_at < ?",
                (cutoff_date.isoformat(),),
            )
            metrics_deleted = cursor.rowcount

            conn.commit()

            print(
                f"Usage metrics: {metrics_before} → {metrics_before - metrics_deleted} (deleted {metrics_deleted})"
            )

    def deduplicate_cities(self):
        """Find and optionally merge duplicate cities"""
        print("\n=== FIND DUPLICATE CITIES ===")

        with self.db.locations.get_connection() as conn:
            cursor = conn.cursor()

            # Find cities with same name and state
            cursor.execute("""
                SELECT city_name, state, COUNT(*) as count, 
                       GROUP_CONCAT(id) as ids,
                       GROUP_CONCAT(city_slug) as slugs,
                       GROUP_CONCAT(vendor) as vendors
                FROM cities
                GROUP BY city_name, state
                HAVING count > 1
                ORDER BY count DESC
            """)

            duplicates = cursor.fetchall()

            if not duplicates:
                print("No duplicate cities found!")
                return

            print(f"Found {len(duplicates)} sets of duplicate cities:")
            print(f"{'City':<25} {'State':<6} {'Count':<6} {'IDs':<15} {'Vendors':<20}")
            print("-" * 75)

            for dup in duplicates:
                print(
                    f"{dup['city_name'][:24]:<25} {dup['state']:<6} {dup['count']:<6} "
                    f"{dup['ids']:<15} {dup['vendors'] or 'none':<20}"
                )

    def fix_city_banana_values(self):
        """Ensure all city_banana values follow the correct format"""
        print("\n=== FIX CITY_BANANA VALUES ===")

        import re

        with self.db.locations.get_connection() as conn:
            cursor = conn.cursor()

            # Find all cities
            cursor.execute("SELECT id, city_name, state, city_banana FROM cities")
            cities = cursor.fetchall()

            updates_needed = []
            for city in cities:
                # Calculate what city_banana should be
                expected_banana = (
                    re.sub(r"[^a-zA-Z0-9]", "", city["city_name"]).lower()
                    + city["state"].upper()
                )

                if city["city_banana"] != expected_banana:
                    updates_needed.append(
                        (city["id"], city["city_banana"], expected_banana)
                    )

            if not updates_needed:
                print("All city_banana values are correct!")
                return

            print(f"Found {len(updates_needed)} cities needing city_banana updates:")
            for city_id, current, expected in updates_needed[:10]:
                print(f"  ID {city_id}: '{current}' → '{expected}'")

            if len(updates_needed) > 10:
                print(f"  ... and {len(updates_needed) - 10} more")

            confirm = input("\nFix all city_banana values? (y/N): ").strip().lower()
            if confirm == "y":
                for city_id, current, expected in updates_needed:
                    cursor.execute(
                        "UPDATE cities SET city_banana = ? WHERE id = ?",
                        (expected, city_id),
                    )
                conn.commit()
                print(f"Updated {len(updates_needed)} city_banana values")

    def clean_orphaned_meetings(self):
        """Remove meetings for cities that no longer exist"""
        print("\n=== CLEAN ORPHANED MEETINGS ===")

        # Get all city_banana values from locations
        with self.db.locations.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT city_banana FROM cities")
            valid_bananas = set(row[0] for row in cursor.fetchall())

        # Find orphaned meetings
        with self.db.meetings.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT city_banana FROM meetings")
            meeting_bananas = set(row[0] for row in cursor.fetchall())

            orphaned = meeting_bananas - valid_bananas

            if not orphaned:
                print("No orphaned meetings found!")
                return

            print(f"Found meetings for {len(orphaned)} non-existent cities:")
            for banana in list(orphaned)[:10]:
                cursor.execute(
                    "SELECT COUNT(*) FROM meetings WHERE city_banana = ?", (banana,)
                )
                count = cursor.fetchone()[0]
                print(f"  {banana}: {count} meetings")

            if len(orphaned) > 10:
                print(f"  ... and {len(orphaned) - 10} more cities")

            # Count total orphaned meetings
            placeholders = ",".join("?" * len(orphaned))
            cursor.execute(
                f"SELECT COUNT(*) FROM meetings WHERE city_banana IN ({placeholders})",
                list(orphaned),
            )
            total_orphaned = cursor.fetchone()[0]

            print(f"\nTotal orphaned meetings: {total_orphaned}")

            confirm = input("Delete all orphaned meetings? (y/N): ").strip().lower()
            if confirm == "y":
                cursor.execute(
                    f"DELETE FROM meetings WHERE city_banana IN ({placeholders})",
                    list(orphaned),
                )
                conn.commit()
                print(f"Deleted {cursor.rowcount} orphaned meetings")

    def show_table_sizes(self):
        """Show size information for all tables"""
        print("\n=== TABLE SIZES ===")

        databases = [
            ("Locations", self.db.locations),
            ("Meetings", self.db.meetings),
            ("Analytics", self.db.analytics),
        ]

        for db_name, db_obj in databases:
            print(f"\n{db_name} Database:")
            with db_obj.get_connection() as conn:
                cursor = conn.cursor()

                # Get all tables
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
                tables = cursor.fetchall()

                for table in tables:
                    table_name = table[0]
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                    count = cursor.fetchone()[0]

                    # Estimate size (rough)
                    cursor.execute(f"SELECT * FROM {table_name} LIMIT 1")
                    if cursor.fetchone():
                        cursor.execute(
                            "SELECT LENGTH(GROUP_CONCAT(sql)) FROM sqlite_master WHERE tbl_name=?",
                            (table_name,),
                        )
                        schema_size = len(str(cursor.fetchone()[0]) or "")
                        estimated_size = (count * schema_size) / 1024  # KB
                        print(
                            f"  {table_name:<20} {count:>8} rows  (~{estimated_size:.1f} KB)"
                        )
                    else:
                        print(f"  {table_name:<20} {count:>8} rows")

    def backup_databases(self, backup_dir=None):
        """Create backups of all databases"""
        import shutil
        from datetime import datetime

        if backup_dir is None:
            backup_dir = os.path.join(self.config.DB_DIR, "backups")

        os.makedirs(backup_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        print(f"\n=== BACKING UP DATABASES to {backup_dir} ===")

        databases = [
            ("locations", self.config.LOCATIONS_DB_PATH),
            ("meetings", self.config.MEETINGS_DB_PATH),
            ("analytics", self.config.ANALYTICS_DB_PATH),
        ]

        for name, path in databases:
            if os.path.exists(path):
                backup_path = os.path.join(backup_dir, f"{name}_{timestamp}.db")
                shutil.copy2(path, backup_path)
                size = os.path.getsize(backup_path) / (1024 * 1024)  # MB
                print(f"  {name:<12} → {backup_path} ({size:.2f} MB)")
            else:
                print(f"  {name:<12} - SKIPPED (not found)")


def main():
    maint = DatabaseMaintenance()

    while True:
        print("\n" + "=" * 60)
        print("ENGAGIC DATABASE MAINTENANCE")
        print("=" * 60)
        print("1. Check integrity")
        print("2. Vacuum databases (reclaim space)")
        print("3. Analyze databases (update stats)")
        print("4. Show table sizes")
        print("5. Clean old analytics")
        print("6. Find duplicate cities")
        print("7. Fix city_banana values")
        print("8. Clean orphaned meetings")
        print("9. Backup databases")
        print("10. Run all maintenance tasks")
        print("0. Exit")

        choice = input("\nChoice: ").strip()

        if choice == "1":
            maint.check_integrity()

        elif choice == "2":
            maint.vacuum_databases()

        elif choice == "3":
            maint.analyze_databases()

        elif choice == "4":
            maint.show_table_sizes()

        elif choice == "5":
            days = input("Delete analytics older than (days, default 30): ").strip()
            days = int(days) if days.isdigit() else 30
            maint.clean_old_analytics(days)

        elif choice == "6":
            maint.deduplicate_cities()

        elif choice == "7":
            maint.fix_city_banana_values()

        elif choice == "8":
            maint.clean_orphaned_meetings()

        elif choice == "9":
            maint.backup_databases()

        elif choice == "10":
            print("\n=== RUNNING ALL MAINTENANCE TASKS ===")
            if maint.check_integrity():
                maint.backup_databases()
                maint.fix_city_banana_values()
                maint.deduplicate_cities()
                maint.clean_orphaned_meetings()
                maint.clean_old_analytics(30)
                maint.analyze_databases()
                maint.vacuum_databases()
                print("\n✓ All maintenance tasks completed!")
            else:
                print(
                    "\n✗ Integrity check failed - fix issues before running maintenance"
                )

        elif choice == "0":
            print("Goodbye!")
            break

        else:
            print("Invalid choice")


if __name__ == "__main__":
    main()
