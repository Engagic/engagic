"""
City Repository - City and zipcode operations

Handles all city-related database operations including lookups,
creation, and related statistics.
"""

import logging
from typing import Optional, List, Dict
from datetime import datetime

from database.repositories.base import BaseRepository
from database.models import City, DatabaseConnectionError

logger = logging.getLogger("engagic")


class CityRepository(BaseRepository):
    """Repository for city operations"""

    def get_city(
        self,
        banana: Optional[str] = None,
        name: Optional[str] = None,
        state: Optional[str] = None,
        slug: Optional[str] = None,
        zipcode: Optional[str] = None,
    ) -> Optional[City]:
        """
        Unified city lookup - replaces 4+ separate methods.

        Uses most specific parameter provided:
        - banana: Direct primary key lookup (fastest)
        - slug: Lookup by vendor-specific identifier
        - zipcode: Lookup via zipcodes join
        - name + state: Normalized name matching

        Examples:
            get_city(banana="paloaltoCA")
            get_city(name="Palo Alto", state="CA")
            get_city(slug="cityofpaloalto")
            get_city(zipcode="94301")
        """
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        if banana:
            # Direct primary key lookup
            row = self._fetch_one("SELECT * FROM cities WHERE banana = ?", (banana,))
        elif slug:
            # Lookup by vendor slug
            row = self._fetch_one("SELECT * FROM cities WHERE slug = ?", (slug,))
        elif zipcode:
            # Lookup via zipcode join
            row = self._fetch_one(
                """
                SELECT c.* FROM cities c
                JOIN zipcodes cz ON c.banana = cz.banana
                WHERE cz.zipcode = ?
                LIMIT 1
            """,
                (zipcode,),
            )
        elif name and state:
            # Normalized name matching (case-insensitive, space-normalized)
            normalized_name = name.lower().replace(" ", "")
            row = self._fetch_one(
                """
                SELECT * FROM cities
                WHERE LOWER(REPLACE(name, ' ', '')) = ?
                AND UPPER(state) = ?
            """,
                (normalized_name, state.upper()),
            )
        else:
            raise ValueError("Must provide at least one search parameter")

        return City.from_db_row(row) if row else None

    def get_cities(
        self,
        state: Optional[str] = None,
        vendor: Optional[str] = None,
        name: Optional[str] = None,
        status: str = "active",
        limit: Optional[int] = None,
    ) -> List[City]:
        """
        Batch city lookup with filters.

        Args:
            state: Filter by state (e.g., "CA")
            vendor: Filter by vendor (e.g., "primegov")
            name: Filter by exact name match (for ambiguous city search)
            status: Filter by status (default: "active")
            limit: Maximum results to return
        """
        conditions = ["status = ?"]
        params = [status]

        if state:
            conditions.append("UPPER(state) = ?")
            params.append(state.upper())

        if vendor:
            conditions.append("vendor = ?")
            params.append(vendor)

        if name:
            conditions.append("LOWER(name) = ?")
            params.append(name.lower())

        query = f"""
            SELECT * FROM cities
            WHERE {" AND ".join(conditions)}
            ORDER BY name
        """

        if limit:
            query += f" LIMIT {limit}"

        rows = self._fetch_all(query, tuple(params))
        return [City.from_db_row(row) for row in rows]

    def get_city_meeting_stats(self, bananas: List[str]) -> Dict[str, Dict[str, int]]:
        """Get meeting statistics for multiple cities at once"""
        if not bananas:
            return {}

        placeholders = ",".join("?" * len(bananas))
        rows = self._fetch_all(
            f"""
            SELECT
                banana,
                COUNT(*) as total_meetings,
                SUM(CASE WHEN packet_url IS NOT NULL AND packet_url != '' THEN 1 ELSE 0 END) as meetings_with_packet,
                SUM(CASE WHEN summary IS NOT NULL THEN 1 ELSE 0 END) as summarized_meetings
            FROM meetings
            WHERE banana IN ({placeholders})
            GROUP BY banana
        """,
            tuple(bananas),
        )

        return {
            row["banana"]: {
                "total_meetings": row["total_meetings"],
                "meetings_with_packet": row["meetings_with_packet"],
                "summarized_meetings": row["summarized_meetings"],
            }
            for row in rows
        }

    def add_city(
        self,
        banana: str,
        name: str,
        state: str,
        vendor: str,
        slug: str,
        county: Optional[str] = None,
        zipcodes: Optional[List[str]] = None,
    ) -> City:
        """Add a new city to the database"""
        self._execute(
            """
            INSERT OR REPLACE INTO cities
            (banana, name, state, vendor, slug, county)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (banana, name, state, vendor, slug, county),
        )

        # Add zipcodes if provided
        if zipcodes:
            for i, zipcode in enumerate(zipcodes):
                is_primary = i == 0
                self._execute(
                    """
                    INSERT OR IGNORE INTO zipcodes
                    (banana, zipcode, is_primary)
                    VALUES (?, ?, ?)
                """,
                    (banana, zipcode, is_primary),
                )

        self._commit()
        logger.info(f"Added city: {banana} ({name}, {state})")

        result = self.get_city(banana=banana)
        if result is None:
            raise DatabaseConnectionError(
                f"Failed to retrieve newly added city: {banana}"
            )
        return result

    def get_city_zipcodes(self, banana: str) -> List[str]:
        """Get all zipcodes for a city"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        rows = self._fetch_all(
            """
            SELECT zipcode FROM zipcodes
            WHERE banana = ?
            ORDER BY is_primary DESC, zipcode
        """,
            (banana,),
        )

        return [row["zipcode"] for row in rows]

    def get_city_meeting_frequency(self, banana: str, days: int = 30) -> int:
        """Get count of meetings for a city in the last N days"""
        row = self._fetch_one(
            """
            SELECT COUNT(*) as count
            FROM meetings
            WHERE banana = ?
            AND date >= datetime('now', '-' || ? || ' days')
        """,
            (banana, days),
        )

        return row["count"] if row else 0

    def get_city_last_sync(self, banana: str) -> Optional[datetime]:
        """Get the last sync time for a city (most recent meeting created_at)"""
        row = self._fetch_one(
            """
            SELECT MAX(created_at) as last_sync
            FROM meetings
            WHERE banana = ?
        """,
            (banana,),
        )

        if row and row["last_sync"]:
            return datetime.fromisoformat(row["last_sync"])
        return None
