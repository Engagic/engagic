#!/usr/bin/env python3
"""
Database viewer and editor for the engagic database schema
Clean interface for managing cities, zipcodes, meetings, and queue
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from infocore.database.unified_db import UnifiedDatabase
from infocore.config import Config


class DatabaseViewer:
    def __init__(self):
        config = Config()
        self.db = UnifiedDatabase(config.UNIFIED_DB_PATH)

    def show_cities_table(self, limit=50):
        """Display cities table with zipcode counts"""
        cities = self.db.get_cities(limit=limit)

        print(f"\n=== CITIES TABLE (showing {len(cities)}) ===")
        print(
            f"{'Banana':<20} {'City':<20} {'State':<6} {'Slug':<20} {'Vendor':<12} {'Status':<8} {'ZIPs':<4}"
        )
        print("-" * 115)

        for city in cities:
            zipcodes = self.db.get_city_zipcodes(city.banana)
            zipcode_display = str(len(zipcodes)) if zipcodes else "0"
            print(
                f"{city.banana:<20} {city.name[:19]:<20} {city.state:<6} "
                f"{city.slug[:19]:<20} {city.vendor:<12} "
                f"{city.status:<8} {zipcode_display:<4}"
            )

    def show_zipcodes_table(self, limit=50):
        """Display zipcodes table with city information"""
        # Get all cities first
        cities = self.db.get_cities(limit=1000)

        results = []
        for city in cities:
            zipcodes = self.db.get_city_zipcodes(city.banana)
            for i, zipcode in enumerate(zipcodes):
                results.append(
                    {
                        "zipcode": zipcode,
                        "city_name": city.name,
                        "state": city.state,
                        "banana": city.banana,
                        "is_primary": i == 0,
                    }
                )

        # Sort by zipcode and limit
        results.sort(key=lambda x: x["zipcode"])
        results = results[:limit]

        if not results:
            print("No zipcodes found.")
            return

        print(f"\n=== ZIPCODES TABLE (showing {len(results)}) ===")
        print(f"{'Zipcode':<8} {'Primary':<8} {'City':<20} {'State':<6} {'Banana':<20}")
        print("-" * 70)

        for row in results:
            primary = "YES" if row["is_primary"] else "NO"
            print(
                f"{row['zipcode']:<8} {primary:<8} "
                f"{row['city_name'][:19]:<20} {row['state']:<6} "
                f"{row['banana'][:19]:<20}"
            )

    def show_meetings_table(self, limit=20, city_filter=None):
        """Display meetings table with city information"""
        # Get all meetings or filter by city
        if city_filter:
            # Get matching cities
            all_cities = self.db.get_cities(limit=1000)
            matching_bananas = [
                c.banana
                for c in all_cities
                if city_filter.lower() in c.name.lower()
                or city_filter.lower() in c.banana.lower()
            ]
            if matching_bananas:
                meetings = self.db.get_meetings(bananas=matching_bananas, limit=limit)
            else:
                meetings = []
        else:
            meetings = self.db.get_meetings(limit=limit)

        if not meetings:
            print("No meetings found.")
            return

        print(f"\n=== MEETINGS TABLE (last {len(meetings)}) ===")
        print(
            f"{'ID':<8} {'City':<20} {'Title':<35} {'Date':<12} {'Summary':<8} {'Status':<10}"
        )
        print("-" * 105)

        for meeting in meetings:
            city = self.db.get_city(banana=meeting.banana)
            city_display = (
                f"{city.name[:15]}, {city.state}" if city else meeting.banana[:19]
            )

            title = meeting.title[:34] if meeting.title else "Unknown"

            # Format date
            date_str = ""
            if meeting.date:
                date_str = meeting.date.strftime("%Y-%m-%d")

            has_summary = "YES" if meeting.summary else "NO"
            status = meeting.status[:9] if meeting.status else "-"

            print(
                f"{meeting.id[:7]:<8} {city_display[:19]:<20} {title:<35} "
                f"{date_str:<12} {has_summary:<8} {status:<10}"
            )

    def show_agenda_items_table(self, limit=20):
        """Display recent agenda items across all meetings"""
        # Get recent meetings with items
        meetings = self.db.get_meetings(limit=100)

        all_items = []
        for meeting in meetings:
            items = self.db.get_agenda_items(meeting.id)
            for item in items:
                all_items.append({"item": item, "meeting": meeting})

        # Limit results
        all_items = all_items[:limit]

        if not all_items:
            print("No agenda items found.")
            return

        print(f"\n=== AGENDA ITEMS (showing {len(all_items)}) ===")
        print(f"{'Item ID':<15} {'Meeting':<30} {'Title':<40} {'Summary':<8}")
        print("-" * 100)

        for row in all_items:
            item = row["item"]
            meeting = row["meeting"]

            meeting_title = meeting.title[:29] if meeting.title else "Unknown"
            item_title = item.title[:39] if item.title else "Unknown"
            has_summary = "YES" if item.summary else "NO"

            print(
                f"{item.id[:14]:<15} {meeting_title:<30} {item_title:<40} {has_summary:<8}"
            )

    def show_queue_table(self, limit=50):
        """Display processing queue"""
        stats = self.db.get_queue_stats()

        print("\n=== PROCESSING QUEUE STATISTICS ===")
        print(f"Pending:     {stats.get('pending_count', 0)}")
        print(f"Processing:  {stats.get('processing_count', 0)}")
        print(f"Completed:   {stats.get('completed_count', 0)}")
        print(f"Failed:      {stats.get('failed_count', 0)}")
        print(f"Permanent:   {stats.get('permanently_failed', 0)}")

        avg_time = stats.get("avg_processing_seconds", 0)
        if avg_time > 0:
            print(f"Avg time:    {avg_time:.1f}s")

        # Show pending items
        conn = self.db.conn
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, packet_url, meeting_id, banana, status, priority, retry_count
            FROM queue
            WHERE status IN ('pending', 'processing', 'failed')
            ORDER BY priority DESC, created_at ASC
            LIMIT ?
        """,
            (limit,),
        )

        rows = cursor.fetchall()

        if rows:
            print(f"\n=== QUEUE ITEMS (showing {len(rows)}) ===")
            print(
                f"{'ID':<6} {'Status':<12} {'Priority':<9} {'Retries':<8} {'City':<20} {'URL':<40}"
            )
            print("-" * 100)

            for row in rows:
                url_display = row["packet_url"][:39] if row["packet_url"] else ""
                banana = row["banana"][:19] if row["banana"] else ""

                print(
                    f"{row['id']:<6} {row['status']:<12} {row['priority']:<9} "
                    f"{row['retry_count']:<8} {banana:<20} {url_display:<40}"
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

        slug = input("Slug (vendor-specific): ").strip()
        if not slug:
            print("Slug required")
            return False

        vendor = input("Vendor (granicus/primegov/civicclerk/legistar/etc): ").strip()
        if not vendor:
            print("Vendor required")
            return False

        county = input("County (optional): ").strip() or None

        zipcodes_input = input("Zipcodes (comma-separated, optional): ").strip()
        zipcodes = (
            [z.strip() for z in zipcodes_input.split(",")] if zipcodes_input else None
        )

        # Generate banana
        import re

        banana = re.sub(r"[^a-zA-Z0-9]", "", city_name).lower() + state.upper()

        try:
            city = self.db.add_city(
                banana=banana,
                name=city_name,
                state=state,
                vendor=vendor,
                slug=slug,
                county=county,
                zipcodes=zipcodes,
            )
            print(f"Added city '{city.name}, {city.state}' with banana {city.banana}")
            if zipcodes:
                print(f"   Added {len(zipcodes)} zipcodes: {', '.join(zipcodes)}")
            return True
        except Exception as e:
            print(f"Error adding city: {e}")
            return False

    def update_city(self):
        """Update city information - continuous edit mode"""
        current_banana = None

        while True:
            if not current_banana:
                print("\n=== UPDATE CITY ===")
                self.show_cities_table(20)

                banana = input("\nEnter banana to update (or 'q' to quit): ").strip()
                if not banana or banana.lower() == "q":
                    return False

                # Get current city
                city = self.db.get_city(banana=banana)
                if not city:
                    print(f"No city found with banana {banana}")
                    continue

                current_banana = banana
            else:
                # Refresh city data
                city = self.db.get_city(banana=current_banana)
                if not city:
                    print(f"City {current_banana} no longer exists")
                    current_banana = None
                    continue

            print(f"\n=== {city.name}, {city.state} ({current_banana}) ===")
            print(f"  name:   {city.name}")
            print(f"  state:  {city.state}")
            print(f"  vendor: {city.vendor}")
            print(f"  slug:   {city.slug}")
            print(f"  county: {city.county or 'None'}")
            print(f"  status: {city.status}")

            field = input(
                "\nField to update (name/state/slug/vendor/status/county) or 'q' to quit: "
            ).strip()

            if not field or field.lower() == "q":
                current_banana = None
                continue

            valid_fields = ["name", "state", "slug", "vendor", "status", "county"]
            if field not in valid_fields:
                print(f"Invalid field. Valid: {', '.join(valid_fields)}")
                continue

            new_value = input(f"New value for {field} (or 'cancel' to skip): ").strip()

            if new_value.lower() == "cancel":
                continue

            if not new_value and field != "county":
                print("Value cannot be empty (except county)")
                continue

            try:
                conn = self.db.conn
                cursor = conn.cursor()

                # If updating name or state, also update banana
                if field in ["name", "state"]:
                    new_name = new_value if field == "name" else city.name
                    new_state = new_value if field == "state" else city.state

                    # Calculate new banana
                    import re

                    new_banana = (
                        re.sub(r"[^a-zA-Z0-9]", "", new_name).lower()
                        + new_state.upper()
                    )

                    # Update with new banana
                    cursor.execute(
                        """
                        UPDATE cities
                        SET name = ?, state = ?, banana = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE banana = ?
                    """,
                        (new_name, new_state, new_banana, current_banana),
                    )

                    # Update foreign keys in other tables
                    cursor.execute(
                        "UPDATE zipcodes SET banana = ? WHERE banana = ?",
                        (new_banana, current_banana),
                    )
                    cursor.execute(
                        "UPDATE meetings SET banana = ? WHERE banana = ?",
                        (new_banana, current_banana),
                    )
                    cursor.execute(
                        "UPDATE queue SET banana = ? WHERE banana = ?",
                        (new_banana, current_banana),
                    )

                    print(f"Updated city and banana: {current_banana} → {new_banana}")
                    current_banana = new_banana
                else:
                    cursor.execute(
                        f"""
                        UPDATE cities SET {field} = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE banana = ?
                    """,
                        (new_value, current_banana),
                    )
                    print(f"Updated {field} = '{new_value}'")

                conn.commit()
            except Exception as e:
                print(f"Error updating city: {e}")
                continue

    def search_database(self):
        """Search across all tables"""
        print("\n=== SEARCH DATABASE ===")
        query = input("Search for: ").strip()
        if not query:
            print("Search query required")
            return

        print(f"\nSearching for '{query}'...")

        results = []

        # Search cities
        all_cities = self.db.get_cities(limit=1000)
        for city in all_cities:
            if (
                query.lower() in city.name.lower()
                or query.lower() in city.state.lower()
                or query.lower() in city.banana.lower()
                or query.lower() in city.slug.lower()
                or query.lower() in city.vendor.lower()
            ):
                results.append(
                    {
                        "type": "CITY",
                        "id": city.banana,
                        "name": f"{city.name}, {city.state}",
                        "info": f"{city.banana} ({city.vendor})",
                        "extra": city.slug,
                    }
                )

        # Search zipcodes
        for city in all_cities:
            zipcodes = self.db.get_city_zipcodes(city.banana)
            for zipcode in zipcodes:
                if query in zipcode:
                    results.append(
                        {
                            "type": "ZIPCODE",
                            "id": zipcode,
                            "name": zipcode,
                            "info": f"{city.name}, {city.state}",
                            "extra": city.banana,
                        }
                    )

        # Search meetings
        meetings = self.db.get_meetings(limit=500)
        for meeting in meetings:
            if (
                query.lower() in meeting.title.lower() if meeting.title else False
            ) or query.lower() in meeting.banana.lower():
                city = self.db.get_city(banana=meeting.banana)
                city_display = f"{city.name}, {city.state}" if city else meeting.banana

                results.append(
                    {
                        "type": "MEETING",
                        "id": meeting.id[:10],
                        "name": meeting.title[:40] if meeting.title else "Unknown",
                        "info": city_display,
                        "extra": meeting.date.strftime("%Y-%m-%d")
                        if meeting.date
                        else "",
                    }
                )

        if not results:
            print("No results found")
            return

        print(f"\nFound {len(results)} results:")
        print(f"{'Type':<10} {'ID':<12} {'Name':<40} {'Info':<30} {'Extra':<20}")
        print("-" * 115)

        for result in results[:50]:
            print(
                f"{result['type']:<10} {result['id'][:11]:<12} {result['name'][:39]:<40} "
                f"{result['info'][:29]:<30} {result['extra'][:19]:<20}"
            )

        if len(results) > 50:
            print(f"\n... and {len(results) - 50} more results")

    def show_statistics(self):
        """Show database statistics"""
        stats = self.db.get_stats()

        print("\n=== DATABASE STATISTICS ===")
        print(f"Cities:              {stats.get('active_cities', 0)}")
        print(f"Total meetings:      {stats.get('total_meetings', 0)}")
        print(f"Summarized meetings: {stats.get('summarized_meetings', 0)}")
        print(f"Pending meetings:    {stats.get('pending_meetings', 0)}")
        print(f"Summary rate:        {stats.get('summary_rate', '0%')}")

        # Additional stats
        conn = self.db.conn
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

        cursor.execute("SELECT COUNT(*) as count FROM items")
        item_count = cursor.fetchone()["count"]

        print(f"Zipcodes:            {zipcode_count}")
        print(f"Agenda items:        {item_count}")
        print(f"Vendors:             {vendor_count}")

        if vendor_breakdown:
            print("\nVendor breakdown:")
            total_cities = stats.get("active_cities", 1)
            for vendor in vendor_breakdown:
                percentage = (vendor["count"] / total_cities) * 100
                print(
                    f"  {vendor['vendor']:<15} {vendor['count']:>4} cities ({percentage:.1f}%)"
                )

        # Queue stats
        queue_stats = self.db.get_queue_stats()
        if any(queue_stats.values()):
            print("\nProcessing queue:")
            print(f"  Pending:    {queue_stats.get('pending_count', 0)}")
            print(f"  Processing: {queue_stats.get('processing_count', 0)}")
            print(f"  Completed:  {queue_stats.get('completed_count', 0)}")
            print(f"  Failed:     {queue_stats.get('failed_count', 0)}")

    def enqueue_unprocessed(self):
        """Bulk enqueue unprocessed meetings"""
        print("\n=== ENQUEUE UNPROCESSED MEETINGS ===")

        limit_input = input("How many meetings to enqueue? (default: all): ").strip()
        limit = int(limit_input) if limit_input.isdigit() else None

        try:
            count = self.db.bulk_enqueue_unprocessed_meetings(limit=limit)
            print(f"Enqueued {count} meetings for processing")
        except Exception as e:
            print(f"Error enqueuing meetings: {e}")

    def reset_failed_queue_items(self):
        """Reset failed queue items"""
        print("\n=== RESET FAILED QUEUE ITEMS ===")

        max_retries = input("Max retries to reset (default: 3): ").strip()
        max_retries = int(max_retries) if max_retries.isdigit() else 3

        try:
            count = self.db.reset_failed_items(max_retries=max_retries)
            print(f"Reset {count} failed items back to pending")
        except Exception as e:
            print(f"Error resetting items: {e}")


def main():
    viewer = DatabaseViewer()

    while True:
        print("\n" + "=" * 60)
        print("ENGAGIC DATABASE VIEWER v4.0 (Unified Schema)")
        print("=" * 60)
        print("View Data:")
        print("  1. Cities")
        print("  2. Zipcodes")
        print("  3. Meetings")
        print("  4. Agenda items")
        print("  5. Processing queue")
        print("  6. Statistics")
        print("\nEdit Data:")
        print("  7. Add city")
        print("  8. Update city")
        print("  9. Search database")
        print("\nQueue Management:")
        print("  10. Enqueue unprocessed meetings")
        print("  11. Reset failed queue items")
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
            city_filter = input(
                "Filter by city (optional, press Enter to skip): "
            ).strip()
            limit = input("How many meetings? (default 20): ").strip()
            limit = int(limit) if limit.isdigit() else 20
            viewer.show_meetings_table(limit, city_filter if city_filter else None)

        elif choice == "4":
            limit = input("How many items? (default 20): ").strip()
            limit = int(limit) if limit.isdigit() else 20
            viewer.show_agenda_items_table(limit)

        elif choice == "5":
            limit = input("How many queue items? (default 50): ").strip()
            limit = int(limit) if limit.isdigit() else 50
            viewer.show_queue_table(limit)

        elif choice == "6":
            viewer.show_statistics()

        elif choice == "7":
            viewer.add_city()

        elif choice == "8":
            viewer.update_city()

        elif choice == "9":
            viewer.search_database()

        elif choice == "10":
            viewer.enqueue_unprocessed()

        elif choice == "11":
            viewer.reset_failed_queue_items()

        elif choice == "0":
            print("Goodbye!")
            break

        else:
            print("Invalid choice.")


if __name__ == "__main__":
    main()
