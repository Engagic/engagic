"""
Test suite for MeetingRepository

Tests meeting repository operations including upsert behavior,
timestamp management, and data persistence.

Run with: python -m unittest tests.test_meeting_repository
"""

import unittest
import tempfile
import os
import time
from datetime import datetime

from database.db import UnifiedDatabase
from database.models import Meeting


class TestMeetingRepository(unittest.TestCase):
    """Test suite for MeetingRepository timestamp and upsert behavior"""

    def setUp(self):
        """Create temporary database for each test"""
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.db = UnifiedDatabase(db_path=self.db_path)

        # Create test city (required for foreign key)
        self.db.cities.add_city(
            banana="testcityCA",
            name="Test City",
            state="CA",
            vendor="test",
            slug="testcity",
        )

    def tearDown(self):
        """Clean up temporary database"""
        self.db.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_initial_insert_sets_updated_at(self):
        """Test that initial meeting insert sets updated_at timestamp"""
        meeting = Meeting(
            id="meeting_001",
            date=datetime(2025, 11, 15),
            title="Initial Meeting",
            banana="testcityCA",
            agenda_url="https://example.com/agenda1.html",
        )

        stored = self.db.meetings.store_meeting(meeting)

        self.assertIsNotNone(stored.updated_at, "updated_at should be set on insert")
        self.assertIsNotNone(stored.created_at, "created_at should be set on insert")

    def test_upsert_bumps_updated_at_on_change(self):
        """
        Test that upserting a meeting with changed data bumps updated_at.

        This is the critical test for the bug fix: sync heuristics rely on
        updated_at to detect changes. If updated_at doesn't bump, sync logic
        may skip re-processing meetings that actually changed.
        """
        # Initial insert
        meeting = Meeting(
            id="meeting_002",
            date=datetime(2025, 11, 15),
            title="Original Title",
            banana="testcityCA",
            agenda_url="https://example.com/agenda_v1.html",
        )
        stored_v1 = self.db.meetings.store_meeting(meeting)
        first_updated_at = stored_v1.updated_at

        # Wait to ensure timestamp difference (SQLite CURRENT_TIMESTAMP has second precision)
        time.sleep(1.1)

        # Upsert with changed title and agenda_url
        meeting.title = "Updated Title"
        meeting.agenda_url = "https://example.com/agenda_v2.html"
        stored_v2 = self.db.meetings.store_meeting(meeting)
        second_updated_at = stored_v2.updated_at

        # Assert updated_at was bumped
        self.assertIsNotNone(second_updated_at, "updated_at should exist after upsert")
        self.assertGreater(
            second_updated_at,
            first_updated_at,
            "updated_at must bump on upsert to track changes for sync heuristics",
        )

        # Assert created_at unchanged
        self.assertEqual(
            stored_v2.created_at,
            stored_v1.created_at,
            "created_at should not change on upsert",
        )

        # Assert data actually updated
        self.assertEqual(stored_v2.title, "Updated Title")
        self.assertEqual(stored_v2.agenda_url, "https://example.com/agenda_v2.html")

    def test_multiple_upserts_continue_bumping_updated_at(self):
        """Test that multiple consecutive upserts continue to bump updated_at"""
        meeting = Meeting(
            id="meeting_003",
            date=datetime(2025, 11, 15),
            title="Version 1",
            banana="testcityCA",
        )

        # Version 1
        v1 = self.db.meetings.store_meeting(meeting)
        time.sleep(1.1)

        # Version 2
        meeting.title = "Version 2"
        v2 = self.db.meetings.store_meeting(meeting)
        time.sleep(1.1)

        # Version 3
        meeting.title = "Version 3"
        v3 = self.db.meetings.store_meeting(meeting)

        # Assert monotonically increasing updated_at
        self.assertGreater(v2.updated_at, v1.updated_at, "V2 updated_at > V1")
        self.assertGreater(v3.updated_at, v2.updated_at, "V3 updated_at > V2")

        # Assert created_at unchanged across all versions
        self.assertEqual(v3.created_at, v1.created_at, "created_at stays constant")

    def test_upsert_with_null_fields_preserves_updated_at_bump(self):
        """
        Test that upserts bump updated_at even when some fields are NULL.

        This ensures sync heuristics detect changes even for partial updates
        (e.g., agenda_url changes but summary stays NULL).
        """
        # Insert with agenda_url only
        meeting = Meeting(
            id="meeting_004",
            date=datetime(2025, 11, 15),
            title="Meeting with Agenda",
            banana="testcityCA",
            agenda_url="https://example.com/agenda.html",
            summary=None,  # No summary yet
        )
        v1 = self.db.meetings.store_meeting(meeting)
        time.sleep(1.1)

        # Upsert with changed agenda_url (summary still NULL)
        meeting.agenda_url = "https://example.com/agenda_updated.html"
        v2 = self.db.meetings.store_meeting(meeting)

        self.assertGreater(
            v2.updated_at,
            v1.updated_at,
            "updated_at should bump even when summary is NULL",
        )
        self.assertIsNone(v2.summary, "summary should remain NULL")
        self.assertEqual(v2.agenda_url, "https://example.com/agenda_updated.html")

    def test_upsert_preserves_existing_summary_when_null(self):
        """
        Test that upserts preserve existing summary/topics when new values are NULL.

        This verifies the CASE WHEN logic works correctly while still bumping updated_at.
        """
        # Insert with summary
        meeting = Meeting(
            id="meeting_005",
            date=datetime(2025, 11, 15),
            title="Processed Meeting",
            banana="testcityCA",
            summary="Original summary",
            topics=["Housing", "Transportation"],
        )
        v1 = self.db.meetings.store_meeting(meeting)
        time.sleep(1.1)

        # Upsert with NULL summary/topics (simulating re-fetch from vendor)
        meeting.summary = None
        meeting.topics = None
        meeting.title = "Updated Title"  # But change title
        v2 = self.db.meetings.store_meeting(meeting)

        # Assert summary/topics preserved
        self.assertEqual(
            v2.summary,
            "Original summary",
            "summary should be preserved when new value is NULL",
        )
        self.assertEqual(
            v2.topics,
            ["Housing", "Transportation"],
            "topics should be preserved when new value is NULL",
        )

        # Assert title updated and updated_at bumped
        self.assertEqual(v2.title, "Updated Title")
        self.assertGreater(
            v2.updated_at,
            v1.updated_at,
            "updated_at should bump even when preserving summary/topics",
        )


if __name__ == "__main__":
    unittest.main()
