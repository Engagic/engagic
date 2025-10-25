#!/usr/bin/env python3
"""
Database viewer and editor for the engagic database schema
Clean interface for managing cities, zipcodes, meetings, and analytics
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.database.unified_db import UnifiedDatabase
from backend.core.config import Config


class DatabaseViewer:
    def __init__(self):
        config = Config()
        self.db = UnifiedDatabase(config.UNIFIED_DB_PATH)

    def show_cities_table(self, limit=50):
        """Display cities table with zipcode counts"""
        with self.db.locations.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT c.id, c.city_name, c.state, c.city_banana, c.city_slug, c.vendor, c.status,
                       c.county, c.created_at,
                       COUNT(z.zipcode) as zipcode_count,
                       GROUP_CONCAT(z.zipcode) as zipcodes
                FROM cities c
                LEFT JOIN zipcodes z ON c.id = z.city_id
                GROUP BY c.id
                ORDER BY c.city_name, c.state
                LIMIT ?
            """,
                (limit,),
            )
            rows = cursor.fetchall()

            if not rows:
                print("No cities found.")
                return

            print(f"\n=== CITIES TABLE (showing {len(rows)}) ===")
            print(
                f"{'ID':<4} {'City':<20} {'State':<6} {'Banana':<20} {'Slug':<20} {'Vendor':<12} {'Status':<8} {'ZIPs':<4}"
            )
            print("-" * 115)

            for row in rows:
                zipcodes_display = f"({row['zipcode_count']} zips)"
                print(
                    f"{row['id']:<4} {row['city_name'][:19]:<20} {row['state']:<6} "
                    f"{row['city_banana'][:19]:<20} {row['city_slug'][:19]:<20} "
                    f"{row['vendor'] or '':<12} {row['status']:<8} {zipcodes_display}"
                )

    def show_zipcodes_table(self, limit=50):
        """Display zipcodes table with city information"""
        with self.db.locations.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT z.id, z.zipcode, z.is_primary, z.created_at,
                       c.city_name, c.state, c.city_banana
                FROM zipcodes z
                JOIN cities c ON z.city_id = c.id
                ORDER BY z.zipcode
                LIMIT ?
            """,
                (limit,),
            )
            rows = cursor.fetchall()

            if not rows:
                print("No zipcodes found.")
                return

            print(f"\n=== ZIPCODES TABLE (showing {len(rows)}) ===")
            print(
                f"{'ID':<4} {'Zipcode':<8} {'Primary':<8} {'City':<20} {'State':<6} {'Banana':<20} {'Created':<12}"
            )
            print("-" * 90)

            for row in rows:
                primary = "YES" if row["is_primary"] else "NO"
                created = row["created_at"][:10] if row["created_at"] else ""
                print(
                    f"{row['id']:<4} {row['zipcode']:<8} {primary:<8} "
                    f"{row['city_name'][:19]:<20} {row['state']:<6} "
                    f"{row['city_banana'][:19]:<20} {created:<12}"
                )

    def show_meetings_table(self, limit=20, city_filter=None):
        """Display meetings table with city information"""
        query = """
            SELECT id, meeting_name, meeting_date, packet_url, city_banana,
                   processed_summary IS NOT NULL as has_summary,
                   raw_packet_size, processing_time_seconds,
                   created_at, last_accessed
            FROM meetings
        """
        params = []
        
        if city_filter:
            query += " WHERE city_banana LIKE ?"
            params.append(f"%{city_filter}%")
            
        query += " ORDER BY meeting_date DESC LIMIT ?"
        params.append(limit)
        
        with self.db.meetings.get_connection() as conn:
            cursor = conn.execute(query, params)
            meetings = cursor.fetchall()

        # Get city info for each meeting
        rows = []
        for meeting in meetings:
            city_info = self.db.get_city_by_banana(meeting["city_banana"])
            if city_info:
                row = dict(meeting)
                row["city_name"] = city_info["city_name"]
                row["state"] = city_info["state"]
                row["vendor"] = city_info.get("vendor", "")
                rows.append(row)
            else:
                # Include meeting even if city not found
                row = dict(meeting)
                row["city_name"] = "Unknown"
                row["state"] = ""
                row["vendor"] = ""
                rows.append(row)

        if not rows:
            print("No meetings found.")
            return

        print(f"\n=== MEETINGS TABLE (last {len(rows)}) ===")
        print(
            f"{'ID':<6} {'City':<20} {'Meeting':<30} {'Date':<12} {'Summary':<8} {'Packet':<7}"
        )
        print("-" * 95)

        for row in rows:
            meeting_name = (
                row["meeting_name"][:29] if row["meeting_name"] else "Unknown"
            )
            
            # Handle various date formats
            meeting_date = ""
            if row["meeting_date"]:
                date_str = str(row["meeting_date"])
                if "In Progress" in date_str:
                    meeting_date = "In Progress"
                elif date_str.startswith("9999"):
                    meeting_date = "TBD"
                else:
                    meeting_date = date_str[:10]
            
            has_summary = "YES" if row["has_summary"] else "NO"
            has_packet = "YES" if row["packet_url"] else "NO"
            
            city_display = f"{row['city_name'][:19]}, {row['state']}" if row['city_name'] != "Unknown" else row['city_banana'][:19]
            
            print(
                f"{row['id']:<6} {city_display[:19]:<20} {meeting_name:<30} "
                f"{meeting_date:<12} {has_summary:<8} {has_packet:<7}"
            )

    def show_usage_metrics(self, limit=20):
        """Display recent usage metrics"""
        with self.db.analytics.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, search_query, search_type, city_banana, zipcode, created_at
                FROM usage_metrics
                ORDER BY created_at DESC
                LIMIT ?
            """,
                (limit,),
            )
            metrics = cursor.fetchall()

        # Get city info for each metric
        rows = []
        for metric in metrics:
            row = dict(metric)
            if metric["city_banana"]:
                city_info = self.db.get_city_by_banana(metric["city_banana"])
                if city_info:
                    row["city_name"] = city_info["city_name"]
                    row["state"] = city_info["state"]
                else:
                    row["city_name"] = "Unknown"
                    row["state"] = ""
            else:
                row["city_name"] = None
                row["state"] = None
            rows.append(row)

        if not rows:
            print("No usage metrics found.")
            return

        print(f"\n=== USAGE METRICS (last {len(rows)}) ===")
        print(f"{'ID':<4} {'Query':<25} {'Type':<12} {'City Found':<25} {'When':<20}")
        print("-" * 90)

        for row in rows:
            query = row["search_query"][:24] if row["search_query"] else ""
            city_found = row["city_name"][:24] if row["city_name"] else "Not Found"
            when = row["created_at"] if row["created_at"] else ""
            print(
                f"{row['id']:<4} {query:<25} {row['search_type']:<12} {city_found:<25} {when:<20}"
            )

    def show_city_requests(self, limit=20):
        """Display city requests (cities users searched for but aren't in system)"""
        with self.db.analytics.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT city_name, state, search_query, search_type, request_count, 
                       status, priority_score, first_requested, last_requested
                FROM city_requests
                ORDER BY request_count DESC, priority_score DESC
                LIMIT ?
            """,
                (limit,),
            )
            rows = cursor.fetchall()

        if not rows:
            print("No city requests found.")
            return

        print(f"\n=== CITY REQUESTS (top {len(rows)}) ===")
        print(
            f"{'Query':<25} {'Type':<12} {'Location':<25} {'Count':<7} {'Priority':<9} {'Last Req':<12}"
        )
        print("-" * 110)

        for row in rows:
            # Format query display
            query = row["search_query"][:24] if row["search_query"] else ""
            
            # Format location display based on type
            if row["search_type"] == "state":
                location = f"State: {row['state']}"
            elif row["search_type"] == "zipcode":
                location = f"{row['city_name'][:15]}, {row['state']}"
            elif row["city_name"] == "STATE_REQUEST":
                location = f"State: {row['state']}"
            else:
                state = row["state"] if row["state"] != "UNKNOWN" else "??"
                location = f"{row['city_name'][:18]}, {state}"
            
            # Format search type
            search_type = row["search_type"] if row["search_type"] else "unknown"
            
            last_req = row["last_requested"][:10] if row["last_requested"] else ""
            
            print(
                f"{query:<25} {search_type:<12} {location:<25} {row['request_count']:<7} "
                f"{row['priority_score']:<9} {last_req:<12}"
            )

    def add_city(self):
        """Interactive city addition"""
        print("\n=== ADD NEW CITY ===")
        city_name = input("City name: ").strip()
        if not city_name:
            print("City name required")
            return False

        state = input("State (2-letter code): ").strip().upper()
        if len(state) != 2:
            print("State must be 2-letter code (e.g., CA)")
            return False

        city_slug = input("City slug (vendor-specific): ").strip()
        if not city_slug:
            print("City slug required")
            return False

        vendor = input("Vendor (granicus/primegov/civicclerk/etc): ").strip()
        county = input("County (optional): ").strip() or None

        zipcodes_input = input("Zipcodes (comma-separated, optional): ").strip()
        zipcodes = (
            [z.strip() for z in zipcodes_input.split(",")] if zipcodes_input else []
        )

        try:
            city_id = self.db.add_city(
                city_name, state, city_slug, vendor, county, zipcodes
            )
            print(f"Added city '{city_name}, {state}' with ID {city_id}")
            if zipcodes:
                print(f"   Added {len(zipcodes)} zipcodes: {', '.join(zipcodes)}")
            return True
        except Exception as e:
            print(f"Error adding city: {e}")
            return False

    def update_city(self):
        """Update city information"""
        print("\n=== UPDATE CITY ===")
        self.show_cities_table(20)

        city_banana = input("Enter city_banana to update: ").strip()
        if not city_banana:
            print("Invalid city_banana")
            return False

        field = input(
            "Field to update (city_name/state/city_slug/vendor/status/county): "
        ).strip()
        valid_fields = ["city_name", "state", "city_slug", "vendor", "status", "county"]

        if field not in valid_fields:
            print(f"Invalid field. Valid: {', '.join(valid_fields)}")
            return False

        new_value = input(f"New value for {field}: ").strip()

        try:
            with self.db.locations.get_connection() as conn:
                cursor = conn.cursor()
                
                # If updating city_name or state, also update city_banana
                if field in ["city_name", "state"]:
                    # Get current values
                    cursor.execute(
                        "SELECT city_name, state FROM cities WHERE city_banana = ?",
                        (city_banana,)
                    )
                    current = cursor.fetchone()
                    if not current:
                        print(f"No city found with city_banana {city_banana}")
                        return False

                    # Determine new values
                    new_city_name = new_value if field == "city_name" else current["city_name"]
                    new_state = new_value if field == "state" else current["state"]

                    # Calculate new city_banana
                    import re
                    new_city_banana = re.sub(r'[^a-zA-Z0-9]', '', new_city_name).lower() + new_state.upper()

                    # Update with new city_banana
                    cursor.execute(
                        f"""
                        UPDATE cities
                        SET {field} = ?, city_banana = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE city_banana = ?
                    """,
                        (new_value, new_city_banana, city_banana),
                    )
                else:
                    cursor.execute(
                        f"""
                        UPDATE cities SET {field} = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE city_banana = ?
                    """,
                        (new_value, city_banana),
                    )

                if cursor.rowcount == 0:
                    print(f"No city found with city_banana {city_banana}")
                    return False

                conn.commit()
                print(f"Updated city {city_banana}: {field} = '{new_value}'")
                return True
        except Exception as e:
            print(f"Error updating city: {e}")
            return False

    def search_database(self):
        """Search across all tables"""
        print("\n=== SEARCH DATABASE ===")
        query = input("Search for: ").strip()
        if not query:
            print("Search query required")
            return

        print(f"\nSearching for '{query}'...")

        results = []

        # Search cities in locations database
        with self.db.locations.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 'CITY' as type, id, city_name || ', ' || state as name, 
                       city_banana, city_slug, vendor
                FROM cities 
                WHERE city_name LIKE ? OR state LIKE ? OR city_slug LIKE ? 
                      OR vendor LIKE ? OR city_banana LIKE ?
            """,
                (f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%"),
            )
            for row in cursor.fetchall():
                results.append({
                    "type": row["type"],
                    "id": row["id"],
                    "name": row["name"],
                    "info": f"{row['city_banana']} ({row['vendor'] or 'no vendor'})",
                    "extra": row["city_slug"]
                })

            # Search zipcodes
            cursor.execute(
                """
                SELECT 'ZIPCODE' as type, z.id, z.zipcode as name, 
                       c.city_name || ', ' || c.state as city_info, c.city_banana
                FROM zipcodes z
                JOIN cities c ON z.city_id = c.id
                WHERE z.zipcode LIKE ?
            """,
                (f"%{query}%",),
            )
            for row in cursor.fetchall():
                results.append({
                    "type": row["type"],
                    "id": row["id"],
                    "name": row["name"],
                    "info": row["city_info"],
                    "extra": row["city_banana"]
                })

        # Search meetings in meetings database
        with self.db.meetings.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 'MEETING' as type, id, meeting_name as name,
                       city_banana, meeting_date
                FROM meetings
                WHERE meeting_name LIKE ? OR city_banana LIKE ?
            """,
                (f"%{query}%", f"%{query}%"),
            )
            for row in cursor.fetchall():
                city_info = self.db.get_city_by_banana(row["city_banana"])
                if city_info:
                    city_display = f"{city_info['city_name']}, {city_info['state']}"
                else:
                    city_display = row["city_banana"]
                    
                results.append({
                    "type": row["type"],
                    "id": row["id"],
                    "name": row["name"][:40] if row["name"] else "Unknown",
                    "info": city_display,
                    "extra": row["meeting_date"][:10] if row["meeting_date"] else ""
                })

        if not results:
            print("No results found")
            return

        print(f"\nFound {len(results)} results:")
        print(f"{'Type':<10} {'ID':<6} {'Name':<40} {'Info':<30} {'Extra':<20}")
        print("-" * 110)

        for result in results[:50]:  # Limit display to 50 results
            print(
                f"{result['type']:<10} {result['id']:<6} {result['name'][:39]:<40} "
                f"{result['info'][:29]:<30} {result['extra'][:19]:<20}"
            )
            
        if len(results) > 50:
            print(f"\n... and {len(results) - 50} more results")

    def show_statistics(self):
        """Show database statistics"""
        stats = self.db.get_cache_stats()

        print("\n=== DATABASE STATISTICS ===")
        print(f"Cities:              {stats.get('cities_count', 0)}")
        print(f"Total meetings:      {stats.get('meetings_count', 0)}")
        print(f"Processed meetings:  {stats.get('processed_count', 0)}")
        print(f"Recent activity:     {stats.get('recent_activity', 0)} (7 days)")

        # Additional stats from locations database
        with self.db.locations.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) as count FROM zipcodes")
            zipcode_count = cursor.fetchone()["count"]

            cursor.execute(
                "SELECT COUNT(DISTINCT vendor) as count FROM cities WHERE vendor IS NOT NULL"
            )
            vendor_count = cursor.fetchone()["count"]

            cursor.execute(
                "SELECT vendor, COUNT(*) as count FROM cities WHERE vendor IS NOT NULL GROUP BY vendor ORDER BY count DESC"
            )
            vendor_breakdown = cursor.fetchall()

        # Stats from analytics database
        with self.db.analytics.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM usage_metrics")
            search_count = cursor.fetchone()["count"]
            
            cursor.execute("SELECT COUNT(*) as count FROM city_requests")
            request_count = cursor.fetchone()["count"]

        # Stats from meetings database  
        with self.db.meetings.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check for problematic meetings
            cursor.execute(
                "SELECT COUNT(*) as count FROM meetings WHERE meeting_date LIKE '%In Progress%'"
            )
            in_progress_count = cursor.fetchone()["count"]
            
            cursor.execute(
                "SELECT COUNT(*) as count FROM meetings WHERE meeting_date > '2026-12-31' OR meeting_date LIKE '9999%'"
            )
            future_count = cursor.fetchone()["count"]

        print(f"Zipcodes:            {zipcode_count}")
        print(f"Vendors:             {vendor_count}")
        print(f"Total searches:      {search_count}")
        print(f"City requests:       {request_count}")
        
        if in_progress_count > 0 or future_count > 0:
            print("\n⚠️  Data Issues:")
            if in_progress_count > 0:
                print(f"  - {in_progress_count} meetings with 'In Progress' dates")
            if future_count > 0:
                print(f"  - {future_count} meetings with invalid future dates")

        if vendor_breakdown:
            print("\nVendor breakdown:")
            for vendor in vendor_breakdown:
                percentage = (vendor['count'] / stats.get('cities_count', 1)) * 100
                print(f"  {vendor['vendor']:<15} {vendor['count']:>4} cities ({percentage:.1f}%)")

    def fix_meeting_dates(self):
        """Fix problematic meeting dates"""
        print("\n=== FIX MEETING DATES ===")
        
        with self.db.meetings.get_connection() as conn:
            cursor = conn.cursor()
            
            # Find problematic meetings
            cursor.execute(
                """
                SELECT id, city_banana, meeting_name, meeting_date 
                FROM meetings 
                WHERE meeting_date LIKE '%In Progress%' 
                   OR meeting_date > '2026-12-31' 
                   OR meeting_date LIKE '9999%'
                LIMIT 20
                """
            )
            problematic = cursor.fetchall()
            
            if not problematic:
                print("No problematic meeting dates found!")
                return
            
            print(f"Found {len(problematic)} meetings with problematic dates:")
            print(f"{'ID':<6} {'City':<20} {'Meeting':<30} {'Current Date':<30}")
            print("-" * 90)
            
            for row in problematic:
                city_info = self.db.get_city_by_banana(row["city_banana"])
                city_display = f"{city_info['city_name'][:19]}" if city_info else row["city_banana"][:19]
                meeting_name = row["meeting_name"][:29] if row["meeting_name"] else "Unknown"
                print(
                    f"{row['id']:<6} {city_display:<20} {meeting_name:<30} {str(row['meeting_date'])[:29]:<30}"
                )
            
            print("\nOptions:")
            print("1. Set all to NULL (will be re-fetched)")
            print("2. Set to specific date")
            print("3. Cancel")
            
            choice = input("\nChoice (1-3): ").strip()
            
            if choice == "1":
                cursor.execute(
                    """
                    UPDATE meetings 
                    SET meeting_date = NULL 
                    WHERE meeting_date LIKE '%In Progress%' 
                       OR meeting_date > '2026-12-31' 
                       OR meeting_date LIKE '9999%'
                    """
                )
                conn.commit()
                print(f"Set {cursor.rowcount} meeting dates to NULL")
                
            elif choice == "2":
                new_date = input("Enter new date (YYYY-MM-DD): ").strip()
                cursor.execute(
                    """
                    UPDATE meetings 
                    SET meeting_date = ? 
                    WHERE meeting_date LIKE '%In Progress%' 
                       OR meeting_date > '2026-12-31' 
                       OR meeting_date LIKE '9999%'
                    """,
                    (new_date,)
                )
                conn.commit()
                print(f"Updated {cursor.rowcount} meeting dates to {new_date}")
                
            else:
                print("Cancelled")


def main():
    viewer = DatabaseViewer()

    while True:
        print("\n" + "=" * 60)
        print("ENGAGIC DATABASE VIEWER v3.0")
        print("=" * 60)
        print("View Data:")
        print("  1. Cities")
        print("  2. Zipcodes") 
        print("  3. Meetings")
        print("  4. Usage metrics")
        print("  5. City requests")
        print("  6. Statistics")
        print("\nEdit Data:")
        print("  7. Add city")
        print("  8. Update city")
        print("  9. Search database")
        print("  10. Fix meeting dates")
        print("\nOther:")
        print("  0. Exit")

        choice = input("\nChoice: ").strip()

        if choice == "1":
            limit = input("How many cities? (default 50): ").strip()
            limit = int(limit) if limit.isdigit() else 50
            viewer.show_cities_table(limit)

        elif choice == "2":
            limit = input("How many zipcodes? (default 50): ").strip()
            limit = int(limit) if limit.isdigit() else 50
            viewer.show_zipcodes_table(limit)

        elif choice == "3":
            city_filter = input("Filter by city (optional, press Enter to skip): ").strip()
            limit = input("How many meetings? (default 20): ").strip()
            limit = int(limit) if limit.isdigit() else 20
            viewer.show_meetings_table(limit, city_filter if city_filter else None)

        elif choice == "4":
            limit = input("How many metrics? (default 20): ").strip()
            limit = int(limit) if limit.isdigit() else 20
            viewer.show_usage_metrics(limit)

        elif choice == "5":
            limit = input("How many requests? (default 20): ").strip()
            limit = int(limit) if limit.isdigit() else 20
            viewer.show_city_requests(limit)

        elif choice == "6":
            viewer.show_statistics()

        elif choice == "7":
            viewer.add_city()

        elif choice == "8":
            viewer.update_city()

        elif choice == "9":
            viewer.search_database()
            
        elif choice == "10":
            viewer.fix_meeting_dates()

        elif choice == "0":
            print("Goodbye!")
            break

        else:
            print("Invalid choice.")


if __name__ == "__main__":
    main()