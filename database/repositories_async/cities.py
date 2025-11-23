"""Async CityRepository for city operations

Handles CRUD operations for cities:
- Store/retrieve cities with zipcodes
- Filter cities by state, vendor, name
- Get meeting frequency statistics
- Get last sync timestamp
"""

from typing import List, Optional
from datetime import datetime

from database.repositories_async.base import BaseRepository
from database.models import City
from config import get_logger

logger = get_logger(__name__).bind(component="city_repository")


class CityRepository(BaseRepository):
    """Repository for city operations

    Provides:
    - Add cities with zipcode handling
    - Retrieve cities with filtering
    - Meeting frequency statistics
    - Last sync timestamp queries

    Confidence: 9/10 (standard CRUD with PostgreSQL-specific features)
    """

    async def add_city(self, city: City) -> None:
        """Add a city to the database

        Args:
            city: City object with banana, name, state, vendor, slug

        Raises:
            asyncpg.UniqueViolationError: If city already exists
        """
        async with self.transaction() as conn:
            await conn.execute(
                """
                INSERT INTO cities (banana, name, state, vendor, slug, county, status)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                city.banana,
                city.name,
                city.state,
                city.vendor,
                city.slug,
                city.county,
                city.status or "active",
            )

            # Insert zipcodes
            if city.zipcodes:
                for zipcode in city.zipcodes:
                    await conn.execute(
                        """
                        INSERT INTO zipcodes (banana, zipcode, is_primary)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (banana, zipcode) DO NOTHING
                        """,
                        city.banana,
                        zipcode,
                        False,  # TODO: Support primary zipcode designation
                    )

        logger.info("city added", banana=city.banana, name=city.name)

    async def get_city(self, banana: str) -> Optional[City]:
        """Get a city by banana

        Args:
            banana: City banana (e.g., "paloaltoCA")

        Returns:
            City object with zipcodes, or None if not found
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT banana, name, state, vendor, slug, county, status
                FROM cities
                WHERE banana = $1
                """,
                banana,
            )

            if not row:
                return None

            # Fetch zipcodes
            zipcodes_rows = await conn.fetch(
                """
                SELECT zipcode
                FROM zipcodes
                WHERE banana = $1
                """,
                banana,
            )
            zipcodes = [str(r["zipcode"]) for r in zipcodes_rows]

            return City(
                banana=row["banana"],
                name=row["name"],
                state=row["state"],
                vendor=row["vendor"],
                slug=row["slug"],
                county=row["county"],
                status=row["status"],
                zipcodes=zipcodes,
            )

    async def get_all_cities(self, status: str = "active") -> List[City]:
        """Get all cities with given status

        Args:
            status: City status filter (default: "active")

        Returns:
            List of City objects with zipcodes
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT banana, name, state, vendor, slug, county, status
                FROM cities
                WHERE status = $1
                ORDER BY name
                """,
                status,
            )

            cities = []
            for row in rows:
                # Fetch zipcodes for each city
                zipcodes_rows = await conn.fetch(
                    """
                    SELECT zipcode
                    FROM zipcodes
                    WHERE banana = $1
                    """,
                    row["banana"],
                )
                zipcodes = [str(r["zipcode"]) for r in zipcodes_rows]

                cities.append(
                    City(
                        banana=row["banana"],
                        name=row["name"],
                        state=row["state"],
                        vendor=row["vendor"],
                        slug=row["slug"],
                        county=row["county"],
                        status=row["status"],
                        zipcodes=zipcodes,
                    )
                )

            return cities

    async def get_cities(
        self,
        state: Optional[str] = None,
        vendor: Optional[str] = None,
        name: Optional[str] = None,
        status: str = "active",
        limit: Optional[int] = None,
    ) -> List[City]:
        """Batch city lookup with filters

        Args:
            state: Filter by state (e.g., "CA")
            vendor: Filter by vendor (e.g., "primegov")
            name: Filter by exact name match
            status: Filter by status (default: "active")
            limit: Maximum number of results

        Returns:
            List of City objects matching filters
        """
        conditions = ["status = $1"]
        params = [status]
        param_counter = 2

        if state:
            conditions.append(f"state = ${param_counter}")
            params.append(state)
            param_counter += 1

        if vendor:
            conditions.append(f"vendor = ${param_counter}")
            params.append(vendor)
            param_counter += 1

        if name:
            conditions.append(f"name = ${param_counter}")
            params.append(name)
            param_counter += 1

        where_clause = " AND ".join(conditions)
        limit_clause = f"LIMIT ${param_counter}" if limit else ""
        if limit:
            params.append(limit)

        query = f"""
            SELECT banana, name, state, vendor, slug, county, status
            FROM cities
            WHERE {where_clause}
            ORDER BY state, name
            {limit_clause}
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

            cities = []
            for row in rows:
                # Fetch zipcodes for this city
                zipcodes_rows = await conn.fetch(
                    """
                    SELECT zipcode
                    FROM zipcodes
                    WHERE banana = $1
                    """,
                    row["banana"],
                )
                zipcodes = [str(r["zipcode"]) for r in zipcodes_rows]

                cities.append(
                    City(
                        banana=row["banana"],
                        name=row["name"],
                        state=row["state"],
                        vendor=row["vendor"],
                        slug=row["slug"],
                        county=row["county"],
                        status=row["status"],
                        zipcodes=zipcodes,
                    )
                )

            return cities

    async def get_city_meeting_frequency(self, banana: str, days: int = 30) -> int:
        """Get count of meetings for a city in the last N days

        Args:
            banana: City banana identifier
            days: Number of days to look back (default: 30)

        Returns:
            Count of meetings in the last N days
        """
        row = await self._fetchrow(
            """
            SELECT COUNT(*) as count
            FROM meetings
            WHERE banana = $1
            AND date >= NOW() - INTERVAL '1 day' * $2
            """,
            banana,
            days
        )
        return row["count"] if row else 0

    async def get_city_last_sync(self, banana: str) -> Optional[datetime]:
        """Get timestamp of most recent meeting for a city

        Used by fetcher to determine if city needs syncing.

        Args:
            banana: City banana

        Returns:
            Datetime of most recent meeting, or None
        """
        row = await self._fetchrow(
            """
            SELECT MAX(date) as last_sync
            FROM meetings
            WHERE banana = $1
            """,
            banana,
        )

        return row["last_sync"] if row else None
