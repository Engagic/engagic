"""
Synchronous bridge for async PostgreSQL Database

Allows existing synchronous code (conductor, CLI) to use the async
Database class without full async/await rewrite.

Usage:
    db = SyncDatabase()  # Creates async pool internally    cities = db.get_all_cities()  # Synchronous call
    db.close()

Implementation:
    Each method uses asyncio.run() to execute the async version.
    This is less efficient than native async but enables gradual migration.
"""

import asyncio
from typing import Optional, List, Dict, Any

from config import config
from database.db_postgres import Database
from database.models import City, Meeting, AgendaItem, Matter


class SyncDatabase:
    """Synchronous wrapper around async PostgreSQL Database

    Bridges sync code (conductor, CLI) → async database.
    Uses asyncio.run() internally - creates new event loop per call.

    Thread Safety:
    - Safe to use from multiple threads (each gets own event loop)    - Connection pool is shared across all SyncDatabase instances
    - No need for thread-local instances (unlike SQLite)
    """

    def __init__(
        self,
        dsn: Optional[str] = None,
        min_size: int = 10,
        max_size: int = 100
    ):
        """Initialize synchronous database wrapper

        Creates async connection pool using asyncio.run()

        Args:
            dsn: PostgreSQL DSN (defaults to config.get_postgres_dsn())
            min_size: Min pool size
            max_size: Max pool size        """
        if dsn is None:
            dsn = config.get_postgres_dsn()

        # Create pool in sync context
        self._db = asyncio.run(Database.create(dsn, min_size, max_size))

    def close(self):
        """Close connection pool"""
        asyncio.run(self._db.close())

    def init_schema(self):
        """Initialize database schema"""
        asyncio.run(self._db.init_schema())

    # ==================
    # CITY OPERATIONS
    # ==================

    def add_city(self, city: City) -> None:
        """Add a city (sync wrapper)"""
        asyncio.run(self._db.add_city(city))

    def get_city(self, banana: str) -> Optional[City]:
        """Get a city by banana (sync wrapper)"""
        return asyncio.run(self._db.get_city(banana))

    def get_all_cities(self, status: str = "active") -> List[City]:
        """Get all cities (sync wrapper)"""
        return asyncio.run(self._db.get_all_cities(status))

    # ==================
    # MEETING OPERATIONS
    # ==================

    def store_meeting(self, meeting: Meeting) -> None:
        """Store meeting (sync wrapper)"""
        asyncio.run(self._db.store_meeting(meeting))

    def get_meeting(self, meeting_id: str) -> Optional[Meeting]:
        """Get meeting (sync wrapper)"""
        return asyncio.run(self._db.get_meeting(meeting_id))

    def get_meetings_for_city(
        self,
        banana: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Meeting]:
        """Get meetings for city (sync wrapper)"""
        return asyncio.run(self._db.get_meetings_for_city(banana, limit, offset))

    # ==================
    # QUEUE OPERATIONS
    # ==================

    def enqueue_job(
        self,
        source_url: str,
        job_type: str,
        payload: Dict[str, Any],
        meeting_id: Optional[str] = None,
        banana: Optional[str] = None,
        priority: int = 0,
    ) -> None:
        """Enqueue job (sync wrapper)"""
        asyncio.run(
            self._db.enqueue_job(
                source_url, job_type, payload, meeting_id, banana, priority
            )
        )

    def get_next_job(self) -> Optional[Dict[str, Any]]:
        """Get next job from queue (sync wrapper)"""
        return asyncio.run(self._db.get_next_job())

    def mark_job_complete(self, queue_id: int) -> None:
        """Mark job complete (sync wrapper)"""
        asyncio.run(self._db.mark_job_complete(queue_id))

    def mark_job_failed(self, queue_id: int, error_message: str) -> None:
        """Mark job failed (sync wrapper)"""
        asyncio.run(self._db.mark_job_failed(queue_id, error_message))

    # ==================
    # SEARCH OPERATIONS
    # ==================

    def search_meetings_fulltext(
        self,
        query: str,
        banana: Optional[str] = None,
        limit: int = 50
    ) -> List[Meeting]:
        """Full-text search (sync wrapper)"""
        return asyncio.run(self._db.search_meetings_fulltext(query, banana, limit))

    # ==================
    # PLACEHOLDER METHODS
    # ==================

    def store_item(self, item: AgendaItem) -> None:
        """Store item (sync wrapper)"""
        asyncio.run(self._db.store_item(item))

    def get_items_for_meeting(self, meeting_id: str) -> List[AgendaItem]:
        """Get items for meeting (sync wrapper)"""
        return asyncio.run(self._db.get_items_for_meeting(meeting_id))

    def store_matter(self, matter: Matter) -> None:
        """Store matter (sync wrapper)"""
        asyncio.run(self._db.store_matter(matter))

    def get_matter(self, matter_id: str) -> Optional[Matter]:
        """Get matter (sync wrapper)"""
        return asyncio.run(self._db.get_matter(matter_id))
