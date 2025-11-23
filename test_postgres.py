#!/usr/bin/env python3
"""
PostgreSQL Database Layer Test

Tests connection, schema initialization, and basic CRUD operations.
Run this after setting up PostgreSQL locally.
"""

import asyncio
import sys
from datetime import datetime

from database.db_postgres import Database
from database.models import City, Meeting, AgendaItem
from config import config

async def test_connection():
    """Test 1: Connection pool creation"""
    print("\n=== TEST 1: Connection Pool ===")
    try:
        db = await Database.create()
        print("✅ Connection pool created")
        return db
    except Exception as e:
        print(f"❌ Failed to create connection pool: {e}")
        sys.exit(1)

async def test_schema_init(db):
    """Test 2: Schema initialization"""
    print("\n=== TEST 2: Schema Initialization ===")
    try:
        await db.init_schema()
        print("✅ Schema initialized (or already exists)")
    except Exception as e:
        print(f"❌ Schema initialization failed: {e}")
        raise

async def test_city_operations(db):
    """Test 3: City CRUD operations"""
    print("\n=== TEST 3: City Operations ===")

    # Create test city
    test_city = City(
        banana="testcityCA",
        name="Test City",
        state="CA",
        vendor="legistar",
        slug="test-city",
        county="Test County",
        status="active",
        zipcodes=["94301", "94302"]
    )

    # Add city
    try:
        await db.add_city(test_city)
        print(f"✅ Added city: {test_city.name}")
    except Exception as e:
        print(f"⚠️  City might already exist: {e}")

    # Retrieve city
    retrieved = await db.get_city("testcityCA")
    if retrieved:
        print(f"✅ Retrieved city: {retrieved.name}, zipcodes: {retrieved.zipcodes}")
    else:
        print("❌ Failed to retrieve city")
        raise Exception("City retrieval failed")

    # List all cities
    cities = await db.get_all_cities()
    print(f"✅ Found {len(cities)} active cities")

    return test_city

async def test_meeting_operations(db, city):
    """Test 4: Meeting CRUD operations"""
    print("\n=== TEST 4: Meeting Operations ===")

    # Create test meeting
    test_meeting = Meeting(
        id=f"{city.banana}_test_meeting_001",
        banana=city.banana,
        title="Test City Council Meeting",
        date=datetime.now(),
        agenda_url="https://example.com/agenda",
        packet_url="https://example.com/packet.pdf",
        summary=None,
        participation={"email": "clerk@testcity.gov", "phone": "555-1234"},
        status="upcoming",
        processing_status="pending",
        topics=["Housing", "Transportation"]
    )

    # Store meeting
    await db.store_meeting(test_meeting)
    print(f"✅ Stored meeting: {test_meeting.title}")

    # Retrieve meeting
    retrieved = await db.get_meeting(test_meeting.id)
    if retrieved:
        print(f"✅ Retrieved meeting: {retrieved.title}")
        print(f"   Topics: {retrieved.topics}")
        print(f"   Participation: {retrieved.participation}")
    else:
        print("❌ Failed to retrieve meeting")
        raise Exception("Meeting retrieval failed")

    # Get meetings for city
    meetings = await db.get_meetings_for_city(city.banana, limit=10)
    print(f"✅ Found {len(meetings)} meetings for {city.name}")

    return test_meeting

async def test_item_operations(db, meeting):
    """Test 5: Agenda Item operations"""
    print("\n=== TEST 5: Agenda Item Operations ===")

    # Create test items
    test_items = [
        AgendaItem(
            id=f"{meeting.id}_item_001",
            meeting_id=meeting.id,
            title="Approve Housing Development at 123 Main St",
            sequence=1,
            attachments=[{"url": "https://example.com/plan.pdf", "title": "Site Plan"}],
            matter_file="RZ-2025-001",
            topics=["Housing", "Zoning"]
        ),
        AgendaItem(
            id=f"{meeting.id}_item_002",
            meeting_id=meeting.id,
            title="Budget Amendment for Transit Expansion",
            sequence=2,
            attachments=[],
            matter_file="BG-2025-042",
            topics=["Transportation", "Budget"]
        ),
    ]

    # Store items
    await db.store_agenda_items(test_items)
    print(f"✅ Stored {len(test_items)} agenda items")

    # Retrieve items
    retrieved_items = await db.get_agenda_items(meeting.id)
    print(f"✅ Retrieved {len(retrieved_items)} items")
    for item in retrieved_items:
        print(f"   - {item.title} (topics: {item.topics})")

    # Update item
    await db.update_agenda_item(
        test_items[0].id,
        summary="Approved 5-0 with conditions on parking requirements.",
        topics=["Housing", "Zoning", "Parking"]
    )
    print(f"✅ Updated item with summary and topics")

    return test_items

async def test_queue_operations(db, meeting):
    """Test 6: Queue operations"""
    print("\n=== TEST 6: Queue Operations ===")

    # Enqueue job
    await db.enqueue_job(
        source_url=meeting.agenda_url,
        job_type="meeting",
        payload={"meeting_id": meeting.id, "banana": meeting.banana},
        meeting_id=meeting.id,
        banana=meeting.banana,
        priority=90
    )
    print("✅ Enqueued processing job")

    # Get next job
    job = await db.get_next_job()
    if job:
        print(f"✅ Retrieved job: {job['job_type']} for {job['meeting_id']}")
        print(f"   Priority: {job['priority']}, Status: processing")

        # Mark complete
        await db.mark_job_complete(job['id'])
        print("✅ Marked job as completed")
    else:
        print("⚠️  No jobs in queue (might have been processed)")

async def test_search(db, meeting):
    """Test 7: Full-text search"""
    print("\n=== TEST 7: Full-Text Search ===")

    # Search for housing
    results = await db.search_meetings_fulltext("housing", limit=10)
    print(f"✅ Search for 'housing' returned {len(results)} results")
    if results:
        for meeting in results[:3]:  # Show first 3
            print(f"   - {meeting.title} ({meeting.banana})")

async def test_meeting_update(db, meeting):
    """Test 8: Meeting summary update"""
    print("\n=== TEST 8: Meeting Summary Update ===")

    await db.update_meeting_summary(
        meeting_id=meeting.id,
        summary="The council approved a new housing development and allocated funds for transit expansion.",
        topics=["Housing", "Transportation", "Budget"],
        processing_method="test",
        processing_time=1.5
    )
    print("✅ Updated meeting summary and aggregated topics")

    # Verify update
    updated = await db.get_meeting(meeting.id)
    if updated and updated.summary:
        print(f"   Summary: {updated.summary[:80]}...")
        print(f"   Topics: {updated.topics}")
        print(f"   Status: {updated.processing_status}")

async def main():
    """Run all tests"""
    print("=" * 60)
    print("PostgreSQL Database Layer Test Suite")
    print("=" * 60)

    print(f"\nConfiguration:")
    print(f"  Host: {config.POSTGRES_HOST}")
    print(f"  Port: {config.POSTGRES_PORT}")
    print(f"  Database: {config.POSTGRES_DB}")
    print(f"  User: {config.POSTGRES_USER}")
    print(f"  Pool: {config.POSTGRES_POOL_MIN_SIZE}-{config.POSTGRES_POOL_MAX_SIZE}")

    db = None
    try:
        # Run tests sequentially
        db = await test_connection()
        await test_schema_init(db)

        city = await test_city_operations(db)
        meeting = await test_meeting_operations(db, city)
        items = await test_item_operations(db, meeting)
        await test_queue_operations(db, meeting)
        await test_meeting_update(db, meeting)
        await test_search(db, meeting)

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        print("\nDatabase layer is working correctly.")
        print("Next steps:")
        print("  1. Set up PostgreSQL on VPS")
        print("  2. Migrate SQLite data → PostgreSQL")
        print("  3. Test full pipeline (sync + process + API)")

    except Exception as e:
        print("\n" + "=" * 60)
        print(f"❌ TEST FAILED: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        if db:
            await db.close()
            print("\n✅ Connection pool closed")

if __name__ == "__main__":
    # Check if USE_POSTGRES is enabled
    if not config.USE_POSTGRES:
        print("❌ ENGAGIC_USE_POSTGRES is not set to 'true'")
        print("   Set it in your environment or .env file")
        sys.exit(1)

    asyncio.run(main())
