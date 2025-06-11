#!/usr/bin/env python3
"""
Simple database viewer and editor for engagic SQLite database
Provides cell-based representation for viewing and editing entries
"""

from database import MeetingDatabase


class DatabaseViewer:
    def __init__(self):
        self.db = MeetingDatabase()

    def show_zipcode_table(self):
        """Display zipcode_entries table in cell format"""
        with self.db.get_connection() as conn:
            cursor = conn.execute("""
                SELECT id, vendor, zipcode, city_name, city_slug, state, county, 
                       created_at, last_accessed 
                FROM zipcode_entries 
                ORDER BY id
            """)
            rows = cursor.fetchall()

            if not rows:
                print("No zipcode entries found.")
                return

            # Headers
            headers = [
                "ID",
                "Zipcode",
                "City Name",
                "City Slug",
                "State",
                "County",
                "Created",
                "Last Accessed",
            ]
            print("\n=== ZIPCODE ENTRIES ===")
            print(" | ".join(f"{h:<15}" for h in headers))
            print("-" * (len(headers) * 17))

            # Data rows
            for row in rows:
                values = [str(v)[:15] if v else "" for v in row]
                print(" | ".join(f"{v:<15}" for v in values))

    def show_meetings_table(self, limit=20):
        """Display meetings table in cell format"""
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, vendor, city_name, city_slug, meeting_date, 
                       meeting_name, packet_url, created_at 
                FROM meetings 
                ORDER BY id DESC 
                LIMIT ?
            """,
                (limit,),
            )
            rows = cursor.fetchall()

            if not rows:
                print("No meeting entries found.")
                return

            # Headers
            headers = [
                "ID",
                "Vendor",
                "City Name",
                "City Slug",
                "Date",
                "Meeting Name",
                "Packet URL",
                "Created",
            ]
            print(f"\n=== MEETINGS (last {limit}) ===")
            print(" | ".join(f"{h:<15}" for h in headers))
            print("-" * (len(headers) * 17))

            # Data rows
            for row in rows:
                values = [str(v)[:15] if v else "" for v in row]
                print(" | ".join(f"{v:<15}" for v in values))

    def update_zipcode_entry(self, entry_id: int, field: str, new_value: str):
        """Update a specific field in zipcode_entries table"""
        valid_fields = ["zipcode", "city_name", "city_slug", "state", "county"]

        if field not in valid_fields:
            print(f"Invalid field. Valid fields: {valid_fields}")
            return False

        with self.db.get_connection() as conn:
            try:
                cursor = conn.execute(
                    f"UPDATE zipcode_entries SET {field} = ? WHERE id = ?",
                    (new_value, entry_id),
                )
                if cursor.rowcount == 0:
                    print(f"No entry found with ID {entry_id}")
                    return False
                else:
                    print(f"Updated entry {entry_id}: {field} = '{new_value}'")
                    return True
            except Exception as e:
                print(f"Error updating entry: {e}")
                return False

    def update_meeting_entry(self, entry_id: int, field: str, new_value: str):
        """Update a specific field in meetings table"""
        valid_fields = [
            "vendor",
            "city_name",
            "city_slug",
            "meeting_date",
            "meeting_name",
            "packet_url",
        ]

        if field not in valid_fields:
            print(f"Invalid field. Valid fields: {valid_fields}")
            return False

        with self.db.get_connection() as conn:
            try:
                cursor = conn.execute(
                    f"UPDATE meetings SET {field} = ? WHERE id = ?",
                    (new_value, entry_id),
                )
                if cursor.rowcount == 0:
                    print(f"No entry found with ID {entry_id}")
                    return False
                else:
                    print(f"Updated entry {entry_id}: {field} = '{new_value}'")
                    return True
            except Exception as e:
                print(f"Error updating entry: {e}")
                return False

    def add_zipcode_entry(
        self,
        zipcode: str,
        city_name: str,
        city_slug: str,
        state: str = "",
        county: str = "",
    ):
        """Add a new zipcode entry"""
        entry_data = {
            "zipcode": zipcode,
            "city": city_name,
            "city_slug": city_slug,
            "state": state,
            "county": county,
            "meetings": [],
        }

        try:
            entry_id = self.db.store_zipcode_entry(entry_data)
            print(f"Added new zipcode entry with ID {entry_id}")
            return True
        except Exception as e:
            print(f"Error adding entry: {e}")
            return False

    def delete_zipcode_entry(self, entry_id: int):
        """Delete a zipcode entry"""
        with self.db.get_connection() as conn:
            try:
                cursor = conn.execute(
                    "DELETE FROM zipcode_entries WHERE id = ?", (entry_id,)
                )
                if cursor.rowcount == 0:
                    print(f"No entry found with ID {entry_id}")
                    return False
                else:
                    print(f"Deleted zipcode entry {entry_id}")
                    return True
            except Exception as e:
                print(f"Error deleting entry: {e}")
                return False

    def delete_meeting_entry(self, entry_id: int):
        """Delete a meeting entry"""
        with self.db.get_connection() as conn:
            try:
                cursor = conn.execute("DELETE FROM meetings WHERE id = ?", (entry_id,))
                if cursor.rowcount == 0:
                    print(f"No entry found with ID {entry_id}")
                    return False
                else:
                    print(f"Deleted meeting entry {entry_id}")
                    return True
            except Exception as e:
                print(f"Error deleting entry: {e}")
                return False

    def search_entries(self, table: str, field: str, value: str):
        """Search for entries in a table"""
        if table == "zipcode":
            valid_fields = ["zipcode", "city_name", "city_slug", "state", "county"]
            table_name = "zipcode_entries"
        elif table == "meetings":
            valid_fields = ["vendor", "city_name", "city_slug", "meeting_name"]
            table_name = "meetings"
        else:
            print("Invalid table. Use 'zipcode' or 'meetings'")
            return

        if field not in valid_fields:
            print(f"Invalid field for {table}. Valid fields: {valid_fields}")
            return

        with self.db.get_connection() as conn:
            cursor = conn.execute(
                f"SELECT * FROM {table_name} WHERE {field} LIKE ? ORDER BY id",
                (f"%{value}%",),
            )
            rows = cursor.fetchall()

            if not rows:
                print(f"No entries found in {table} where {field} contains '{value}'")
                return

            print(f"\n=== SEARCH RESULTS: {table.upper()} ===")
            for row in rows:
                print(f"ID {row['id']}: {dict(row)}")


def main():
    viewer = DatabaseViewer()

    while True:
        print("\n" + "=" * 60)
        print("ENGAGIC DATABASE VIEWER")
        print("=" * 60)
        print("1. View zipcode entries")
        print("2. View meetings")
        print("3. Update zipcode entry")
        print("4. Update meeting entry")
        print("5. Add zipcode entry")
        print("6. Delete zipcode entry")
        print("7. Delete meeting entry")
        print("8. Search entries")
        print("9. Exit")

        choice = input("\nEnter choice (1-9): ").strip()

        if choice == "1":
            viewer.show_zipcode_table()

        elif choice == "2":
            limit = input("How many meetings to show? (default 20): ").strip()
            limit = int(limit) if limit.isdigit() else 20
            viewer.show_meetings_table(limit)

        elif choice == "3":
            viewer.show_zipcode_table()
            entry_id = input("Enter zipcode entry ID to update: ").strip()
            if not entry_id.isdigit():
                print("Invalid ID")
                continue
            field = input(
                "Enter field to update (zipcode/city_name/city_slug/vendor/state/county): "
            ).strip()
            new_value = input(f"Enter new value for {field}: ").strip()
            viewer.update_zipcode_entry(int(entry_id), field, new_value)

        elif choice == "4":
            viewer.show_meetings_table()
            entry_id = input("Enter meeting entry ID to update: ").strip()
            if not entry_id.isdigit():
                print("Invalid ID")
                continue
            field = input(
                "Enter field to update (vendor/city_name/city_slug/meeting_date/meeting_name/packet_url): "
            ).strip()
            new_value = input(f"Enter new value for {field}: ").strip()
            viewer.update_meeting_entry(int(entry_id), field, new_value)

        elif choice == "5":
            zipcode = input("Enter zipcode: ").strip()
            city_name = input("Enter city name: ").strip()
            city_slug = input("Enter city slug: ").strip()
            state = input("Enter state (optional): ").strip()
            county = input("Enter county (optional): ").strip()
            viewer.add_zipcode_entry(zipcode, city_name, city_slug, state, county)

        elif choice == "6":
            viewer.show_zipcode_table()
            entry_id = input("Enter zipcode entry ID to delete: ").strip()
            if not entry_id.isdigit():
                print("Invalid ID")
                continue
            confirm = (
                input(f"Are you sure you want to delete entry {entry_id}? (y/N): ")
                .strip()
                .lower()
            )
            if confirm == "y":
                viewer.delete_zipcode_entry(int(entry_id))

        elif choice == "7":
            viewer.show_meetings_table()
            entry_id = input("Enter meeting entry ID to delete: ").strip()
            if not entry_id.isdigit():
                print("Invalid ID")
                continue
            confirm = (
                input(f"Are you sure you want to delete entry {entry_id}? (y/N): ")
                .strip()
                .lower()
            )
            if confirm == "y":
                viewer.delete_meeting_entry(int(entry_id))

        elif choice == "8":
            table = input("Search in which table? (zipcode/meetings): ").strip().lower()
            field = input("Search in which field? ").strip()
            value = input("Search for what value? ").strip()
            viewer.search_entries(table, field, value)

        elif choice == "9":
            print("Goodbye!")
            break

        else:
            print("Invalid choice. Please enter 1-9.")


if __name__ == "__main__":
    main()
