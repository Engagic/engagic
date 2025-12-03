"""Async CityRepository for city operations

Handles CRUD operations for cities:
- Store/retrieve cities with zipcodes
- Filter cities by state, vendor, name
- Get meeting frequency statistics
- Get last sync timestamp
"""

from typing import Any, Dict, List, Optional
from datetime import datetime

from database.repositories_async.base import BaseRepository
from database.repositories_async.helpers import deserialize_city_participation
from database.models import City
from config import get_logger

logger = get_logger(__name__).bind(component="city_repository")


def _build_city(row, zipcodes: List[str]) -> City:
    """Factory to construct City from database row + zipcodes"""
    return City(
        banana=row["banana"],
        name=row["name"],
        state=row["state"],
        vendor=row["vendor"],
        slug=row["slug"],
        county=row["county"],
        status=row["status"],
        participation=deserialize_city_participation(row["participation"]),
        zipcodes=zipcodes,
    )


class CityRepository(BaseRepository):
    """Repository for city operations

    Provides:
    - Add cities with zipcode handling
    - Retrieve cities with filtering
    - Meeting frequency statistics
    - Last sync timestamp queries
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

            # Insert zipcodes (batch for efficiency)
            if city.zipcodes:
                zipcode_records = [(city.banana, z, False) for z in city.zipcodes]
                await conn.executemany(
                    """
                    INSERT INTO zipcodes (banana, zipcode, is_primary)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (banana, zipcode) DO NOTHING
                    """,
                    zipcode_records,
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
                SELECT banana, name, state, vendor, slug, county, status, participation
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

            return _build_city(row, zipcodes)

    async def get_city_by_zipcode(self, zipcode: str) -> Optional[City]:
        """Get city by zipcode lookup

        Args:
            zipcode: ZIP code to search for

        Returns:
            City object or None
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT c.banana, c.name, c.state, c.vendor, c.slug, c.county, c.status, c.participation
                FROM cities c
                INNER JOIN zipcodes z ON c.banana = z.banana
                WHERE z.zipcode = $1
                LIMIT 1
                """,
                zipcode,
            )

            if not row:
                return None

            # Fetch all zipcodes for this city
            zip_rows = await conn.fetch(
                "SELECT zipcode FROM zipcodes WHERE banana = $1",
                row["banana"]
            )
            zipcodes = [str(r["zipcode"]) for r in zip_rows]

            return _build_city(row, zipcodes)

    async def get_all_cities(
        self, status: str = "active", include_zipcodes: bool = False
    ) -> List[City]:
        """Get all cities with given status

        Args:
            status: City status filter (default: "active")
            include_zipcodes: If True, batch fetch zipcodes for all cities.
                             Default False for performance in search contexts.

        Returns:
            List of City objects (zipcodes empty unless include_zipcodes=True)
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT banana, name, state, vendor, slug, county, status, participation
                FROM cities
                WHERE status = $1
                ORDER BY name
                """,
                status,
            )

            zipcodes_map: Dict[str, List[str]] = {}
            if include_zipcodes and rows:
                bananas = [row["banana"] for row in rows]
                zipcodes_rows = await conn.fetch(
                    "SELECT banana, zipcode FROM zipcodes WHERE banana = ANY($1)",
                    bananas,
                )
                for zrow in zipcodes_rows:
                    zipcodes_map.setdefault(zrow["banana"], []).append(str(zrow["zipcode"]))

            return [_build_city(row, zipcodes_map.get(row["banana"], [])) for row in rows]

    async def get_cities(
        self,
        state: Optional[str] = None,
        vendor: Optional[str] = None,
        name: Optional[str] = None,
        status: str = "active",
        limit: Optional[int] = None,
        include_zipcodes: bool = False,
    ) -> List[City]:
        """Batch city lookup with filters

        Args:
            state: Filter by state (e.g., "CA")
            vendor: Filter by vendor (e.g., "primegov")
            name: Filter by exact name match
            status: Filter by status (default: "active")
            limit: Maximum number of results
            include_zipcodes: If True, batch fetch zipcodes for all cities.
                             Default False for performance in search contexts.

        Returns:
            List of City objects matching filters (zipcodes empty unless include_zipcodes=True)
        """
        conditions = ["status = $1"]
        params: List[Any] = [status]
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
            conditions.append(f"LOWER(name) = ${param_counter}")
            params.append(name.lower())
            param_counter += 1

        where_clause = " AND ".join(conditions)
        limit_clause = f"LIMIT ${param_counter}" if limit else ""
        if limit:
            params.append(limit)

        query = f"""
            SELECT banana, name, state, vendor, slug, county, status, participation
            FROM cities
            WHERE {where_clause}
            ORDER BY state, name
            {limit_clause}
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

            zipcodes_map: Dict[str, List[str]] = {}
            if include_zipcodes and rows:
                bananas = [row["banana"] for row in rows]
                zipcodes_rows = await conn.fetch(
                    "SELECT banana, zipcode FROM zipcodes WHERE banana = ANY($1)",
                    bananas,
                )
                for zrow in zipcodes_rows:
                    zipcodes_map.setdefault(zrow["banana"], []).append(str(zrow["zipcode"]))

            return [_build_city(row, zipcodes_map.get(row["banana"], [])) for row in rows]

    async def get_city_names(self, status: str = "active") -> List[str]:
        """Get just city names for fuzzy matching (no N+1)

        Lightweight query that returns only names, avoiding the full City
        object construction and zipcode queries. Used for fuzzy search.

        Args:
            status: City status filter (default: "active")

        Returns:
            List of city names
        """
        rows = await self._fetch(
            "SELECT DISTINCT name FROM cities WHERE status = $1 ORDER BY name",
            status,
        )
        return [row["name"] for row in rows]

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
