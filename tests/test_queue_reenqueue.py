"""
Regression tests for queue re-enqueue bug fix

Tests that completed/failed jobs can be re-enqueued with updated state,
and that pending/processing jobs return -1 without modification.

Run with: python -m unittest tests.test_queue_reenqueue
"""

import unittest
import tempfile
import os
from datetime import datetime

from database.db import UnifiedDatabase
from database.models import Meeting


class TestQueueReenqueue(unittest.TestCase):
    """Test suite for queue re-enqueue functionality"""

    def setUp(self):
        """Create temporary database for each test"""
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        # UnifiedDatabase __init__ automatically connects and initializes schema
        self.db = UnifiedDatabase(db_path=self.db_path)
        # Use the queue repository from the database instance
        self.queue = self.db.queue

    def tearDown(self):
        """Clean up temporary database"""
        self.db.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_reenqueue_completed_meeting_job(self):
        """Test that completed meeting jobs can be re-enqueued"""
        # Create test city first (required for foreign key)
        self.db.cities.add_city(
            banana="testcityCA",
            name="Test City",
            state="CA",
            vendor="test",
            slug="testcity",
        )

        # Create test meeting (required for foreign key)
        meeting = Meeting(
            id="meeting_123",
            date=datetime(2025, 1, 15),
            title="Test Meeting",
            banana="testcityCA",
            agenda_url="https://example.com/agenda.pdf",
        )
        self.db.meetings.store_meeting(meeting)

        # Enqueue initial job
        queue_id_1 = self.queue.enqueue_meeting_job(
            meeting_id="meeting_123",
            source_url="https://example.com/agenda.pdf",
            banana="testcityCA",
            priority=100,
        )
        self.assertNotEqual(queue_id_1, -1, "Initial enqueue should return valid queue_id")

        # Mark as completed
        self.queue.mark_processing_complete(queue_id_1)

        # Verify status is completed
        job = self.db.conn.execute(
            "SELECT status FROM queue WHERE id = ?", (queue_id_1,)
        ).fetchone()
        self.assertEqual(job["status"], "completed")

        # Re-enqueue with higher priority (simulating changed packet)
        queue_id_2 = self.queue.enqueue_meeting_job(
            meeting_id="meeting_123",
            source_url="https://example.com/agenda.pdf",
            banana="testcityCA",
            priority=200,  # Changed priority
        )

        # Should return same queue_id (UPSERT, not new insert)
        self.assertEqual(queue_id_1, queue_id_2, "Re-enqueue should return same queue_id")

        # Verify status reset to pending
        job = self.db.conn.execute(
            "SELECT status, priority, retry_count, error_message FROM queue WHERE id = ?",
            (queue_id_2,)
        ).fetchone()
        self.assertEqual(job["status"], "pending", "Status should be reset to pending")
        self.assertEqual(job["priority"], 200, "Priority should be updated")
        self.assertEqual(job["retry_count"], 0, "Retry count should be reset")
        self.assertIsNone(job["error_message"], "Error message should be cleared")

    def test_reenqueue_failed_matter_job(self):
        """Test that failed matter jobs can be re-enqueued with updated payload"""
        # Create test city and meeting (required for foreign keys)
        self.db.cities.add_city(
            banana="testcityCA",
            name="Test City",
            state="CA",
            vendor="test",
            slug="testcity",
        )
        meeting = Meeting(
            id="meeting_456",
            date=datetime(2025, 1, 16),
            title="Test Meeting 2",
            banana="testcityCA",
        )
        self.db.meetings.store_meeting(meeting)

        # Enqueue initial matter job
        queue_id_1 = self.queue.enqueue_matter_job(
            matter_id="testcityCA_matter_001",
            meeting_id="meeting_456",
            item_ids=["item_1", "item_2"],
            banana="testcityCA",
            priority=50,
        )
        self.assertNotEqual(queue_id_1, -1, "Initial enqueue should return valid queue_id")

        # Mark as failed
        self.queue.mark_processing_failed(queue_id_1, "Test error", increment_retry=False)

        # Verify status is failed
        job = self.db.conn.execute(
            "SELECT status FROM queue WHERE id = ?", (queue_id_1,)
        ).fetchone()
        self.assertEqual(job["status"], "failed")

        # Re-enqueue with updated item_ids (simulating changed attachments)
        queue_id_2 = self.queue.enqueue_matter_job(
            matter_id="testcityCA_matter_001",
            meeting_id="meeting_456",
            item_ids=["item_1", "item_2", "item_3"],  # Added item_3
            banana="testcityCA",
            priority=75,  # Changed priority
        )

        # Should return same queue_id
        self.assertEqual(queue_id_1, queue_id_2, "Re-enqueue should return same queue_id")

        # Verify status reset and payload updated
        job = self.db.conn.execute(
            "SELECT status, priority, payload, retry_count FROM queue WHERE id = ?",
            (queue_id_2,)
        ).fetchone()
        self.assertEqual(job["status"], "pending", "Status should be reset to pending")
        self.assertEqual(job["priority"], 75, "Priority should be updated")
        self.assertEqual(job["retry_count"], 0, "Retry count should be reset")
        self.assertIn("item_3", job["payload"], "Payload should include new item_3")

    def test_pending_job_not_reenqueued(self):
        """Test that pending jobs return -1 without modification"""
        # Create test city and meeting
        self.db.cities.add_city(
            banana="testcityCA",
            name="Test City",
            state="CA",
            vendor="test",
            slug="testcity",
        )
        meeting = Meeting(
            id="meeting_789",
            date=datetime(2025, 1, 17),
            title="Test Meeting 3",
            banana="testcityCA",
        )
        self.db.meetings.store_meeting(meeting)

        # Enqueue job
        queue_id_1 = self.queue.enqueue_meeting_job(
            meeting_id="meeting_789",
            source_url="https://example.com/packet.pdf",
            banana="testcityCA",
            priority=100,
        )
        self.assertNotEqual(queue_id_1, -1)

        # Try to enqueue again (job is still pending)
        queue_id_2 = self.queue.enqueue_meeting_job(
            meeting_id="meeting_789",
            source_url="https://example.com/packet.pdf",
            banana="testcityCA",
            priority=200,  # Different priority
        )

        # Should return -1 (no change)
        self.assertEqual(queue_id_2, -1, "Pending job should return -1")

        # Verify priority unchanged
        job = self.db.conn.execute(
            "SELECT priority FROM queue WHERE id = ?", (queue_id_1,)
        ).fetchone()
        self.assertEqual(job["priority"], 100, "Priority should not be updated")

    def test_processing_job_not_reenqueued(self):
        """Test that processing jobs return -1 without modification"""
        # Create test city and meeting
        self.db.cities.add_city(
            banana="testcityCA",
            name="Test City",
            state="CA",
            vendor="test",
            slug="testcity",
        )
        meeting = Meeting(
            id="meeting_999",
            date=datetime(2025, 1, 18),
            title="Test Meeting 4",
            banana="testcityCA",
        )
        self.db.meetings.store_meeting(meeting)

        # Enqueue and start processing
        queue_id_1 = self.queue.enqueue_meeting_job(
            meeting_id="meeting_999",
            source_url="https://example.com/agenda.pdf",
            banana="testcityCA",
            priority=100,
        )
        self.assertNotEqual(queue_id_1, -1)

        # Mark as processing
        self.db.conn.execute(
            "UPDATE queue SET status = 'processing' WHERE id = ?", (queue_id_1,)
        )
        self.db.conn.commit()

        # Try to enqueue again
        queue_id_2 = self.queue.enqueue_meeting_job(
            meeting_id="meeting_999",
            source_url="https://example.com/agenda.pdf",
            banana="testcityCA",
            priority=200,
        )

        # Should return -1 (no change)
        self.assertEqual(queue_id_2, -1, "Processing job should return -1")

        # Verify status still processing
        job = self.db.conn.execute(
            "SELECT status, priority FROM queue WHERE id = ?", (queue_id_1,)
        ).fetchone()
        self.assertEqual(job["status"], "processing", "Status should remain processing")
        self.assertEqual(job["priority"], 100, "Priority should not be updated")

    def test_enqueue_matters_first_counts_correctly(self):
        """Test that enqueue methods correctly handle already-pending jobs

        This is a simplified integration test that verifies the fix works
        end-to-end without testing internal implementation details.
        """
        # Create test city and meeting
        self.db.cities.add_city(
            banana="testcityCA",
            name="Test City",
            state="CA",
            vendor="test",
            slug="testcity",
        )
        meeting = Meeting(
            id="meeting_001",
            date=datetime(2025, 1, 15),
            title="Test Meeting",
            banana="testcityCA",
        )
        self.db.meetings.store_meeting(meeting)

        # Enqueue a matter job
        queue_id_1 = self.queue.enqueue_matter_job(
            matter_id="testcityCA_matter_001",
            meeting_id="meeting_001",
            item_ids=["item_1", "item_2"],
            banana="testcityCA",
            priority=100,
        )
        self.assertNotEqual(queue_id_1, -1, "Initial enqueue should return valid queue_id")

        # Try to enqueue the same matter again (still pending)
        queue_id_2 = self.queue.enqueue_matter_job(
            matter_id="testcityCA_matter_001",
            meeting_id="meeting_001",
            item_ids=["item_1", "item_2"],
            banana="testcityCA",
            priority=100,
        )
        self.assertEqual(queue_id_2, -1, "Second enqueue (pending) should return -1")

        # Mark matter as completed
        self.queue.mark_processing_complete(queue_id_1)

        # Try to enqueue again (now completed, should allow re-enqueue)
        queue_id_3 = self.queue.enqueue_matter_job(
            matter_id="testcityCA_matter_001",
            meeting_id="meeting_001",
            item_ids=["item_1", "item_2", "item_3"],  # Updated item_ids
            banana="testcityCA",
            priority=150,  # Updated priority
        )
        self.assertEqual(queue_id_1, queue_id_3, "Re-enqueue should return same queue_id")

        # Verify job was reset to pending with updated data
        job = self.db.conn.execute(
            "SELECT status, priority, payload FROM queue WHERE id = ?",
            (queue_id_3,)
        ).fetchone()
        self.assertEqual(job["status"], "pending", "Status should be reset to pending")
        self.assertEqual(job["priority"], 150, "Priority should be updated")
        self.assertIn("item_3", job["payload"], "Payload should include updated item_ids")


if __name__ == "__main__":
    unittest.main()
