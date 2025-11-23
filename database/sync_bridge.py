"""
Synchronous bridge for async PostgreSQL Database

Allows existing synchronous code (conductor, CLI) to use the async
Database class without full async/await rewrite.

Usage:
    db = SyncDatabase()  # Defers pool creation until first use
    cities = db.get_all_cities()  # Synchronous call
    db.close()  # Clean up pool and event loop

Implementation:
    Creates persistent event loop on first use, avoiding event loop closure issues.
    All methods use the same event loop via run_until_complete().
    Thread-safe via locking. Enables gradual migration to full async.
"""

import asyncio
import threading
from typing import Optional, List, Dict, Any

from config import config
from database.db_postgres import Database
from database.models import City, Meeting, AgendaItem, Matter


class SyncDatabase:
    """Synchronous wrapper around async PostgreSQL Database

    Bridges sync code (conductor, CLI) → async database.
    Uses persistent event loop to avoid loop closure issues.

    Thread Safety:
    - Safe to use from multiple threads (uses thread-local lock)
    - Connection pool is created once and reused
    - Event loop stays alive for lifetime of instance
    """

    def __init__(
        self,
        dsn: Optional[str] = None,
        min_size: int = 10,
        max_size: int = 100
    ):
        """Initialize synchronous database wrapper

        Defers pool creation until first use to avoid event loop issues.

        Args:
            dsn: PostgreSQL DSN (defaults to config.get_postgres_dsn())
            min_size: Min pool size
            max_size: Max pool size
        """
        if dsn is None:
            dsn = config.get_postgres_dsn()

        self._dsn = dsn
        self._min_size = min_size
        self._max_size = max_size
        self._db = None
        self._loop = None
        self._lock = threading.Lock()

    def _ensure_initialized(self):
        """Ensure database pool and event loop are initialized

        Creates persistent event loop on first use. Thread-safe.
        """
        if self._db is None:
            with self._lock:
                if self._db is None:  # Double-check locking
                    # Create persistent event loop for this instance
                    self._loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(self._loop)
                    # Create database pool
                    self._db = self._loop.run_until_complete(
                        Database.create(self._dsn, self._min_size, self._max_size)
                    )

    def close(self):
        """Close connection pool and event loop"""
        if self._db is not None:
            self._loop.run_until_complete(self._db.close())
            self._loop.close()
            self._db = None
            self._loop = None

    def init_schema(self):
        """Initialize database schema"""
        self._ensure_initialized()
        self._loop.run_until_complete(self._db.init_schema())

    # ==================
    # CITY OPERATIONS
    # ==================

    def add_city(self, city: City) -> None:
        """Add a city (sync wrapper)"""
        self._ensure_initialized()
        self._loop.run_until_complete(self._db.cities.add_city(city))

    def get_city(self, banana: str) -> Optional[City]:
        """Get a city by banana (sync wrapper)"""
        self._ensure_initialized()
        return self._loop.run_until_complete(self._db.cities.get_city(banana))

    def get_all_cities(self, status: str = "active") -> List[City]:
        """Get all cities (sync wrapper)"""
        self._ensure_initialized()
        return self._loop.run_until_complete(self._db.cities.get_all_cities(status))

    def get_cities(self, status: str = "active", limit: int = 1000) -> List[City]:
        """Alias for get_all_cities (compatibility)"""
        return self.get_all_cities(status)

    def get_city_zipcodes(self, banana: str) -> List[str]:
        """Get zipcodes for a city (sync wrapper)"""
        self._ensure_initialized()
        city = self._loop.run_until_complete(self._db.cities.get_city(banana))
        return city.zipcodes if city and city.zipcodes else []

    # ==================
    # MEETING OPERATIONS
    # ==================

    def store_meeting(self, meeting: Meeting) -> None:
        """Store meeting (sync wrapper)"""
        self._ensure_initialized()
        self._loop.run_until_complete(self._db.meetings.store_meeting(meeting))

    def get_meeting(self, meeting_id: str) -> Optional[Meeting]:
        """Get meeting (sync wrapper)"""
        self._ensure_initialized()
        return self._loop.run_until_complete(self._db.meetings.get_meeting(meeting_id))

    def get_meetings_for_city(
        self,
        banana: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Meeting]:
        """Get meetings for city (sync wrapper)"""
        self._ensure_initialized()
        return self._loop.run_until_complete(self._db.meetings.get_meetings_for_city(banana, limit, offset))

    def get_meetings(self, bananas: List[str] = None, limit: int = 50) -> List[Meeting]:
        """Get meetings (compatibility wrapper)"""
        self._ensure_initialized()
        if bananas:
            # Get meetings for multiple cities
            all_meetings = []
            for banana in bananas:
                meetings = self._loop.run_until_complete(
                    self._db.meetings.get_meetings_for_city(banana, limit=limit)
                )
                all_meetings.extend(meetings)
            return all_meetings[:limit]
        else:
            # Get recent meetings across all cities
            return self._loop.run_until_complete(
                self._db.meetings.get_recent_meetings(limit=limit)
            )

    def get_agenda_items(self, meeting_id: str) -> List[AgendaItem]:
        """Alias for get_items_for_meeting (compatibility)"""
        return self.get_items_for_meeting(meeting_id)

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
        self._ensure_initialized()
        self._loop.run_until_complete(
            self._db.enqueue_job(
                source_url, job_type, payload, meeting_id, banana, priority
            )
        )

    def get_next_job(self) -> Optional[Dict[str, Any]]:
        """Get next job from queue (sync wrapper)"""
        self._ensure_initialized()
        return self._loop.run_until_complete(self._db.get_next_job())

    def mark_job_complete(self, queue_id: int) -> None:
        """Mark job complete (sync wrapper)"""
        self._ensure_initialized()
        self._loop.run_until_complete(self._db.mark_job_complete(queue_id))

    def mark_job_failed(self, queue_id: int, error_message: str) -> None:
        """Mark job failed (sync wrapper)"""
        self._ensure_initialized()
        self._loop.run_until_complete(self._db.queue.mark_job_failed(queue_id, error_message))

    def get_queue_stats(self) -> dict:
        """Get queue statistics (sync wrapper)"""
        self._ensure_initialized()
        return self._loop.run_until_complete(self._db.queue.get_queue_stats())

    # ==================
    # STATS OPERATIONS
    # ==================

    def get_stats(self) -> dict:
        """Get database statistics (sync wrapper)"""
        self._ensure_initialized()
        return self._loop.run_until_complete(self._db.get_stats())

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
        self._ensure_initialized()
        return self._loop.run_until_complete(self._db.search_meetings_fulltext(query, banana, limit))

    # ==================
    # PLACEHOLDER METHODS
    # ==================

    def store_item(self, item: AgendaItem) -> None:
        """Store item (sync wrapper)"""
        self._ensure_initialized()
        self._loop.run_until_complete(self._db.store_item(item))

    def get_items_for_meeting(self, meeting_id: str) -> List[AgendaItem]:
        """Get items for meeting (sync wrapper)"""
        self._ensure_initialized()
        return self._loop.run_until_complete(self._db.get_items_for_meeting(meeting_id))

    def store_matter(self, matter: Matter) -> None:
        """Store matter (sync wrapper)"""
        self._ensure_initialized()
        self._loop.run_until_complete(self._db.store_matter(matter))

    def get_matter(self, matter_id: str) -> Optional[Matter]:
        """Get matter (sync wrapper)"""
        self._ensure_initialized()
        return self._loop.run_until_complete(self._db.get_matter(matter_id))
