"""
Regression tests for store_meeting_from_sync skip handling.

Verifies we record structured metadata whenever a meeting is skipped
so the fetcher can continue processing the remaining meetings.
"""

import os
import tempfile
import unittest

from database.db import UnifiedDatabase


class TestStoreMeetingFromSync(unittest.TestCase):
    """Ensure meeting ingestion reports skip metadata instead of failing."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.db = UnifiedDatabase(db_path=self.db_path)
        self.city = self.db.add_city(
            banana="testcityCA",
            name="Test City",
            state="CA",
            vendor="legistar",
            slug="testcity",
        )

    def tearDown(self):
        self.db.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_missing_meeting_id_marks_skip(self):
        """Meetings without IDs should be skipped with context."""
        meeting_dict = {
            "title": "No ID meeting",
            "packet_url": "https://legistar.granicus.com/testcity/packet.pdf",
            "agenda_url": "https://legistar.granicus.com/testcity/agenda.html",
        }

        stored, stats = self.db.store_meeting_from_sync(meeting_dict, self.city)

        self.assertIsNone(stored)
        self.assertEqual(stats.get("meetings_skipped"), 1)
        self.assertEqual(stats.get("skip_reason"), "missing_meeting_id")
        self.assertEqual(stats.get("skipped_title"), "No ID meeting")

    def test_invalid_url_validation_marks_skip(self):
        """Invalid packet/agenda URLs should be detected and skipped."""
        meeting_dict = {
            "meeting_id": "bad_url_001",
            "title": "Bad URL Meeting",
            "packet_url": "https://attacker.com/malware.pdf",
            "agenda_url": "https://legistar.granicus.com/testcity/agenda.html",
        }

        stored, stats = self.db.store_meeting_from_sync(meeting_dict, self.city)

        self.assertIsNone(stored)
        self.assertEqual(stats.get("meetings_skipped"), 1)
        self.assertEqual(stats.get("skip_reason"), "url_validation")
        self.assertEqual(stats.get("skipped_title"), "Bad URL Meeting")


if __name__ == "__main__":
    unittest.main()
