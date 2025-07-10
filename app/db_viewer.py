#!/usr/bin/env python3
"""
Database viewer and editor for the new engagic database schema
Clean interface for managing cities, zipcodes, meetings, and analytics
"""

import json
from datetime import datetime
from databases import DatabaseManager
from config import config


class DatabaseViewer:
    def __init__(self):
        self.db = DatabaseManager(
            locations_db_path=config.LOCATIONS_DB_PATH,
            meetings_db_path=config.MEETINGS_DB_PATH,
            analytics_db_path=config.ANALYTICS_DB_PATH
        )

    def show_cities_table(self, limit=50):
        """Display cities table with zipcode counts"""
        with self.db.locations.get_connection() as conn:
            cursor = conn.execute("""
                SELECT c.id, c.city_name, c.state, c.city_slug, c.vendor, c.status,
                       c.county, c.created_at,
                       COUNT(z.zipcode) as zipcode_count,
                       GROUP_CONCAT(z.zipcode) as zipcodes
                FROM cities c
                LEFT JOIN zipcodes z ON c.id = z.city_id
                GROUP BY c.id
                ORDER BY c.city_name, c.state
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()

            if not rows:
                print("No cities found.")
                return

            print(f"\n=== CITIES TABLE (showing {len(rows)}) ===")
            print(f"{'ID':<4} {'City':<20} {'State':<6} {'Slug':<20} {'Vendor':<12} {'Status':<8} {'ZIPs':<4} {'Zipcodes':<30}")
            print("-" * 110)

            for row in rows:
                zipcodes = row['zipcodes'][:30] if row['zipcodes'] else ""
                print(f"{row['id']:<4} {row['city_name'][:19]:<20} {row['state']:<6} "
                     f"{row['city_slug'][:19]:<20} {row['vendor'] or '':<12} "
                     f"{row['status']:<8} {row['zipcode_count']:<4} {zipcodes}")

    def show_zipcodes_table(self, limit=50):
        """Display zipcodes table with city information"""
        with self.db.locations.get_connection() as conn:
            cursor = conn.execute("""
                SELECT z.id, z.zipcode, z.is_primary, z.created_at,
                       c.city_name, c.state, c.city_slug
                FROM zipcodes z
                JOIN cities c ON z.city_id = c.id
                ORDER BY z.zipcode
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()

            if not rows:
                print("No zipcodes found.")
                return

            print(f"\n=== ZIPCODES TABLE (showing {len(rows)}) ===")
            print(f"{'ID':<4} {'Zipcode':<8} {'Primary':<8} {'City':<20} {'State':<6} {'Slug':<20} {'Created':<12}")
            print("-" * 85)

            for row in rows:
                primary = "YES" if row['is_primary'] else "NO"
                created = row['created_at'][:10] if row['created_at'] else ""
                print(f"{row['id']:<4} {row['zipcode']:<8} {primary:<8} "
                     f"{row['city_name'][:19]:<20} {row['state']:<6} "
                     f"{row['city_slug'][:19]:<20} {created:<12}")

    def show_meetings_table(self, limit=20):
        """Display meetings table with city information"""
        # First get meetings
        with self.db.meetings.get_connection() as conn:
            cursor = conn.execute("""
                SELECT id, meeting_name, meeting_date, packet_url, city_slug,
                       processed_summary IS NOT NULL as has_summary,
                       created_at, last_accessed
                FROM meetings
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))
            meetings = cursor.fetchall()
        
        # Then get city info for each meeting
        rows = []
        for meeting in meetings:
            city_info = self.db.get_city_by_slug(meeting['city_slug'])
            if city_info:
                row = dict(meeting)
                row['city_name'] = city_info['city_name']
                row['state'] = city_info['state']
                row['vendor'] = city_info.get('vendor', '')
                rows.append(row)
            else:
                # Include meeting even if city not found
                row = dict(meeting)
                row['city_name'] = 'Unknown'
                row['state'] = ''
                row['vendor'] = ''
                rows.append(row)

        if not rows:
            print("No meetings found.")
            return

        print(f"\n=== MEETINGS TABLE (last {len(rows)}) ===")
        print(f"{'ID':<4} {'City':<20} {'Meeting':<25} {'Date':<12} {'Summary':<8} {'Created':<12}")
        print("-" * 90)

        for row in rows:
            meeting_name = row['meeting_name'][:24] if row['meeting_name'] else "Unknown"
            meeting_date = row['meeting_date'][:10] if row['meeting_date'] else ""
            has_summary = "YES" if row['has_summary'] else "NO"
            created = row['created_at'][:10] if row['created_at'] else ""
            packet_url = row["packet_url"] if row["packet_url"] else ""
            print(f"{row['id']:<4} {row['city_name'][:19]:<20} {meeting_name:<25} "
                 f"{meeting_date:<12} {has_summary:<8} {created:<12} {packet_url}")

    def show_usage_metrics(self, limit=20):
        """Display recent usage metrics"""
        # Get usage metrics first
        with self.db.analytics.get_connection() as conn:
            cursor = conn.execute("""
                SELECT id, search_query, search_type, city_slug, zipcode, created_at
                FROM usage_metrics
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))
            metrics = cursor.fetchall()
        
        # Then get city info for each metric
        rows = []
        for metric in metrics:
            row = dict(metric)
            if metric['city_slug']:
                city_info = self.db.get_city_by_slug(metric['city_slug'])
                if city_info:
                    row['city_name'] = city_info['city_name']
                    row['state'] = city_info['state']
                else:
                    row['city_name'] = 'Unknown'
                    row['state'] = ''
            else:
                row['city_name'] = None
                row['state'] = None
            rows.append(row)

        if not rows:
            print("No usage metrics found.")
            return

        print(f"\n=== USAGE METRICS (last {len(rows)}) ===")
        print(f"{'ID':<4} {'Query':<20} {'Type':<12} {'City Found':<20} {'When':<12}")
        print("-" * 75)

        for row in rows:
            query = row['search_query'][:19] if row['search_query'] else ""
            city_found = row['city_name'][:19] if row['city_name'] else "Not Found"
            when = row['created_at'][:10] if row['created_at'] else ""
            print(f"{row['id']:<4} {query:<20} {row['search_type']:<12} {city_found:<20} {when:<12}")

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

        vendor = input("Vendor (primegov/civicclerk/etc): ").strip()
        county = input("County (optional): ").strip() or None

        zipcodes_input = input("Zipcodes (comma-separated, optional): ").strip()
        zipcodes = [z.strip() for z in zipcodes_input.split(",")] if zipcodes_input else []

        try:
            city_id = self.db.add_city(city_name, state, city_slug, vendor, county, zipcodes)
            print(f"Added city '{city_name}, {state}' with ID {city_id}")
            if zipcodes:
                print(f"   Added {len(zipcodes)} zipcodes: {', '.join(zipcodes)}")
            return True
        except Exception as e:
            print(f"Error adding city: {e}")
            return False

    def add_zipcode_to_city(self):
        """Add zipcode to existing city"""
        print("\n=== ADD ZIPCODE TO CITY ===")
        self.show_cities_table(20)
        
        city_id = input("Enter city ID: ").strip()
        if not city_id.isdigit():
            print("Invalid city ID")
            return False

        zipcode = input("Enter zipcode: ").strip()
        if not zipcode.isdigit() or len(zipcode) != 5:
            print("Invalid zipcode format")
            return False

        is_primary = input("Is this the primary zipcode? (y/N): ").strip().lower() == 'y'

        try:
            with self.db.locations.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO zipcodes (zipcode, city_id, is_primary)
                    VALUES (?, ?, ?)
                """, (zipcode, int(city_id), is_primary))
                conn.commit()
                print(f"Added zipcode {zipcode} to city ID {city_id}")
                return True
        except Exception as e:
            print(f"Error adding zipcode: {e}")
            return False

    def update_city(self):
        """Update city information"""
        print("\n=== UPDATE CITY ===")
        self.show_cities_table(20)
        
        city_id = input("Enter city ID to update: ").strip()
        if not city_id.isdigit():
            print("Invalid city ID")
            return False

        field = input("Field to update (city_name/state/city_slug/vendor/status/county): ").strip()
        valid_fields = ['city_name', 'state', 'city_slug', 'vendor', 'status', 'county']
        
        if field not in valid_fields:
            print(f"Invalid field. Valid: {', '.join(valid_fields)}")
            return False

        new_value = input(f"New value for {field}: ").strip()

        try:
            with self.db.locations.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    UPDATE cities SET {field} = ?, updated_at = CURRENT_TIMESTAMP 
                    WHERE id = ?
                """, (new_value, int(city_id)))
                
                if cursor.rowcount == 0:
                    print(f"No city found with ID {city_id}")
                    return False
                
                conn.commit()
                print(f"Updated city {city_id}: {field} = '{new_value}'")
                return True
        except Exception as e:
            print(f"Error updating city: {e}")
            return False

    def delete_city(self):
        """Delete city and all related data"""
        print("\n=== DELETE CITY ===")
        self.show_cities_table(20)
        
        city_id = input("Enter city ID to delete: ").strip()
        if not city_id.isdigit():
            print("Invalid city ID")
            return False

        # Show what will be deleted
        with self.db.locations.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT city_name, state FROM cities WHERE id = ?", (int(city_id),))
            city_row = cursor.fetchone()
            if not city_row:
                print(f"No city found with ID {city_id}")
                return False

            cursor.execute("SELECT COUNT(*) as count FROM zipcodes WHERE city_id = ?", (int(city_id),))
            zipcode_count = cursor.fetchone()['count']
            
            # Get city_slug for cross-database operations
            cursor.execute("SELECT city_slug FROM cities WHERE id = ?", (int(city_id),))
            city_slug_row = cursor.fetchone()
            city_slug = city_slug_row['city_slug'] if city_slug_row else None
        
        # Count meetings in meetings database
        meeting_count = 0
        if city_slug:
            with self.db.meetings.get_connection() as conn:
                cursor = conn.execute("SELECT COUNT(*) as count FROM meetings WHERE city_slug = ?", (city_slug,))
                meeting_count = cursor.fetchone()['count']

        print(f"\nWARNING: This will delete:")
        print(f"   City: {city_row['city_name']}, {city_row['state']}")
        print(f"   {zipcode_count} zipcodes")
        print(f"   {meeting_count} meetings")

        confirm = input("\nAre you sure? Type 'DELETE' to confirm: ").strip()
        if confirm != "DELETE":
            print("Cancelled")
            return False

        try:
            # Delete from analytics database
            if city_slug:
                with self.db.analytics.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM usage_metrics WHERE city_slug = ?", (city_slug,))
                    conn.commit()
                
                # Delete from meetings database
                with self.db.meetings.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM meetings WHERE city_slug = ?", (city_slug,))
                    conn.commit()
            
            # Delete from locations database (zipcodes and city)
            with self.db.locations.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM zipcodes WHERE city_id = ?", (int(city_id),))
                cursor.execute("DELETE FROM cities WHERE id = ?", (int(city_id),))
                conn.commit()
            
            print(f"Deleted city and all related data")
            return True
        except Exception as e:
            print(f"Error deleting city: {e}")
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
            cursor.execute("""
                SELECT 'CITY' as type, id, city_name || ', ' || state as name, city_slug, vendor
                FROM cities 
                WHERE city_name LIKE ? OR state LIKE ? OR city_slug LIKE ? OR vendor LIKE ?
            """, (f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%"))
            results.extend(cursor.fetchall())
            
            # Search zipcodes
            cursor.execute("""
                SELECT 'ZIPCODE' as type, z.id, z.zipcode as name, 
                       c.city_name || ', ' || c.state as city_info, c.vendor
                FROM zipcodes z
                JOIN cities c ON z.city_id = c.id
                WHERE z.zipcode LIKE ?
            """, (f"%{query}%",))
            zipcode_results = cursor.fetchall()
            # Convert to expected format
            for row in zipcode_results:
                results.append({
                    'type': row['type'],
                    'id': row['id'],
                    'name': row['name'],
                    'city_slug': row['city_info'],
                    'vendor': row['vendor']
                })
        
        # Search meetings in meetings database
        with self.db.meetings.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 'MEETING' as type, id, meeting_name as name,
                       city_slug, meeting_date as vendor
                FROM meetings
                WHERE meeting_name LIKE ?
            """, (f"%{query}%",))
            meeting_results = cursor.fetchall()
            
            # Get city info for each meeting
            for row in meeting_results:
                city_info = self.db.get_city_by_slug(row['city_slug'])
                if city_info:
                    city_display = f"{city_info['city_name']}, {city_info['state']}"
                else:
                    city_display = row['city_slug']
                results.append({
                    'type': row['type'],
                    'id': row['id'],
                    'name': row['name'],
                    'city_slug': city_display,
                    'vendor': row['vendor']
                })

            if not results:
                print("No results found")
                return

            print(f"\nFound {len(results)} results:")
            print(f"{'Type':<8} {'ID':<4} {'Name':<30} {'City/Info':<25} {'Extra':<15}")
            print("-" * 85)
            
            for result in results:
                print(f"{result['type']:<8} {result['id']:<4} {str(result['name'])[:29]:<30} "
                     f"{str(result['city_slug'])[:24]:<25} {str(result['vendor'] or '')[:14]:<15}")

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
            zipcode_count = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(DISTINCT vendor) as count FROM cities WHERE vendor IS NOT NULL")
            vendor_count = cursor.fetchone()['count']
            
            cursor.execute("SELECT vendor, COUNT(*) as count FROM cities WHERE vendor IS NOT NULL GROUP BY vendor ORDER BY count DESC")
            vendor_breakdown = cursor.fetchall()
        
        # Stats from analytics database
        with self.db.analytics.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM usage_metrics")
            search_count = cursor.fetchone()['count']

        print(f"Zipcodes:            {zipcode_count}")
        print(f"Vendors:             {vendor_count}")
        print(f"Total searches:      {search_count}")
        
        if vendor_breakdown:
            print(f"\nVendor breakdown:")
            for vendor in vendor_breakdown:
                print(f"  {vendor['vendor']}: {vendor['count']} cities")


def main():
    viewer = DatabaseViewer()

    while True:
        print("\n" + "=" * 60)
        print("ENGAGIC DATABASE VIEWER v2.0")
        print("=" * 60)
        print("View Data:")
        print("  1. Cities")
        print("  2. Zipcodes") 
        print("  3. Meetings")
        print("  4. Usage metrics")
        print("  5. Statistics")
        print("\nEdit Data:")
        print("  6. Add city")
        print("  7. Add zipcode to city")
        print("  8. Update city")
        print("  9. Delete city")
        print("\nOther:")
        print("  10. Search database")
        print("  11. Exit")

        choice = input("\nChoice (1-11): ").strip()

        if choice == "1":
            limit = input("How many cities? (default 50): ").strip()
            limit = int(limit) if limit.isdigit() else 50
            viewer.show_cities_table(limit)

        elif choice == "2":
            limit = input("How many zipcodes? (default 50): ").strip()
            limit = int(limit) if limit.isdigit() else 50
            viewer.show_zipcodes_table(limit)

        elif choice == "3":
            limit = input("How many meetings? (default 20): ").strip()
            limit = int(limit) if limit.isdigit() else 20
            viewer.show_meetings_table(limit)

        elif choice == "4":
            limit = input("How many metrics? (default 20): ").strip()
            limit = int(limit) if limit.isdigit() else 20
            viewer.show_usage_metrics(limit)

        elif choice == "5":
            viewer.show_statistics()

        elif choice == "6":
            viewer.add_city()

        elif choice == "7":
            viewer.add_zipcode_to_city()

        elif choice == "8":
            viewer.update_city()

        elif choice == "9":
            viewer.delete_city()

        elif choice == "10":
            viewer.search_database()

        elif choice == "11":
            print("Goodbye!")
            break

        else:
            print("Invalid choice. Please enter 1-11.")


if __name__ == "__main__":
    main()