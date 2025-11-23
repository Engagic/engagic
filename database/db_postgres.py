"""
PostgreSQL Database Layer for Engagic

Replaces SQLite-based UnifiedDatabase with PostgreSQL + asyncpg.
Simplifies repository pattern - one Database class handles all operations.

Key Differences from SQLite version:
- Async/await throughout (asyncpg is async-only)
- Connection pooling (10-100 connections)
- Normalized topics (separate tables instead of JSON)
- JSONB for complex structures (attachments, metadata)
- No thread-local concerns (async handles concurrency)

Usage:
    db = await Database.create(config.get_postgres_dsn())
    cities = await db.get_all_cities()
    await db.close()
"""

import asyncpg
import json
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

from config import get_logger, config
from database.models import City, Meeting, AgendaItem, Matter
from exceptions import DatabaseConnectionError
from pipeline.models import QueueJob, MeetingJob, MatterJob

logger = get_logger(__name__).bind(component="database_postgres")


class Database:
    """Async PostgreSQL database with connection pooling

    This class replaces the SQLite UnifiedDatabase + 6 repositories
    with a single async interface.

    Connection Management:
    - Uses asyncpg connection pool (shared across requests)
    - Pool size: 10-100 connections (configurable)
    - Automatically handles connection lifecycle

    Topic Normalization:
    - Topics stored in separate tables (meeting_topics, item_topics, matter_topics)
    - Automatically handled in save/retrieve methods
    - Enables efficient topic filtering and indexing
    """

    pool: asyncpg.Pool

    def __init__(self, pool: asyncpg.Pool):
        """Initialize with existing connection pool

        Use Database.create() classmethod instead of direct instantiation.
        """
        self.pool = pool
        logger.info("database initialized", pool_size=f"{pool._minsize}-{pool._maxsize}")

    @classmethod
    async def create(
        cls,
        dsn: Optional[str] = None,
        min_size: int = 10,
        max_size: int = 100
    ) -> "Database":
        """Create database with connection pool

        Args:
            dsn: PostgreSQL connection string (defaults to config.get_postgres_dsn())
            min_size: Minimum pool size
            max_size: Maximum pool size

        Returns:
            Initialized Database instance

        Example:
            db = await Database.create()
            cities = await db.get_all_cities()
            await db.close()
        """
        if dsn is None:
            dsn = config.get_postgres_dsn()

        try:
            pool = await asyncpg.create_pool(
                dsn,
                min_size=min_size,
                max_size=max_size,
                command_timeout=60,
            )
            logger.info("connection pool created", min_size=min_size, max_size=max_size)
            return cls(pool)
        except Exception as e:
            logger.error("failed to create connection pool", error=str(e))
            raise DatabaseConnectionError(f"Failed to connect to PostgreSQL: {e}")

    async def close(self):
        """Close connection pool"""
        await self.pool.close()
        logger.info("connection pool closed")

    async def init_schema(self):
        """Initialize database schema from schema_postgres.sql

        Creates all tables, indexes, and constraints.
        Safe to call multiple times (uses IF NOT EXISTS).
        """
        schema_path = Path(__file__).parent / "schema_postgres.sql"
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        schema_sql = schema_path.read_text()

        async with self.pool.acquire() as conn:
            await conn.execute(schema_sql)

        logger.info("schema initialized")

    # ==================
    # CITY OPERATIONS
    # ==================

    async def add_city(self, city: City) -> None:
        """Add a city to the database

        Args:
            city: City object with banana, name, state, vendor, slug

        Raises:
            asyncpg.UniqueViolationError: If city already exists
        """
        async with self.pool.acquire() as conn:
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
            City object or None if not found
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
            zipcodes = [r["zipcode"] for r in zipcodes_rows]

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
            List of City objects
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
                zipcodes = [r["zipcode"] for r in zipcodes_rows]

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
                zipcodes = [r["zipcode"] for r in zipcodes_rows]

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
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
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

    # ==================
    # MEETING OPERATIONS
    # ==================

    async def store_meeting(self, meeting: Meeting) -> None:
        """Store or update a meeting

        Handles:
        - Meeting row (INSERT or UPDATE)
        - Topics normalization (meeting_topics table)
        - Participation JSONB storage

        Args:
            meeting: Meeting object
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Upsert meeting row
                await conn.execute(
                    """
                    INSERT INTO meetings (
                        id, banana, title, date, agenda_url, packet_url,
                        summary, participation, status, processing_status,
                        processing_method, processing_time
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    ON CONFLICT (id) DO UPDATE SET
                        title = EXCLUDED.title,
                        date = EXCLUDED.date,
                        agenda_url = EXCLUDED.agenda_url,
                        packet_url = EXCLUDED.packet_url,
                        summary = EXCLUDED.summary,
                        participation = EXCLUDED.participation,
                        status = EXCLUDED.status,
                        processing_status = EXCLUDED.processing_status,
                        processing_method = EXCLUDED.processing_method,
                        processing_time = EXCLUDED.processing_time,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    meeting.id,
                    meeting.banana,
                    meeting.title,
                    meeting.date,
                    meeting.agenda_url,
                    meeting.packet_url,
                    meeting.summary,
                    json.dumps(meeting.participation) if meeting.participation else None,
                    meeting.status,
                    meeting.processing_status or "pending",
                    meeting.processing_method,
                    meeting.processing_time,
                )

                # Handle topics (delete + insert for simplicity)
                if meeting.topics:
                    await conn.execute(
                        "DELETE FROM meeting_topics WHERE meeting_id = $1",
                        meeting.id,
                    )
                    for topic in meeting.topics:
                        await conn.execute(
                            """
                            INSERT INTO meeting_topics (meeting_id, topic)
                            VALUES ($1, $2)
                            ON CONFLICT DO NOTHING
                            """,
                            meeting.id,
                            topic,
                        )

        logger.info("meeting stored", meeting_id=meeting.id, banana=meeting.banana)

    async def get_meeting(self, meeting_id: str) -> Optional[Meeting]:
        """Get a meeting by ID

        Args:
            meeting_id: Meeting identifier

        Returns:
            Meeting object with denormalized topics, or None
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    id, banana, title, date, agenda_url, packet_url,
                    summary, participation, status, processing_status,
                    processing_method, processing_time, created_at, updated_at
                FROM meetings
                WHERE id = $1
                """,
                meeting_id,
            )

            if not row:
                return None

            # Fetch topics
            topic_rows = await conn.fetch(
                """
                SELECT topic
                FROM meeting_topics
                WHERE meeting_id = $1
                """,
                meeting_id,
            )
            topics = [r["topic"] for r in topic_rows]

            # Deserialize JSONB columns if needed (asyncpg sometimes returns as string)
            participation = row["participation"]
            if isinstance(participation, str):
                participation = json.loads(participation)

            return Meeting(
                id=row["id"],
                banana=row["banana"],
                title=row["title"],
                date=row["date"],
                agenda_url=row["agenda_url"],
                packet_url=row["packet_url"],
                summary=row["summary"],
                participation=participation,
                status=row["status"],
                processing_status=row["processing_status"],
                processing_method=row["processing_method"],
                processing_time=row["processing_time"],
                topics=topics,
            )

    async def get_meetings_for_city(
        self,
        banana: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Meeting]:
        """Get meetings for a city, ordered by date descending

        Args:
            banana: City banana
            limit: Maximum number of meetings to return
            offset: Number of meetings to skip

        Returns:
            List of Meeting objects with topics
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    id, banana, title, date, agenda_url, packet_url,
                    summary, participation, status, processing_status,
                    processing_method, processing_time
                FROM meetings
                WHERE banana = $1
                ORDER BY date DESC
                LIMIT $2 OFFSET $3
                """,
                banana,
                limit,
                offset,
            )

            meetings = []
            for row in rows:
                # Fetch topics for each meeting
                topic_rows = await conn.fetch(
                    """
                    SELECT topic
                    FROM meeting_topics
                    WHERE meeting_id = $1
                    """,
                    row["id"],
                )
                topics = [r["topic"] for r in topic_rows]

                # Deserialize JSONB columns if needed
                participation = row["participation"]
                if isinstance(participation, str):
                    participation = json.loads(participation)

                meetings.append(
                    Meeting(
                        id=row["id"],
                        banana=row["banana"],
                        title=row["title"],
                        date=row["date"],
                        agenda_url=row["agenda_url"],
                        packet_url=row["packet_url"],
                        summary=row["summary"],
                        participation=participation,
                        status=row["status"],
                        processing_status=row["processing_status"],
                        processing_method=row["processing_method"],
                        processing_time=row["processing_time"],
                        topics=topics,
                    )
                )

            return meetings

    async def get_meeting_by_packet_url(self, packet_url: str) -> Optional[Meeting]:
        """Get meeting by packet_url for cache optimization

        Used by processor.py to check if a packet has already been processed.

        Args:
            packet_url: The packet URL to look up

        Returns:
            Meeting object with denormalized topics, or None if not found
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    id, banana, title, date, agenda_url, packet_url,
                    summary, participation, status, processing_status,
                    processing_method, processing_time, created_at, updated_at
                FROM meetings
                WHERE packet_url = $1
                LIMIT 1
                """,
                packet_url,
            )

            if not row:
                return None

            # Fetch topics
            topic_rows = await conn.fetch(
                """
                SELECT topic
                FROM meeting_topics
                WHERE meeting_id = $1
                """,
                row["id"],
            )
            topics = [r["topic"] for r in topic_rows]

            # Deserialize JSONB columns if needed
            participation = row["participation"]
            if isinstance(participation, str):
                participation = json.loads(participation)

            return Meeting(
                id=row["id"],
                banana=row["banana"],
                title=row["title"],
                date=row["date"],
                agenda_url=row["agenda_url"],
                packet_url=row["packet_url"],
                summary=row["summary"],
                participation=participation,
                status=row["status"],
                processing_status=row["processing_status"],
                processing_method=row["processing_method"],
                processing_time=row["processing_time"],
                topics=topics,
            )

    # ==================
    # QUEUE OPERATIONS
    # ==================

    async def enqueue_job(
        self,
        source_url: str,
        job_type: str,
        payload: Dict[str, Any],
        meeting_id: Optional[str] = None,
        banana: Optional[str] = None,
        priority: int = 0,
    ) -> None:
        """Add job to processing queue

        Args:
            source_url: Unique identifier for job (used for deduplication)
            job_type: Type of job (e.g., "meeting", "item")
            payload: Job data (will be JSON-serialized)
            meeting_id: Associated meeting ID
            banana: Associated city banana
            priority: Job priority (higher = processed first)
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO queue (
                    source_url, meeting_id, banana, job_type, payload,
                    status, priority, retry_count
                )
                VALUES ($1, $2, $3, $4, $5, 'pending', $6, 0)
                ON CONFLICT (source_url) DO UPDATE SET
                    status = 'pending',
                    priority = EXCLUDED.priority,
                    retry_count = 0,
                    error_message = NULL,
                    failed_at = NULL
                """,
                source_url,
                meeting_id,
                banana,
                job_type,
                json.dumps(payload),
                priority,
            )

        logger.debug("job enqueued", source_url=source_url, job_type=job_type)

    async def get_next_job(self) -> Optional[Dict[str, Any]]:
        """Get next pending job from queue (highest priority first)

        Returns:
            Job dict with id, source_url, job_type, payload, etc., or None if queue empty
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Lock and fetch next job
                row = await conn.fetchrow(
                    """
                    SELECT id, source_url, meeting_id, banana, job_type, payload,
                           priority, retry_count
                    FROM queue
                    WHERE status = 'pending'
                    ORDER BY priority DESC, created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                    """
                )

                if not row:
                    return None

                # Mark as processing
                await conn.execute(
                    """
                    UPDATE queue
                    SET status = 'processing', started_at = CURRENT_TIMESTAMP
                    WHERE id = $1
                    """,
                    row["id"],
                )

                return {
                    "id": row["id"],
                    "source_url": row["source_url"],
                    "meeting_id": row["meeting_id"],
                    "banana": row["banana"],
                    "job_type": row["job_type"],
                    "payload": row["payload"],  # Already deserialized by asyncpg
                    "priority": row["priority"],
                    "retry_count": row["retry_count"],
                }

    async def mark_job_complete(self, queue_id: int) -> None:
        """Mark job as completed

        Args:
            queue_id: Queue entry ID
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE queue
                SET status = 'completed', completed_at = CURRENT_TIMESTAMP
                WHERE id = $1
                """,
                queue_id,
            )

        logger.debug("job completed", queue_id=queue_id)

    async def mark_job_failed(self, queue_id: int, error_message: str) -> None:
        """Mark job as failed

        Implements retry logic:
        - retry_count < 3: Increment retry, set status back to pending
        - retry_count >= 3: Set status to dead_letter

        Args:
            queue_id: Queue entry ID
            error_message: Error description
        """
        async with self.pool.acquire() as conn:
            # Get current retry count
            row = await conn.fetchrow(
                "SELECT retry_count FROM queue WHERE id = $1",
                queue_id,
            )

            if not row:
                return

            retry_count = row["retry_count"]

            if retry_count < 3:
                # Retry
                await conn.execute(
                    """
                    UPDATE queue
                    SET status = 'pending',
                        retry_count = retry_count + 1,
                        error_message = $2,
                        failed_at = NOW()
                    WHERE id = $1
                    """,
                    queue_id,
                    error_message,
                )
                logger.warning("job failed, retrying", queue_id=queue_id, retry_count=retry_count + 1)
            else:
                # Dead letter
                await conn.execute(
                    """
                    UPDATE queue
                    SET status = 'dead_letter',
                        retry_count = retry_count + 1,
                        error_message = $2,
                        failed_at = NOW()
                    WHERE id = $1
                    """,
                    queue_id,
                    error_message,
                )
                logger.error("job dead lettered", queue_id=queue_id, error=error_message)

    async def get_next_for_processing(
        self, banana: Optional[str] = None
    ) -> Optional[QueueJob]:
        """Get next typed job from processing queue based on priority and status

        Uses atomic UPDATE-RETURNING to prevent race conditions when multiple
        workers try to dequeue simultaneously.

        Args:
            banana: Optional city filter

        Returns:
            QueueJob object or None if queue empty
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Atomic SELECT-UPDATE using FOR UPDATE SKIP LOCKED
                if banana:
                    row = await conn.fetchrow(
                        """
                        SELECT id, source_url, meeting_id, banana, job_type, payload,
                               priority, retry_count, status, created_at, started_at
                        FROM queue
                        WHERE status = 'pending' AND banana = $1
                        ORDER BY priority DESC, created_at ASC
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                        """,
                        banana,
                    )
                else:
                    row = await conn.fetchrow(
                        """
                        SELECT id, source_url, meeting_id, banana, job_type, payload,
                               priority, retry_count, status, created_at, started_at
                        FROM queue
                        WHERE status = 'pending'
                        ORDER BY priority DESC, created_at ASC
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                        """
                    )

                if not row:
                    return None

                # Mark as processing
                await conn.execute(
                    """
                    UPDATE queue
                    SET status = 'processing', started_at = NOW()
                    WHERE id = $1
                    """,
                    row["id"],
                )

                # Parse payload JSON and reconstruct typed payload
                payload_data = json.loads(row["payload"]) if isinstance(row["payload"], str) else row["payload"]
                if row["job_type"] == "meeting":
                    payload = MeetingJob.from_dict(payload_data)
                elif row["job_type"] == "matter":
                    payload = MatterJob.from_dict(payload_data)
                else:
                    raise ValueError(f"Unknown job_type: {row['job_type']}")

                return QueueJob(
                    id=row["id"],
                    job_type=row["job_type"],
                    payload=payload,
                    banana=row["banana"],
                    priority=row["priority"],
                    status="processing",
                    retry_count=row.get("retry_count", 0),
                    error_message=None,
                    created_at=row.get("created_at"),
                    started_at=row.get("started_at")
                )

    async def mark_processing_complete(self, queue_id: int) -> None:
        """Mark a queue item as completed

        Args:
            queue_id: Queue job ID
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE queue
                SET status = 'completed', completed_at = NOW()
                WHERE id = $1
                """,
                queue_id,
            )

        logger.info("marked queue item as completed", queue_id=queue_id)

    async def mark_processing_failed(
        self, queue_id: int, error_message: str, increment_retry: bool = True
    ) -> None:
        """Mark a queue item as failed with smart retry logic

        Implements exponential backoff retry (3 attempts) before moving to DLQ.
        - retry_count < 3: Reset to 'pending' with lower priority
        - retry_count >= 3: Move to 'dead_letter' status

        Args:
            queue_id: Queue job ID
            error_message: Error description
            increment_retry: If False, mark as failed without retry logic
                           (used for non-retryable errors like "analyzer not available")
        """
        async with self.pool.acquire() as conn:
            if not increment_retry:
                # Non-retryable error - mark as failed without incrementing retry_count
                await conn.execute(
                    """
                    UPDATE queue
                    SET status = 'failed',
                        error_message = $2,
                        completed_at = NOW()
                    WHERE id = $1
                    """,
                    queue_id,
                    error_message,
                )
                logger.warning("marked queue item as failed (non-retryable)", queue_id=queue_id, error=error_message)
                return

            # Get current retry_count
            row = await conn.fetchrow(
                "SELECT retry_count, priority FROM queue WHERE id = $1",
                queue_id,
            )

            if not row:
                logger.error("queue item not found", queue_id=queue_id)
                return

            current_retry_count = row["retry_count"]
            current_priority = row["priority"]

            if current_retry_count < 2:  # Will be 3 after increment (0 -> 1 -> 2)
                # Retry with exponential backoff priority
                new_priority = current_priority - (20 * (current_retry_count + 1))

                await conn.execute(
                    """
                    UPDATE queue
                    SET status = 'pending',
                        priority = $2,
                        retry_count = retry_count + 1,
                        error_message = $3,
                        completed_at = NULL
                    WHERE id = $1
                    """,
                    queue_id,
                    new_priority,
                    error_message,
                )
                logger.warning(
                    f"Job {queue_id} retry scheduled (attempt {current_retry_count + 1}/3, "
                    f"priority {current_priority} -> {new_priority}): {error_message}"
                )
            else:
                # Move to dead letter queue
                await conn.execute(
                    """
                    UPDATE queue
                    SET status = 'dead_letter',
                        retry_count = retry_count + 1,
                        error_message = $2,
                        failed_at = NOW(),
                        completed_at = NOW()
                    WHERE id = $1
                    """,
                    queue_id,
                    error_message,
                )
                logger.error(
                    f"Job {queue_id} moved to dead letter queue after {current_retry_count + 1} failures: {error_message}"
                )

    # ==================
    # ITEM OPERATIONS
    # ==================

    async def store_agenda_items(self, meeting_id: str, items: List[AgendaItem]) -> int:
        """Store multiple agenda items (bulk insert)

        Signature matches SQLite ItemRepository.store_agenda_items() for compatibility.

        Handles:
        - Items table
        - Topic normalization (item_topics table)
        - Attachments JSONB storage

        Args:
            meeting_id: Meeting ID these items belong to (for API compatibility)
            items: List of AgendaItem objects (each already has meeting_id set)

        Returns:
            Number of items stored
        """
        if not items:
            return 0

        stored_count = 0

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for item in items:
                    # Upsert item row
                    await conn.execute(
                        """
                        INSERT INTO items (
                            id, meeting_id, title, sequence, attachments,
                            attachment_hash, matter_id, matter_file, matter_type,
                            agenda_number, sponsors, summary, topics
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                        ON CONFLICT (id) DO UPDATE SET
                            title = EXCLUDED.title,
                            sequence = EXCLUDED.sequence,
                            attachments = EXCLUDED.attachments,
                            attachment_hash = EXCLUDED.attachment_hash,
                            matter_id = EXCLUDED.matter_id,
                            matter_file = EXCLUDED.matter_file,
                            matter_type = EXCLUDED.matter_type,
                            agenda_number = EXCLUDED.agenda_number,
                            sponsors = EXCLUDED.sponsors,
                            summary = EXCLUDED.summary,
                            topics = EXCLUDED.topics
                        """,
                        item.id,
                        item.meeting_id,  # Use item's meeting_id (should match parameter)
                        item.title,
                        item.sequence,
                        json.dumps(item.attachments) if item.attachments else None,
                        item.attachment_hash,
                        item.matter_id,
                        item.matter_file,
                        item.matter_type,
                        item.agenda_number,
                        json.dumps(item.sponsors) if item.sponsors else None,
                        item.summary,
                        json.dumps(item.topics) if item.topics else None,
                    )
                    stored_count += 1

                    # Handle topics (normalize to item_topics table)
                    if item.topics:
                        # Delete existing topics for this item
                        await conn.execute(
                            "DELETE FROM item_topics WHERE item_id = $1",
                            item.id,
                        )
                        # Insert new topics
                        for topic in item.topics:
                            await conn.execute(
                                """
                                INSERT INTO item_topics (item_id, topic)
                                VALUES ($1, $2)
                                ON CONFLICT DO NOTHING
                                """,
                                item.id,
                                topic,
                            )

        logger.debug("stored agenda items", count=stored_count, meeting_id=meeting_id)
        return stored_count

    async def get_agenda_items(self, meeting_id: str, load_matters: bool = False) -> List[AgendaItem]:
        """Get all agenda items for a meeting

        Args:
            meeting_id: Meeting identifier
            load_matters: If True, eagerly load Matter objects for items

        Returns:
            List of AgendaItem objects with denormalized topics
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    id, meeting_id, title, sequence, attachments,
                    attachment_hash, matter_id, matter_file, matter_type,
                    agenda_number, sponsors, summary, topics
                FROM items
                WHERE meeting_id = $1
                ORDER BY sequence
                """,
                meeting_id,
            )

            items = []
            for row in rows:
                # Fetch topics from item_topics table
                topic_rows = await conn.fetch(
                    "SELECT topic FROM item_topics WHERE item_id = $1",
                    row["id"],
                )
                topics = [r["topic"] for r in topic_rows]

                # Defensive deserialization for JSONB columns (handles old string-stored data)
                attachments = row["attachments"]
                if isinstance(attachments, str):
                    attachments = json.loads(attachments)
                if attachments is None:
                    attachments = []

                sponsors = row["sponsors"]
                if isinstance(sponsors, str):
                    sponsors = json.loads(sponsors)
                if sponsors is None:
                    sponsors = []

                topics_jsonb = row["topics"]
                if isinstance(topics_jsonb, str):
                    topics_jsonb = json.loads(topics_jsonb)
                if topics_jsonb is None:
                    topics_jsonb = []

                items.append(
                    AgendaItem(
                        id=row["id"],
                        meeting_id=row["meeting_id"],
                        title=row["title"],
                        sequence=row["sequence"],
                        attachments=attachments,
                        attachment_hash=row["attachment_hash"],
                        matter_id=row["matter_id"],
                        matter_file=row["matter_file"],
                        matter_type=row["matter_type"],
                        agenda_number=row["agenda_number"],
                        sponsors=sponsors,
                        summary=row["summary"],
                        topics=topics or topics_jsonb,  # Prefer normalized, fallback to JSONB
                    )
                )

            return items

    async def update_agenda_item(
        self,
        item_id: str,
        summary: str = None,
        topics: List[str] = None,
        **kwargs
    ) -> None:
        """Update agenda item fields

        Supports both positional args and kwargs for backward compatibility:
        - update_agenda_item(item_id, summary, topics)
        - update_agenda_item(item_id, summary=..., topics=...)

        Args:
            item_id: Item identifier
            summary: Item summary text (optional)
            topics: Item topics list (optional)
            **kwargs: Additional fields to update
        """
        # Merge positional args into kwargs
        if summary is not None:
            kwargs["summary"] = summary
        if topics is not None:
            kwargs["topics"] = topics

        if not kwargs:
            return

        # Build dynamic UPDATE query
        set_clauses = []
        values = []
        param_num = 1

        for key, value in kwargs.items():
            if key == "topics":
                # Handle topics separately (normalize to item_topics table)
                continue
            set_clauses.append(f"{key} = ${param_num}")
            values.append(value)
            param_num += 1

        if set_clauses:
            values.append(item_id)  # WHERE clause parameter
            query = f"""
                UPDATE items
                SET {', '.join(set_clauses)}
                WHERE id = ${param_num}
            """

            async with self.pool.acquire() as conn:
                await conn.execute(query, *values)

        # Handle topics normalization
        if "topics" in kwargs and kwargs["topics"]:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    # Delete + insert for simplicity
                    await conn.execute(
                        "DELETE FROM item_topics WHERE item_id = $1",
                        item_id,
                    )
                    for topic in kwargs["topics"]:
                        await conn.execute(
                            """
                            INSERT INTO item_topics (item_id, topic)
                            VALUES ($1, $2)
                            ON CONFLICT DO NOTHING
                            """,
                            item_id,
                            topic,
                        )

        logger.debug("updated agenda item", item_id=item_id, fields=list(kwargs.keys()))

    async def get_agenda_item(self, item_id: str) -> Optional[AgendaItem]:
        """Get a single agenda item by ID

        Args:
            item_id: Item identifier

        Returns:
            AgendaItem object with denormalized topics, or None
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    id, meeting_id, title, sequence, attachments,
                    attachment_hash, matter_id, matter_file, matter_type,
                    agenda_number, sponsors, summary, topics
                FROM items
                WHERE id = $1
                """,
                item_id,
            )

            if not row:
                return None

            # Fetch topics from item_topics table
            topic_rows = await conn.fetch(
                "SELECT topic FROM item_topics WHERE item_id = $1",
                row["id"],
            )
            topics = [r["topic"] for r in topic_rows]

            # Defensive deserialization for JSONB columns
            attachments = row["attachments"]
            if isinstance(attachments, str):
                attachments = json.loads(attachments)
            if attachments is None:
                attachments = []

            sponsors = row["sponsors"]
            if isinstance(sponsors, str):
                sponsors = json.loads(sponsors)
            if sponsors is None:
                sponsors = []

            topics_jsonb = row["topics"]
            if isinstance(topics_jsonb, str):
                topics_jsonb = json.loads(topics_jsonb)
            if topics_jsonb is None:
                topics_jsonb = []

            return AgendaItem(
                id=row["id"],
                meeting_id=row["meeting_id"],
                title=row["title"],
                sequence=row["sequence"],
                attachments=attachments,
                attachment_hash=row["attachment_hash"],
                matter_id=row["matter_id"],
                matter_file=row["matter_file"],
                matter_type=row["matter_type"],
                agenda_number=row["agenda_number"],
                sponsors=sponsors,
                summary=row["summary"],
                topics=topics or topics_jsonb,  # Prefer normalized, fallback to JSONB
            )

    async def get_all_items_for_matter(self, matter_id: str) -> List[AgendaItem]:
        """Get ALL agenda items across ALL meetings for a given matter

        Used by processor for matter-based processing.

        Args:
            matter_id: Composite matter ID (e.g., "nashvilleTN_7a8f3b2c1d9e4f5a")

        Returns:
            List of ALL AgendaItem objects for this matter across all meetings
        """
        if not matter_id:
            return []

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    id, meeting_id, title, sequence, attachments,
                    attachment_hash, matter_id, matter_file, matter_type,
                    agenda_number, sponsors, summary, topics
                FROM items
                WHERE matter_id = $1
                ORDER BY meeting_id, sequence
                """,
                matter_id,
            )

            items = []
            for row in rows:
                # Fetch topics from item_topics table
                topic_rows = await conn.fetch(
                    "SELECT topic FROM item_topics WHERE item_id = $1",
                    row["id"],
                )
                topics = [r["topic"] for r in topic_rows]

                # Defensive deserialization for JSONB columns
                attachments = row["attachments"]
                if isinstance(attachments, str):
                    attachments = json.loads(attachments)
                if attachments is None:
                    attachments = []

                sponsors = row["sponsors"]
                if isinstance(sponsors, str):
                    sponsors = json.loads(sponsors)
                if sponsors is None:
                    sponsors = []

                topics_jsonb = row["topics"]
                if isinstance(topics_jsonb, str):
                    topics_jsonb = json.loads(topics_jsonb)
                if topics_jsonb is None:
                    topics_jsonb = []

                items.append(
                    AgendaItem(
                        id=row["id"],
                        meeting_id=row["meeting_id"],
                        title=row["title"],
                        sequence=row["sequence"],
                        attachments=attachments,
                        attachment_hash=row["attachment_hash"],
                        matter_id=row["matter_id"],
                        matter_file=row["matter_file"],
                        matter_type=row["matter_type"],
                        agenda_number=row["agenda_number"],
                        sponsors=sponsors,
                        summary=row["summary"],
                        topics=topics or topics_jsonb,  # Prefer normalized, fallback to JSONB
                    )
                )

            return items

    # ==================
    # MATTER OPERATIONS
    # ==================

    async def store_matter(self, matter: Matter) -> None:
        """Store or update a matter

        Handles:
        - city_matters table
        - Topic normalization (matter_topics table)
        - Attachments/sponsors JSONB storage

        Args:
            matter: Matter object
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Upsert matter row
                await conn.execute(
                    """
                    INSERT INTO city_matters (
                        id, banana, matter_id, matter_file, matter_type,
                        title, sponsors, canonical_summary, canonical_topics,
                        attachments, metadata, first_seen, last_seen,
                        appearance_count, status
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                    ON CONFLICT (id) DO UPDATE SET
                        matter_file = EXCLUDED.matter_file,
                        matter_type = EXCLUDED.matter_type,
                        title = EXCLUDED.title,
                        sponsors = EXCLUDED.sponsors,
                        canonical_summary = EXCLUDED.canonical_summary,
                        canonical_topics = EXCLUDED.canonical_topics,
                        attachments = EXCLUDED.attachments,
                        metadata = EXCLUDED.metadata,
                        last_seen = EXCLUDED.last_seen,
                        appearance_count = EXCLUDED.appearance_count,
                        status = EXCLUDED.status,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    matter.id,
                    matter.banana,
                    matter.matter_id,
                    matter.matter_file,
                    matter.matter_type,
                    matter.title,
                    json.dumps(matter.sponsors) if matter.sponsors else None,
                    matter.canonical_summary,
                    json.dumps(matter.canonical_topics) if matter.canonical_topics else None,
                    json.dumps(matter.attachments) if matter.attachments else None,
                    json.dumps(matter.metadata) if matter.metadata else None,
                    matter.first_seen,
                    matter.last_seen,
                    matter.appearance_count or 1,
                    matter.status or "active",
                )

                # Handle topics normalization
                if matter.canonical_topics:
                    await conn.execute(
                        "DELETE FROM matter_topics WHERE matter_id = $1",
                        matter.id,
                    )
                    for topic in matter.canonical_topics:
                        await conn.execute(
                            """
                            INSERT INTO matter_topics (matter_id, topic)
                            VALUES ($1, $2)
                            ON CONFLICT DO NOTHING
                            """,
                            matter.id,
                            topic,
                        )

        logger.debug("stored matter", matter_id=matter.id, banana=matter.banana)

    async def get_matter(self, matter_id: str) -> Optional[Matter]:
        """Get a matter by ID

        Args:
            matter_id: Matter identifier (composite hash including city_banana)

        Returns:
            Matter object or None
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    id, banana, matter_id, matter_file, matter_type,
                    title, sponsors, canonical_summary, canonical_topics,
                    attachments, metadata, first_seen, last_seen,
                    appearance_count, status, created_at, updated_at
                FROM city_matters
                WHERE id = $1
                """,
                matter_id,
            )

            if not row:
                return None

            # Fetch topics from matter_topics table
            topic_rows = await conn.fetch(
                "SELECT topic FROM matter_topics WHERE matter_id = $1",
                matter_id,
            )
            topics = [r["topic"] for r in topic_rows]

            return Matter(
                id=row["id"],
                banana=row["banana"],
                matter_id=row["matter_id"],
                matter_file=row["matter_file"],
                matter_type=row["matter_type"],
                title=row["title"],
                sponsors=row["sponsors"],
                canonical_summary=row["canonical_summary"],
                canonical_topics=topics or row["canonical_topics"],  # Prefer normalized
                attachments=row["attachments"],
                metadata=row["metadata"],
                first_seen=row["first_seen"],
                last_seen=row["last_seen"],
                appearance_count=row["appearance_count"],
                status=row["status"],
            )

    async def update_matter_summary(
        self,
        matter_id: str,
        canonical_summary: str,
        canonical_topics: List[str],
        attachment_hash: str
    ) -> None:
        """Update matter with canonical summary, topics, and attachment hash

        Args:
            matter_id: Composite matter ID
            canonical_summary: Deduplicated summary
            canonical_topics: Extracted topics
            attachment_hash: SHA256 hash of attachments
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Update matter row
                await conn.execute(
                    """
                    UPDATE city_matters
                    SET canonical_summary = $2,
                        metadata = COALESCE(metadata, '{}'::jsonb) || jsonb_build_object('attachment_hash', $3),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = $1
                    """,
                    matter_id,
                    canonical_summary,
                    attachment_hash,
                )

                # Update topics normalization
                if canonical_topics:
                    # Delete existing topics
                    await conn.execute(
                        "DELETE FROM matter_topics WHERE matter_id = $1",
                        matter_id,
                    )
                    # Insert new topics
                    for topic in canonical_topics:
                        await conn.execute(
                            """
                            INSERT INTO matter_topics (matter_id, topic)
                            VALUES ($1, $2)
                            ON CONFLICT DO NOTHING
                            """,
                            matter_id,
                            topic,
                        )

        logger.debug("updated matter with canonical summary", matter_id=matter_id)

    # ==================
    # FETCHER-SPECIFIC METHODS
    # ==================

    async def store_meeting_from_sync(
        self,
        meeting_dict: Dict[str, Any],
        city: City
    ) -> tuple[Optional[Meeting], Dict[str, Any]]:
        """Transform vendor meeting dict -> validate -> store -> enqueue

        This is the primary method called by the fetcher after scraping.
        Matches SQLite interface signature.

        Args:
            meeting_dict: Raw meeting dict from vendor adapter
            city: City object for this meeting

        Returns:
            Tuple of (stored Meeting object or None, stats dict)
        """
        stats = {
            'items_stored': 0,
            'items_skipped_procedural': 0,
            'matters_tracked': 0,
            'matters_duplicate': 0,
            'meetings_skipped': 0,
            'skip_reason': None,
            'skipped_title': None,
        }

        try:
            # Phase 1: Parse and validate
            meeting_date = self._parse_meeting_date(meeting_dict)
            meeting_id = meeting_dict.get("meeting_id")

            if not meeting_id or not meeting_id.strip():
                logger.error(
                    "adapter returned blank meeting_id",
                    city=city.banana,
                    meeting_title=meeting_dict.get('title', 'Unknown')
                )
                stats['meetings_skipped'] = 1
                stats['skip_reason'] = "missing_meeting_id"
                stats['skipped_title'] = meeting_dict.get("title", "Unknown")
                return None, stats

            # Phase 2: Create Meeting object
            meeting_obj = Meeting(
                id=meeting_id,
                banana=city.banana,
                title=meeting_dict.get("title", ""),
                date=meeting_date,
                agenda_url=meeting_dict.get("agenda_url"),
                packet_url=meeting_dict.get("packet_url"),
                summary=None,
                participation=meeting_dict.get("participation"),
                status=meeting_dict.get("meeting_status"),
                processing_status="pending",
            )

            # Preserve existing summary if already processed (don't overwrite on re-sync)
            existing_meeting = await self.get_meeting(meeting_obj.id)
            if existing_meeting and existing_meeting.summary:
                meeting_obj.summary = existing_meeting.summary
                meeting_obj.processing_status = existing_meeting.processing_status
                meeting_obj.processing_method = existing_meeting.processing_method
                meeting_obj.processing_time = existing_meeting.processing_time
                meeting_obj.topics = existing_meeting.topics
                logger.debug("preserved existing summary", title=meeting_obj.title)

            # Phase 3: Process agenda items (if present)
            agenda_items = []
            items_data = meeting_dict.get("items")
            if items_data:
                agenda_items = await self._process_agenda_items_async(
                    items_data, meeting_obj, stats
                )

            # Phase 4: Store meeting + items atomically
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    await self.store_meeting(meeting_obj)

                    if agenda_items:
                        stored_count = await self.store_agenda_items(meeting_obj.id, agenda_items)
                        stats['items_stored'] = stored_count

            # Phase 5: Enqueue for processing (if not already processed)
            await self._enqueue_if_needed_async(
                meeting_obj, meeting_date, agenda_items, items_data, stats
            )

            return meeting_obj, stats

        except Exception as e:
            import traceback
            logger.error(
                "unexpected error storing meeting",
                packet_url=meeting_dict.get('packet_url', 'unknown'),
                error=str(e),
                traceback=traceback.format_exc()
            )
            # Re-raise unexpected exceptions
            raise

    def _parse_meeting_date(self, meeting_dict: Dict[str, Any]) -> Optional[datetime]:
        """Parse date from adapter format, trying multiple formats"""
        meeting_date = None
        if meeting_dict.get("start"):
            date_str = meeting_dict["start"]
            # Try multiple date formats
            for fmt in [
                None,  # ISO format via fromisoformat
                "%m/%d/%y",  # NovusAgenda: "11/05/25"
                "%Y-%m-%d",  # Standard: "2025-11-05"
                "%m/%d/%Y",  # US format: "11/05/2025"
            ]:
                try:
                    if fmt is None:
                        meeting_date = datetime.fromisoformat(
                            date_str.replace("Z", "+00:00")
                        )
                    else:
                        meeting_date = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    continue

        return meeting_date

    async def _process_agenda_items_async(
        self,
        items_data: List[Dict[str, Any]],
        stored_meeting: Meeting,
        stats: Dict[str, Any]
    ) -> List[AgendaItem]:
        """Process agenda items: preserve summaries if already processed"""
        agenda_items = []

        # Build map of existing items to preserve summaries
        existing_items = await self.get_agenda_items(stored_meeting.id)
        existing_items_map = {item.id: item for item in existing_items}

        for item_data in items_data:
            item_id = f"{stored_meeting.id}_{item_data['item_id']}"

            # Parse attachments/sponsors
            item_attachments = item_data.get("attachments", [])
            sponsors = item_data.get("sponsors", [])

            agenda_item = AgendaItem(
                id=item_id,
                meeting_id=stored_meeting.id,
                title=item_data.get("title", ""),
                sequence=item_data.get("sequence", 0),
                attachments=item_attachments,
                attachment_hash=None,  # TODO: Compute hash for change detection
                matter_id=None,  # TODO: Matter tracking for PostgreSQL
                matter_file=item_data.get("matter_file"),
                matter_type=item_data.get("matter_type"),
                agenda_number=item_data.get("agenda_number"),
                sponsors=sponsors,
                summary=None,
                topics=None,
            )

            # Preserve existing summary if already processed
            if item_id in existing_items_map:
                existing_item = existing_items_map[item_id]
                if existing_item.summary:
                    agenda_item.summary = existing_item.summary
                if existing_item.topics:
                    agenda_item.topics = existing_item.topics

            agenda_items.append(agenda_item)

        return agenda_items

    async def _enqueue_if_needed_async(
        self,
        stored_meeting: Meeting,
        meeting_date: Optional[datetime],
        agenda_items: List[AgendaItem],
        items_data: Optional[List[Dict[str, Any]]],
        stats: Dict[str, Any]
    ):
        """Determine if meeting needs processing and enqueue appropriately"""
        has_items = bool(items_data)
        packet_url = stored_meeting.packet_url

        # Check if already processed
        skip_enqueue, skip_reason = self._should_skip_enqueue(
            agenda_items, stored_meeting, has_items
        )

        if skip_enqueue:
            logger.debug(
                "skipping enqueue",
                meeting_title=stored_meeting.title,
                reason=skip_reason
            )
            return

        if not (has_items or packet_url):
            logger.debug(
                "meeting has no agenda/packet/items - stored for display only",
                meeting_title=stored_meeting.title
            )
            return

        # Calculate priority based on meeting date proximity
        priority = self._calculate_priority_from_date(meeting_date)

        # Enqueue for processing
        source_url = stored_meeting.agenda_url or stored_meeting.packet_url or stored_meeting.id
        await self.enqueue_job(
            source_url=source_url,
            job_type="meeting",
            payload={"meeting_id": stored_meeting.id, "banana": stored_meeting.banana},
            meeting_id=stored_meeting.id,
            banana=stored_meeting.banana,
            priority=priority,
        )

        logger.debug(
            "enqueued for processing",
            meeting_title=stored_meeting.title,
            priority=priority
        )

    def _should_skip_enqueue(
        self,
        agenda_items: List[AgendaItem],
        stored_meeting: Meeting,
        has_items: bool
    ) -> tuple[bool, Optional[str]]:
        """Determine if meeting should skip enqueueing (already processed)"""
        # Priority 1: Check for item-level summaries (GOLDEN PATH)
        if has_items and agenda_items:
            items_with_summaries = [item for item in agenda_items if item.summary]
            # Skip only if 100% complete
            if items_with_summaries and len(items_with_summaries) == len(agenda_items):
                return True, f"all {len(agenda_items)} items already have summaries"

        # Priority 2: Check for monolithic summary (fallback path)
        if stored_meeting.summary:
            return True, "meeting already has summary (monolithic)"

        return False, None

    def _calculate_priority_from_date(self, meeting_date: Optional[datetime]) -> int:
        """Calculate priority based on meeting date proximity"""
        if meeting_date:
            # Handle timezone-aware dates from adapters
            now = datetime.now(meeting_date.tzinfo) if meeting_date.tzinfo else datetime.now()
            days_from_now = (meeting_date - now).days
            days_distance = abs(days_from_now)
        else:
            days_distance = 999

        return max(0, 150 - days_distance)

    async def get_city_last_sync(self, banana: str) -> Optional[datetime]:
        """Get timestamp of most recent meeting for a city

        Used by fetcher to determine if city needs syncing.

        Args:
            banana: City banana

        Returns:
            Datetime of most recent meeting, or None
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT MAX(date) as last_sync
                FROM meetings
                WHERE banana = $1
                """,
                banana,
            )

            return row["last_sync"] if row else None

    # ==================
    # PROCESSOR-SPECIFIC METHODS
    # ==================

    async def update_meeting_summary(
        self,
        meeting_id: str,
        summary: Optional[str],
        processing_method: str,
        processing_time: float,
        participation: Optional[Dict[str, Any]] = None,
        topics: Optional[List[str]] = None,
    ) -> None:
        """Update meeting summary and processing metadata

        Signature matches SQLite MeetingRepository.update_meeting_summary() for compatibility.

        Args:
            meeting_id: Meeting identifier
            summary: Generated summary text (can be None for item-level processing)
            processing_method: Processing method used
            processing_time: Time taken (seconds)
            participation: Optional participation data dict
            topics: Aggregated topics
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Update meeting
                await conn.execute(
                    """
                    UPDATE meetings
                    SET summary = $2,
                        processing_status = 'completed',
                        processing_method = $3,
                        processing_time = $4,
                        participation = $5,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = $1
                    """,
                    meeting_id,
                    summary,
                    processing_method,
                    processing_time,
                    json.dumps(participation) if participation else None,
                )

                # Update topics if provided (normalize to meeting_topics table)
                if topics:
                    # Delete + insert
                    await conn.execute(
                        "DELETE FROM meeting_topics WHERE meeting_id = $1",
                        meeting_id,
                    )
                    for topic in topics:
                        await conn.execute(
                            """
                            INSERT INTO meeting_topics (meeting_id, topic)
                            VALUES ($1, $2)
                            ON CONFLICT DO NOTHING
                            """,
                            meeting_id,
                            topic,
                        )

        logger.info("updated meeting summary", meeting_id=meeting_id, topic_count=len(topics) if topics else 0)

    # ==================
    # SEARCH OPERATIONS
    # ==================

    async def search_meetings_fulltext(
        self,
        query: str,
        banana: Optional[str] = None,
        limit: int = 50
    ) -> List[Meeting]:
        """Full-text search on meetings using PostgreSQL FTS

        Args:
            query: Search query
            banana: Optional city filter
            limit: Maximum results

        Returns:
            List of matching meetings
        """
        async with self.pool.acquire() as conn:
            if banana:
                rows = await conn.fetch(
                    """
                    SELECT
                        id, banana, title, date, agenda_url, packet_url,
                        summary, participation, status, processing_status,
                        processing_method, processing_time,
                        ts_rank(to_tsvector('english', COALESCE(title, '') || ' ' || COALESCE(summary, '')), plainto_tsquery('english', $1)) AS rank
                    FROM meetings
                    WHERE banana = $2
                      AND to_tsvector('english', COALESCE(title, '') || ' ' || COALESCE(summary, '')) @@ plainto_tsquery('english', $1)
                    ORDER BY rank DESC, date DESC
                    LIMIT $3
                    """,
                    query,
                    banana,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT
                        id, banana, title, date, agenda_url, packet_url,
                        summary, participation, status, processing_status,
                        processing_method, processing_time,
                        ts_rank(to_tsvector('english', COALESCE(title, '') || ' ' || COALESCE(summary, '')), plainto_tsquery('english', $1)) AS rank
                    FROM meetings
                    WHERE to_tsvector('english', COALESCE(title, '') || ' ' || COALESCE(summary, '')) @@ plainto_tsquery('english', $1)
                    ORDER BY rank DESC, date DESC
                    LIMIT $2
                    """,
                    query,
                    limit,
                )

            meetings = []
            for row in rows:
                # Fetch topics
                topic_rows = await conn.fetch(
                    "SELECT topic FROM meeting_topics WHERE meeting_id = $1",
                    row["id"],
                )
                topics = [r["topic"] for r in topic_rows]

                # Deserialize JSONB columns if needed
                participation = row["participation"]
                if isinstance(participation, str):
                    participation = json.loads(participation)

                meetings.append(
                    Meeting(
                        id=row["id"],
                        banana=row["banana"],
                        title=row["title"],
                        date=row["date"],
                        agenda_url=row["agenda_url"],
                        packet_url=row["packet_url"],
                        summary=row["summary"],
                        participation=participation,
                        status=row["status"],
                        processing_status=row["processing_status"],
                        processing_method=row["processing_method"],
                        processing_time=row["processing_time"],
                        topics=topics,
                    )
                )

            return meetings

    # ==================
    # STATS & MONITORING
    # ==================

    async def get_stats(self) -> dict:
        """Get database statistics for monitoring

        Returns format matching SQLite UnifiedDatabase for API compatibility:
        - active_cities: Count of cities with status='active'
        - total_meetings: Total meeting count
        - summarized_meetings: Meetings with summary
        - pending_meetings: Meetings with processing_status='pending'
        - summary_rate: Percentage string like "75.3%"
        """
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow("""
                SELECT
                    (SELECT COUNT(*) FROM cities WHERE status = 'active') as active_cities,
                    (SELECT COUNT(*) FROM meetings) as total_meetings,
                    (SELECT COUNT(*) FROM meetings WHERE summary IS NOT NULL) as summarized_meetings,
                    (SELECT COUNT(*) FROM meetings WHERE processing_status = 'pending') as pending_meetings
            """)

            stats = dict(result)

            # Calculate summary rate
            total = stats['total_meetings']
            summarized = stats['summarized_meetings']
            stats['summary_rate'] = f"{summarized / total * 100:.1f}%" if total > 0 else "0%"

            return stats

    async def get_queue_stats(self) -> dict:
        """Get queue statistics for Prometheus

        Returns format matching SQLite UnifiedDatabase for API compatibility:
        - {status}_count for each status (pending, processing, completed, failed, dead_letter)
        - avg_processing_seconds: Average processing time in seconds
        """
        async with self.pool.acquire() as conn:
            # Count by status
            status_rows = await conn.fetch("""
                SELECT status, COUNT(*) as count
                FROM queue
                GROUP BY status
            """)

            # Build stats dict with {status}_count keys
            stats = {}
            for row in status_rows:
                stats[f"{row['status']}_count"] = row['count']

            # Ensure all statuses have defaults
            for status in ['pending', 'processing', 'completed', 'failed', 'dead_letter']:
                stats.setdefault(f"{status}_count", 0)

            # Average processing time (completed jobs only)
            avg_row = await conn.fetchrow("""
                SELECT AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) as avg_seconds
                FROM queue
                WHERE status = 'completed'
                AND completed_at IS NOT NULL
                AND started_at IS NOT NULL
            """)

            stats['avg_processing_seconds'] = float(avg_row['avg_seconds']) if avg_row['avg_seconds'] else 0.0

            return stats

    async def get_random_meeting_with_items(self) -> Optional[Meeting]:
        """Get a random meeting that has items and a summary"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT m.*
                FROM meetings m
                WHERE m.summary IS NOT NULL
                AND EXISTS (SELECT 1 FROM items WHERE meeting_id = m.id)
                ORDER BY RANDOM()
                LIMIT 1
            """)

            if not row:
                return None

            # Parse participation
            participation = None
            if row["participation"]:
                if isinstance(row["participation"], str):
                    participation = json.loads(row["participation"])
                else:
                    participation = row["participation"]

            # Get topics
            topic_rows = await conn.fetch(
                "SELECT topic FROM meeting_topics WHERE meeting_id = $1",
                row["id"]
            )
            topics = [t["topic"] for t in topic_rows] if topic_rows else []

            return Meeting(
                id=row["id"],
                banana=row["banana"],
                title=row["title"],
                date=row["date"],
                agenda_url=row["agenda_url"],
                packet_url=row["packet_url"],
                summary=row["summary"],
                participation=participation,
                status=row["status"],
                processing_status=row["processing_status"],
                processing_method=row["processing_method"],
                processing_time=row["processing_time"],
                topics=topics,
            )

    # ==================
    # TOPIC SEARCH
    # ==================

    async def search_meetings_by_topic(
        self,
        topic: str,
        banana: Optional[str] = None,
        limit: int = 50
    ) -> List[Meeting]:
        """Search meetings by topic, optionally filtered by city"""
        async with self.pool.acquire() as conn:
            if banana:
                rows = await conn.fetch("""
                    SELECT DISTINCT m.*
                    FROM meetings m
                    JOIN meeting_topics mt ON m.id = mt.meeting_id
                    WHERE mt.topic = $1 AND m.banana = $2
                    ORDER BY m.date DESC
                    LIMIT $3
                """, topic, banana, limit)
            else:
                rows = await conn.fetch("""
                    SELECT DISTINCT m.*
                    FROM meetings m
                    JOIN meeting_topics mt ON m.id = mt.meeting_id
                    WHERE mt.topic = $1
                    ORDER BY m.date DESC
                    LIMIT $2
                """, topic, limit)

            meetings = []
            for row in rows:
                # Parse participation
                participation = None
                if row["participation"]:
                    if isinstance(row["participation"], str):
                        participation = json.loads(row["participation"])
                    else:
                        participation = row["participation"]

                # Get topics
                topic_rows = await conn.fetch(
                    "SELECT topic FROM meeting_topics WHERE meeting_id = $1",
                    row["id"]
                )
                topics = [t["topic"] for t in topic_rows] if topic_rows else []

                meetings.append(Meeting(
                    id=row["id"],
                    banana=row["banana"],
                    title=row["title"],
                    date=row["date"],
                    agenda_url=row["agenda_url"],
                    packet_url=row["packet_url"],
                    summary=row["summary"],
                    participation=participation,
                    status=row["status"],
                    processing_status=row["processing_status"],
                    processing_method=row["processing_method"],
                    processing_time=row["processing_time"],
                    topics=topics,
                ))

            return meetings

    async def get_items_by_topic(self, meeting_id: str, topic: str) -> List[AgendaItem]:
        """Get agenda items for a meeting filtered by topic"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT i.*
                FROM items i
                JOIN item_topics it ON i.id = it.item_id
                WHERE i.meeting_id = $1 AND it.topic = $2
                ORDER BY i.sequence
            """, meeting_id, topic)

            items = []
            for row in rows:
                # Parse JSON fields
                attachments = []
                if row["attachments"]:
                    if isinstance(row["attachments"], str):
                        attachments = json.loads(row["attachments"])
                    else:
                        attachments = row["attachments"]

                sponsors = []
                if row["sponsors"]:
                    if isinstance(row["sponsors"], str):
                        sponsors = json.loads(row["sponsors"])
                    else:
                        sponsors = row["sponsors"]

                # Get topics
                topic_rows = await conn.fetch(
                    "SELECT topic FROM item_topics WHERE item_id = $1",
                    row["id"]
                )
                topics = [t["topic"] for t in topic_rows] if topic_rows else []

                items.append(AgendaItem(
                    id=row["id"],
                    meeting_id=row["meeting_id"],
                    title=row["title"],
                    sequence=row["sequence"],
                    attachments=attachments,
                    summary=row["summary"],
                    topics=topics,
                    matter_id=row["matter_id"],
                    matter_file=row["matter_file"],
                    matter_type=row["matter_type"],
                    agenda_number=row["agenda_number"],
                    sponsors=sponsors,
                ))

            return items

    async def get_popular_topics(self, limit: int = 20) -> List[dict]:
        """Get most popular topics across all meetings"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT topic, COUNT(*) as count
                FROM meeting_topics
                GROUP BY topic
                ORDER BY count DESC
                LIMIT $1
            """, limit)

            return [{"topic": row["topic"], "count": row["count"]} for row in rows]

    # ==================
    # CACHE (STUB - Not Used in PostgreSQL)
    # ==================

    async def get_cached_summary(self, packet_url: str) -> Optional[dict]:
        """Get cached summary (stub for compatibility)"""
        # Cache table exists but isn't actively used in current flow
        # Return None to indicate no cache hit
        return None
