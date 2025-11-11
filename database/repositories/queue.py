"""
Queue Repository - Processing queue operations

Handles all job queue database operations including enqueueing,
dequeuing, status updates, and queue management.
"""

import logging
import sqlite3
from typing import Optional, Dict, Any, List
from datetime import datetime

from database.repositories.base import BaseRepository
from exceptions import DatabaseConnectionError
from pipeline.models import (
    QueueJob,
    MeetingJob,
    MatterJob,
    serialize_payload
)

logger = logging.getLogger("engagic")


class QueueRepository(BaseRepository):
    """Repository for processing queue operations"""

    def enqueue_meeting_job(
        self,
        meeting_id: str,
        source_url: str,
        banana: str,
        priority: int = 0,
    ) -> int:
        """Enqueue a meeting processing job (typed)

        Args:
            meeting_id: Meeting ID
            source_url: agenda_url or packet_url
            banana: City banana
            priority: Queue priority (higher = processed first)

        Returns:
            Queue ID or -1 if already exists
        """
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        payload = MeetingJob(meeting_id=meeting_id, source_url=source_url)
        payload_json = serialize_payload(payload)

        try:
            cursor = self._execute(
                """
                INSERT INTO queue
                (job_type, payload, meeting_id, banana, priority, source_url)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("meeting", payload_json, meeting_id, banana, priority, source_url),
            )
            self._commit()
            queue_id = cursor.lastrowid
            if queue_id is None:
                raise DatabaseConnectionError("Failed to get queue ID after insert")
            logger.info(
                f"Enqueued meeting job {meeting_id} for processing with priority {priority}"
            )
            return queue_id
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed" in str(e):
                logger.debug(f"Meeting job {meeting_id} already in queue")
                return -1
            raise

    def enqueue_matter_job(
        self,
        matter_id: str,
        meeting_id: str,
        item_ids: List[str],
        banana: str,
        priority: int = 0,
    ) -> int:
        """Enqueue a matter processing job (typed)

        Args:
            matter_id: Matter ID (composite: {banana}_{matter_key})
            meeting_id: Representative meeting ID
            item_ids: List of agenda item IDs for this matter
            banana: City banana
            priority: Queue priority (higher = processed first)

        Returns:
            Queue ID or -1 if already exists
        """
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        payload = MatterJob(matter_id=matter_id, meeting_id=meeting_id, item_ids=item_ids)
        payload_json = serialize_payload(payload)

        # Use matter_id as source_url for uniqueness constraint (backward compat)
        source_url = f"matters://{matter_id}"

        try:
            cursor = self._execute(
                """
                INSERT INTO queue
                (job_type, payload, meeting_id, banana, priority, source_url)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("matter", payload_json, meeting_id, banana, priority, source_url),
            )
            self._commit()
            queue_id = cursor.lastrowid
            if queue_id is None:
                raise DatabaseConnectionError("Failed to get queue ID after insert")
            logger.info(
                f"Enqueued matter job {matter_id} for processing with priority {priority}"
            )
            return queue_id
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed" in str(e):
                logger.debug(f"Matter job {matter_id} already in queue")
                return -1
            raise

    def enqueue_for_processing(
        self,
        source_url: str,
        meeting_id: str,
        banana: str,
        priority: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """DEPRECATED: Add source URL to processing queue with priority

        Use enqueue_meeting_job() or enqueue_matter_job() instead.

        This method is kept for backward compatibility during migration.
        It will route to the appropriate typed method based on source_url.

        Args:
            source_url: agenda_url, packet_url, or matters:// URL
            meeting_id: Meeting ID
            banana: City banana
            priority: Queue priority (higher = processed first)
            metadata: Optional processing metadata (used for matter jobs)
        """
        logger.warning("enqueue_for_processing is deprecated, use typed methods instead")

        # Route to appropriate typed method
        if source_url.startswith("matters://"):
            matter_id = source_url.replace("matters://", "")
            item_ids = metadata.get("item_ids", []) if metadata else []
            return self.enqueue_matter_job(
                matter_id=matter_id,
                meeting_id=meeting_id,
                item_ids=item_ids,
                banana=banana,
                priority=priority
            )
        else:
            return self.enqueue_meeting_job(
                meeting_id=meeting_id,
                source_url=source_url,
                banana=banana,
                priority=priority
            )

    def get_next_for_processing(
        self, banana: Optional[str] = None
    ) -> Optional[QueueJob]:
        """Get next typed job from processing queue based on priority and status

        Returns:
            QueueJob with discriminated union payload, or None if queue empty
        """
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        if banana:
            row = self._fetch_one(
                """
                SELECT * FROM queue
                WHERE status = 'pending' AND banana = ?
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
                """,
                (banana,),
            )
        else:
            row = self._fetch_one(
                """
                SELECT * FROM queue
                WHERE status = 'pending'
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
                """
            )

        if row:
            # Mark as processing
            self._execute(
                """
                UPDATE queue
                SET status = 'processing', started_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (row["id"],),
            )
            self._commit()

            # Convert to typed QueueJob
            try:
                return QueueJob.from_db_row(dict(row))
            except Exception as e:
                logger.error(f"Failed to deserialize queue job {row['id']}: {e}")
                # Mark as failed if deserialization fails
                self.mark_processing_failed(row['id'], f"Deserialization error: {e}")
                return None

        return None

    def mark_processing_complete(self, queue_id: int) -> None:
        """Mark a queue item as completed"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        self._execute(
            """
            UPDATE queue
            SET status = 'completed', completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (queue_id,),
        )
        self._commit()
        logger.info(f"Marked queue item {queue_id} as completed")

    def mark_processing_failed(
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

        Confidence: 9/10 - Standard retry pattern with DLQ
        """
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        if not increment_retry:
            # Non-retryable error - mark as failed without incrementing retry_count
            self._execute(
                """
                UPDATE queue
                SET status = 'failed',
                    error_message = ?,
                    completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (error_message, queue_id),
            )
            self._commit()
            logger.warning(f"Marked queue item {queue_id} as failed (non-retryable): {error_message}")
            return

        # Get current retry_count
        cursor = self._execute("SELECT retry_count, priority FROM queue WHERE id = ?", (queue_id,))
        row = cursor.fetchone()
        if not row:
            logger.error(f"Queue item {queue_id} not found")
            return

        current_retry_count = row['retry_count']
        current_priority = row['priority']

        if current_retry_count < 2:  # Will be 3 after increment (0 -> 1 -> 2)
            # Retry with exponential backoff priority
            # Priority decreases by 20 * (retry_count + 1)
            # This pushes failed jobs to back of queue
            new_priority = current_priority - (20 * (current_retry_count + 1))

            self._execute(
                """
                UPDATE queue
                SET status = 'pending',
                    priority = ?,
                    retry_count = retry_count + 1,
                    error_message = ?,
                    completed_at = NULL
                WHERE id = ?
                """,
                (new_priority, error_message, queue_id),
            )
            self._commit()
            logger.warning(
                f"Job {queue_id} retry scheduled (attempt {current_retry_count + 1}/3, "
                f"priority {current_priority} -> {new_priority}): {error_message}"
            )
        else:
            # Move to dead letter queue
            self._execute(
                """
                UPDATE queue
                SET status = 'dead_letter',
                    retry_count = retry_count + 1,
                    error_message = ?,
                    failed_at = CURRENT_TIMESTAMP,
                    completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (error_message, queue_id),
            )
            self._commit()
            logger.error(
                f"Job {queue_id} moved to dead letter queue after {current_retry_count + 1} failures: {error_message}"
            )

    def reset_failed_items(self, max_retries: int = 3) -> int:
        """Reset failed items back to pending if under retry limit"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        self._execute(
            """
            UPDATE queue
            SET status = 'pending', error_message = NULL
            WHERE status = 'failed' AND retry_count < ?
            """,
            (max_retries,),
        )
        reset_count = self.conn.cursor().rowcount
        self._commit()
        logger.info(f"Reset {reset_count} failed items back to pending")
        return reset_count

    def clear_queue(self) -> Dict[str, int]:
        """Clear all items from the queue (nuclear option)

        Returns:
            Dictionary with counts of items cleared by status
        """
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        # Get counts before clearing
        stats = self.get_queue_stats()

        self._execute("DELETE FROM queue")
        self._commit()

        logger.warning("Cleared entire processing queue")
        return {
            "pending": stats.get("pending_count", 0),
            "processing": stats.get("processing_count", 0),
            "completed": stats.get("completed_count", 0),
            "failed": stats.get("failed_count", 0),
        }

    def get_dead_letter_jobs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get jobs in the dead letter queue

        Args:
            limit: Maximum number of jobs to return

        Returns:
            List of dead letter jobs with error messages and timestamps
        """
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        rows = self._fetch_all(
            """
            SELECT id, source_url, meeting_id, banana, error_message,
                   retry_count, failed_at, created_at
            FROM queue
            WHERE status = 'dead_letter'
            ORDER BY failed_at DESC
            LIMIT ?
            """,
            (limit,)
        )

        return [dict(row) for row in rows]

    def get_queue_stats(self) -> Dict[str, Any]:
        """Get processing queue statistics

        Includes counts for all statuses (pending, processing, completed, failed, dead_letter)
        """
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        stats = {}

        # Count by status
        rows = self._fetch_all(
            """
            SELECT status, COUNT(*) as count
            FROM queue
            GROUP BY status
            """
        )
        for row in rows:
            stats[f"{row['status']}_count"] = row["count"]

        # Average processing time
        row = self._fetch_one(
            """
            SELECT AVG(julianday(completed_at) - julianday(started_at)) * 86400 as avg_seconds
            FROM queue
            WHERE status = 'completed' AND completed_at IS NOT NULL AND started_at IS NOT NULL
            """
        )
        avg_time = row["avg_seconds"] if row else None
        stats["avg_processing_seconds"] = avg_time if avg_time else 0

        return stats

    def bulk_enqueue_unprocessed_meetings(self, limit: Optional[int] = None) -> int:
        """Bulk enqueue all unprocessed meetings with packet URLs"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        # Find all meetings with packet URLs but no summaries
        query = """
            SELECT m.packet_url, m.id, m.banana, m.date
            FROM meetings m
            LEFT JOIN queue pq ON m.packet_url = pq.source_url
            WHERE m.packet_url IS NOT NULL
            AND m.summary IS NULL
            AND pq.id IS NULL
            ORDER BY m.date DESC
        """

        if limit:
            query += f" LIMIT {limit}"

        meetings = self._fetch_all(query)

        enqueued = 0
        for meeting in meetings:
            # Calculate priority based on meeting date proximity
            # Recent past + near future = HIGH priority
            # Far past + far future = LOW priority
            if meeting["date"]:
                try:
                    meeting_date = (
                        datetime.fromisoformat(meeting["date"])
                        if isinstance(meeting["date"], str)
                        else meeting["date"]
                    )
                    days_from_now = (meeting_date - datetime.now()).days
                    days_distance = abs(days_from_now)
                except Exception:
                    days_distance = 999
            else:
                days_distance = 999

            # Priority decreases as distance from today increases
            # Today: 150, Yesterday/Tomorrow: 149, 2 days: 148, etc.
            priority = max(0, 150 - days_distance)

            try:
                self._execute(
                    """
                    INSERT INTO queue
                    (source_url, meeting_id, banana, priority)
                    VALUES (?, ?, ?, ?)
                    """,
                    (meeting["packet_url"], meeting["id"], meeting["banana"], priority),
                )
                enqueued += 1
            except sqlite3.IntegrityError:
                logger.debug(f"Skipping already queued source: {meeting['packet_url']}")

        self._commit()
        logger.info(f"Bulk enqueued {enqueued} meetings for processing")
        return enqueued
