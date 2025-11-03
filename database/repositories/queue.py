"""
Queue Repository - Processing queue operations

Handles all job queue database operations including enqueueing,
dequeuing, status updates, and queue management.
"""

import logging
import json
import sqlite3
from typing import Optional, Dict, Any
from datetime import datetime

from database.repositories.base import BaseRepository
from database.models import DatabaseConnectionError

logger = logging.getLogger("engagic")


class QueueRepository(BaseRepository):
    """Repository for processing queue operations"""

    def enqueue_for_processing(
        self,
        source_url: str,
        meeting_id: str,
        banana: str,
        priority: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Add source URL to processing queue with priority

        Args:
            source_url: agenda_url, packet_url, or items:// synthetic URL
            meeting_id: Meeting ID
            banana: City banana
            priority: Queue priority (higher = processed first)
            metadata: Optional processing metadata
        """
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        metadata_json = json.dumps(metadata) if metadata else None

        try:
            cursor = self._execute(
                """
                INSERT INTO queue
                (source_url, meeting_id, banana, priority, processing_metadata)
                VALUES (?, ?, ?, ?, ?)
                """,
                (source_url, meeting_id, banana, priority, metadata_json),
            )
            self._commit()
            queue_id = cursor.lastrowid
            if queue_id is None:
                raise DatabaseConnectionError("Failed to get queue ID after insert")
            logger.info(
                f"Enqueued {source_url} for processing with priority {priority}"
            )
            return queue_id
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed" in str(e):
                logger.debug(f"Source {source_url} already in queue")
                return -1
            raise

    def get_next_for_processing(
        self, banana: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get next item from processing queue based on priority and status"""
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

            result = dict(row)
            if result.get("processing_metadata"):
                result["processing_metadata"] = json.loads(
                    result["processing_metadata"]
                )
            return result
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
        """Mark a queue item as failed with error message"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        if increment_retry:
            self._execute(
                """
                UPDATE queue
                SET status = 'failed',
                    error_message = ?,
                    retry_count = retry_count + 1,
                    completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (error_message, queue_id),
            )
        else:
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
        logger.warning(f"Marked queue item {queue_id} as failed: {error_message}")

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

    def get_queue_stats(self) -> Dict[str, Any]:
        """Get processing queue statistics"""
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

        # Failed with high retry count
        row = self._fetch_one(
            """
            SELECT COUNT(*) as count
            FROM queue
            WHERE status = 'failed' AND retry_count >= 3
            """
        )
        stats["permanently_failed"] = row["count"] if row else 0

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
