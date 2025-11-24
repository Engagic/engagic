#!/usr/bin/env python3
"""
PostgreSQL Edge Case Tests

Tests edge cases, NULL handling, JSONB validation, and matter deduplication
to ensure production robustness.

Run with:
    ENGAGIC_USE_POSTGRES=true python tests/test_postgres_edge_cases.py
"""

import asyncio
import sys
import os
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_postgres import Database
from database.models import Meeting, AgendaItem, Matter
from config import config, get_logger

logger = get_logger(__name__)


class EdgeCaseTests:
    """Edge case test suite for PostgreSQL migration"""

    def __init__(self, db: Database):
        self.db = db
        self.passed = 0
        self.failed = 0

    def _log_test(self, test_name: str, passed: bool, message: str = ""):
        """Log test result"""
        if passed:
            self.passed += 1
            print(f"✅ PASS | {test_name}")
            if message:
                print(f"         {message}")
        else:
            self.failed += 1
            print(f"❌ FAIL | {test_name}")
            if message:
                print(f"         {message}")

    async def test_meeting_null_date(self):
        """Test meeting with NULL date"""
        test_name = "Meeting with NULL date"

        try:
            meeting = Meeting(
                id="test_null_date",
                banana="testCA",
                title="Test Meeting",
                date=None,
                source_url="https://test.com",
            )

            await self.db.meetings.store_meeting(meeting)
            retrieved = await self.db.meetings.get_meeting("test_null_date")

            if retrieved and retrieved.date is None:
                self._log_test(test_name, True, "NULL date handled correctly")
            else:
                self._log_test(test_name, False, f"Expected NULL date, got {retrieved.date if retrieved else 'None'}")

        except Exception as e:
            self._log_test(test_name, False, f"Exception: {e}")

    async def test_item_empty_attachments(self):
        """Test item with empty attachments list"""
        test_name = "Item with empty attachments"

        try:
            # First create a meeting
            meeting = Meeting(
                id="test_meeting_empty_attach",
                banana="testCA",
                title="Test Meeting",
                date=datetime.now(),
                source_url="https://test.com",
            )
            await self.db.meetings.store_meeting(meeting)

            item = AgendaItem(
                id="test_empty_attach",
                meeting_id="test_meeting_empty_attach",
                title="Test Item",
                attachments=[],  # Empty list
                sponsors=[],     # Empty list
            )

            await self.db.items.store_agenda_items("test_meeting_empty_attach", [item])
            retrieved = await self.db.items.get_agenda_item("test_empty_attach")

            if retrieved and retrieved.attachments == []:
                self._log_test(test_name, True, "Empty attachments handled correctly")
            else:
                self._log_test(test_name, False, f"Expected empty list, got {retrieved.attachments if retrieved else 'None'}")

        except Exception as e:
            self._log_test(test_name, False, f"Exception: {e}")

    async def test_item_null_fields(self):
        """Test item with NULL optional fields"""
        test_name = "Item with NULL optional fields"

        try:
            # Create meeting first
            meeting = Meeting(
                id="test_meeting_null_fields",
                banana="testCA",
                title="Test Meeting",
                date=datetime.now(),
                source_url="https://test.com",
            )
            await self.db.meetings.store_meeting(meeting)

            item = AgendaItem(
                id="test_null_fields",
                meeting_id="test_meeting_null_fields",
                title="Test Item",
                attachments=None,
                sponsors=None,
                matter_id=None,
                matter_file=None,
                summary=None,
                topics=None,
            )

            await self.db.items.store_agenda_items("test_meeting_null_fields", [item])
            retrieved = await self.db.items.get_agenda_item("test_null_fields")

            if retrieved:
                self._log_test(test_name, True, "NULL optional fields handled correctly")
            else:
                self._log_test(test_name, False, "Failed to retrieve item with NULL fields")

        except Exception as e:
            self._log_test(test_name, False, f"Exception: {e}")

    async def test_meeting_empty_topics(self):
        """Test meeting with empty topics list"""
        test_name = "Meeting with empty topics"

        try:
            meeting = Meeting(
                id="test_empty_topics",
                banana="testCA",
                title="Test Meeting",
                date=datetime.now(),
                source_url="https://test.com",
                topics=[],  # Empty topics
            )

            await self.db.meetings.store_meeting(meeting)
            retrieved = await self.db.meetings.get_meeting("test_empty_topics")

            # Check that no topic rows were created
            async with self.db.pool.acquire() as conn:
                topic_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM meeting_topics WHERE meeting_id = $1",
                    "test_empty_topics"
                )

            if retrieved and topic_count == 0:
                self._log_test(test_name, True, "Empty topics handled correctly")
            else:
                self._log_test(test_name, False, f"Expected 0 topics, found {topic_count}")

        except Exception as e:
            self._log_test(test_name, False, f"Exception: {e}")

    async def test_topic_deduplication(self):
        """Test that duplicate topics are deduplicated"""
        test_name = "Topic deduplication"

        try:
            meeting = Meeting(
                id="test_topic_dedup",
                banana="testCA",
                title="Test Meeting",
                date=datetime.now(),
                source_url="https://test.com",
                topics=["Housing", "Housing", "Zoning"],  # Duplicate "Housing"
            )

            await self.db.meetings.store_meeting(meeting)

            # Check topic count
            async with self.db.pool.acquire() as conn:
                topics = await conn.fetch(
                    "SELECT topic FROM meeting_topics WHERE meeting_id = $1 ORDER BY topic",
                    "test_topic_dedup"
                )

            topic_list = [row["topic"] for row in topics]

            # Should have 2 unique topics, not 3
            if len(topic_list) == 2 and topic_list == ["Housing", "Zoning"]:
                self._log_test(test_name, True, "Duplicate topics deduplicated correctly")
            else:
                self._log_test(test_name, False, f"Expected 2 unique topics, got {len(topic_list)}: {topic_list}")

        except Exception as e:
            self._log_test(test_name, False, f"Exception: {e}")

    async def test_matter_deduplication(self):
        """Test that same matter across meetings uses canonical summary"""
        test_name = "Matter deduplication"

        try:
            # Create two meetings
            meeting1 = Meeting(
                id="test_matter_meeting1",
                banana="testCA",
                title="Meeting 1",
                date=datetime.now(),
                source_url="https://test1.com",
            )
            meeting2 = Meeting(
                id="test_matter_meeting2",
                banana="testCA",
                title="Meeting 2",
                date=datetime.now(),
                source_url="https://test2.com",
            )

            await self.db.meetings.store_meeting(meeting1)
            await self.db.meetings.store_meeting(meeting2)

            # Create matter
            matter = Matter(
                id="test_matter_dedup",
                banana="testCA",
                matter_file="BL2025-TEST",
                title="Test Ordinance",
                canonical_summary="This is the canonical summary",
                canonical_topics=["Housing"],
            )
            await self.db.matters.store_matter(matter)

            # Create items in both meetings referencing same matter
            item1 = AgendaItem(
                id="test_matter_item1",
                meeting_id="test_matter_meeting1",
                title="First Reading - Test Ordinance",
                matter_id="test_matter_dedup",
                matter_file="BL2025-TEST",
            )
            item2 = AgendaItem(
                id="test_matter_item2",
                meeting_id="test_matter_meeting2",
                title="Second Reading - Test Ordinance",
                matter_id="test_matter_dedup",
                matter_file="BL2025-TEST",
            )

            await self.db.items.store_agenda_items("test_matter_meeting1", [item1])
            await self.db.items.store_agenda_items("test_matter_meeting2", [item2])

            # Verify matter appears in both meetings
            async with self.db.pool.acquire() as conn:
                appearance_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM matter_appearances WHERE matter_id = $1",
                    "test_matter_dedup"
                )

            if appearance_count == 2:
                self._log_test(test_name, True, "Matter tracked across 2 meetings")
            else:
                self._log_test(test_name, False, f"Expected 2 appearances, found {appearance_count}")

        except Exception as e:
            self._log_test(test_name, False, f"Exception: {e}")

    async def test_jsonb_structure_validation(self):
        """Test JSONB structure validation"""
        test_name = "JSONB structure validation"

        try:
            meeting = Meeting(
                id="test_jsonb",
                banana="testCA",
                title="Test Meeting",
                date=datetime.now(),
                source_url="https://test.com",
                participation={
                    "email": "public@test.com",
                    "phone": "+1-555-0100",
                    "zoom": "https://zoom.us/test",
                }
            )

            await self.db.meetings.store_meeting(meeting)
            retrieved = await self.db.meetings.get_meeting("test_jsonb")

            if (retrieved and
                isinstance(retrieved.participation, dict) and
                retrieved.participation.get("email") == "public@test.com"):
                self._log_test(test_name, True, "JSONB participation stored and retrieved correctly")
            else:
                self._log_test(test_name, False, f"JSONB structure invalid: {retrieved.participation if retrieved else 'None'}")

        except Exception as e:
            self._log_test(test_name, False, f"Exception: {e}")

    async def test_queue_duplicate_source_url(self):
        """Test that duplicate source_url updates existing job"""
        test_name = "Queue duplicate source_url"

        try:
            # Enqueue first job
            await self.db.queue.enqueue_job(
                source_url="https://test.com/duplicate",
                job_type="meeting",
                banana="testCA",
                payload={"test": "first"},
            )

            # Enqueue duplicate (should update, not create new)
            await self.db.queue.enqueue_job(
                source_url="https://test.com/duplicate",
                job_type="meeting",
                banana="testCA",
                payload={"test": "second"},
            )

            # Check queue count
            async with self.db.pool.acquire() as conn:
                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM queue WHERE source_url = $1",
                    "https://test.com/duplicate"
                )

            if count == 1:
                self._log_test(test_name, True, "Duplicate source_url updates existing job")
            else:
                self._log_test(test_name, False, f"Expected 1 job, found {count}")

        except Exception as e:
            self._log_test(test_name, False, f"Exception: {e}")

    async def test_cross_city_matter_isolation(self):
        """Test that matters from different cities don't collide"""
        test_name = "Cross-city matter isolation"

        try:
            # Create same matter_file in two different cities
            matter1 = Matter(
                id="test_city1_matter",
                banana="city1CA",
                matter_file="BL2025-1",  # Same number
                title="City 1 Ordinance",
                canonical_summary="City 1 summary",
            )
            matter2 = Matter(
                id="test_city2_matter",
                banana="city2CA",
                matter_file="BL2025-1",  # Same number, different city
                title="City 2 Ordinance",
                canonical_summary="City 2 summary",
            )

            await self.db.matters.store_matter(matter1)
            await self.db.matters.store_matter(matter2)

            # Verify both exist
            retrieved1 = await self.db.matters.get_matter("test_city1_matter")
            retrieved2 = await self.db.matters.get_matter("test_city2_matter")

            if (retrieved1 and retrieved2 and
                retrieved1.banana == "city1CA" and
                retrieved2.banana == "city2CA"):
                self._log_test(test_name, True, "Cross-city matters isolated correctly")
            else:
                self._log_test(test_name, False, "Matter collision detected")

        except Exception as e:
            self._log_test(test_name, False, f"Exception: {e}")

    async def cleanup(self):
        """Clean up test data"""
        try:
            async with self.db.pool.acquire() as conn:
                # Delete test data (cascades via foreign keys)
                await conn.execute("DELETE FROM meetings WHERE id LIKE 'test_%'")
                await conn.execute("DELETE FROM cities WHERE banana LIKE 'test%' OR banana LIKE 'city%'")
                await conn.execute("DELETE FROM queue WHERE source_url LIKE 'https://test.com%'")
                await conn.execute("DELETE FROM city_matters WHERE id LIKE 'test_%'")
            logger.info("cleaned up test data")
        except Exception as e:
            logger.warning("cleanup failed", error=str(e))

    async def run_all(self):
        """Run all edge case tests"""
        print("\n" + "="*80)
        print("PostgreSQL Edge Case Tests")
        print("="*80 + "\n")

        # Run tests
        await self.test_meeting_null_date()
        await self.test_item_empty_attachments()
        await self.test_item_null_fields()
        await self.test_meeting_empty_topics()
        await self.test_topic_deduplication()
        await self.test_matter_deduplication()
        await self.test_jsonb_structure_validation()
        await self.test_queue_duplicate_source_url()
        await self.test_cross_city_matter_isolation()

        # Cleanup
        await self.cleanup()

        # Summary
        print("\n" + "="*80)
        total = self.passed + self.failed
        print(f"Results: {self.passed}/{total} passed")
        print("="*80 + "\n")

        return self.failed == 0


async def main():
    """Main test entry point"""
    # Verify PostgreSQL is enabled
    if not config.USE_POSTGRES:
        print("❌ ENGAGIC_USE_POSTGRES is not set to 'true'")
        print("Set environment variable: export ENGAGIC_USE_POSTGRES=true")
        sys.exit(1)

    # Initialize database
    db = await Database.create()

    try:
        tests = EdgeCaseTests(db)
        passed = await tests.run_all()

        if passed:
            print("✅ ALL TESTS PASSED")
            sys.exit(0)
        else:
            print("❌ SOME TESTS FAILED")
            sys.exit(1)

    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
