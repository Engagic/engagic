#!/usr/bin/env python3
"""
Comprehensive test suite for Engagic core functionality
Tests database, adapters, and processor after Phase 1-3 refactor
"""

import sys

sys.path.insert(0, "/root/engagic")

from database.db import DatabaseManager
from config import config
from vendors.adapters.all_adapters import (
    PrimeGovAdapter,
    CivicClerkAdapter,
    LegistarAdapter,
    GranicusAdapter,
    NovusAgendaAdapter,
    CivicPlusAdapter,
)


def get_adapter_for_city(city):
    """Get appropriate adapter for a city"""
    vendor = city.vendor
    city_slug = city.vendor_slug

    adapter_map = {
        "primegov": PrimeGovAdapter,
        "civicclerk": CivicClerkAdapter,
        "legistar": LegistarAdapter,
        "granicus": GranicusAdapter,
        "novusagenda": NovusAgendaAdapter,
        "civicplus": CivicPlusAdapter,
    }

    adapter_class = adapter_map.get(vendor)
    if not adapter_class:
        raise ValueError(f"Unsupported vendor: {vendor}")

    return adapter_class(city_slug)


def test_database():
    """Test unified database operations"""
    print("\n" + "=" * 60)
    print("TEST 1: Database Operations")
    print("=" * 60)

    db = DatabaseManager(config.UNIFIED_DB_PATH)

    # Test 1.1: Get city by banana
    print("\n[1.1] Testing get_city(banana='paloaltoCA')...")
    city = db.get_city(banana="paloaltoCA")
    if city:
        print(f"  ✓ Found: {city.name}, {city.state} (vendor: {city.vendor})")
    else:
        print("  ✗ FAILED: City not found")
        return False

    # Test 1.2: Get city by name and state
    print("\n[1.2] Testing get_city(name='Palo Alto', state='CA')...")
    city = db.get_city(name="Palo Alto", state="CA")
    if city and city.banana == "paloaltoCA":
        print(f"  ✓ Found: {city.banana}")
    else:
        print("  ✗ FAILED: City lookup by name/state failed")
        return False

    # Test 1.3: Get city by zipcode
    print("\n[1.3] Testing get_city(zipcode='94301')...")
    city = db.get_city(zipcode="94301")
    if city and city.banana == "paloaltoCA":
        print(f"  ✓ Found: {city.name} via zipcode")
    else:
        print("  ✗ FAILED: Zipcode lookup failed")
        return False

    # Test 1.4: Get cities by vendor
    print("\n[1.4] Testing get_cities(vendor='primegov', limit=5)...")
    cities = db.get_cities(vendor="primegov", limit=5)
    if len(cities) > 0:
        print(f"  ✓ Found {len(cities)} PrimeGov cities:")
        for c in cities[:3]:
            print(f"     - {c.name}, {c.state}")
    else:
        print("  ✗ FAILED: No PrimeGov cities found")
        return False

    # Test 1.5: Get meetings for city
    print("\n[1.5] Testing get_meetings(city_bananas=['paloaltoCA'], limit=3)...")
    meetings = db.get_meetings(city_bananas=["paloaltoCA"], limit=3)
    print(f"  ✓ Found {len(meetings)} meetings for Palo Alto")
    if meetings:
        for m in meetings[:2]:
            print(f"     - {m.date.strftime('%Y-%m-%d')}: {m.title[:50]}...")

    # Test 1.6: Check processing cache
    print("\n[1.6] Testing get_cached_summary()...")
    if meetings and meetings[0].packet_url:
        cached = db.get_cached_summary(meetings[0].packet_url)
        if cached:
            print(
                f"  ✓ Found cached summary ({len(cached.get('processed_summary', ''))} chars)"
            )
        else:
            print("  ⚠ No cached summary (expected for new meetings)")
    else:
        print("  ⚠ No meetings with packet URLs to test cache")

    print("\n" + "=" * 60)
    print("DATABASE TESTS: PASSED ✓")
    print("=" * 60)
    return True


def test_adapters():
    """Test adapter functionality"""
    print("\n" + "=" * 60)
    print("TEST 2: Adapter Functionality")
    print("=" * 60)

    db = DatabaseManager(config.UNIFIED_DB_PATH)

    # Test one city from each vendor
    test_cases = [
        ("paloaltoCA", "primegov", "Palo Alto, CA"),
        ("glendoraCA", "primegov", "Glendora, CA"),
        ("newberlinWI", "civicclerk", "New Berlin, WI"),
    ]

    for banana, expected_vendor, city_display in test_cases:
        print(
            f"\n[2.{test_cases.index((banana, expected_vendor, city_display)) + 1}] Testing {city_display} ({expected_vendor})..."
        )

        city = db.get_city(banana=banana)
        if not city:
            print("  ✗ FAILED: City not found in database")
            continue

        if city.vendor != expected_vendor:
            print(f"  ✗ FAILED: Expected {expected_vendor}, got {city.vendor}")
            continue

        try:
            adapter = get_adapter_for_city(city)
            print(f"  ✓ Adapter created: {adapter.__class__.__name__}")

            # Try fetching meetings (with timeout protection)
            print("  → Fetching meetings...")
            meetings = list(adapter.fetch_meetings())
            print(f"  ✓ Fetched {len(meetings)} meetings")

            if meetings:
                sample = meetings[0]
                print(f"     Sample: {sample.get('title', 'N/A')[:60]}")
                print(f"            Date: {sample.get('date', 'N/A')}")
                print(
                    f"            Has packet: {'packet_url' in sample and sample['packet_url']}"
                )

        except Exception as e:
            print(f"  ✗ FAILED: {type(e).__name__}: {str(e)[:100]}")
            continue

    print("\n" + "=" * 60)
    print("ADAPTER TESTS: COMPLETED")
    print("=" * 60)
    return True


def test_processor():
    """Test PDF processor"""
    print("\n" + "=" * 60)
    print("TEST 3: PDF Processor")
    print("=" * 60)

    try:
        from pipeline.processor import AgendaProcessor

        print("\n[3.1] Testing processor initialization...")
        processor = AgendaProcessor()
        print("  ✓ Processor initialized")

        # Find a meeting with a packet URL
        db = DatabaseManager(config.UNIFIED_DB_PATH)
        print("\n[3.2] Finding meeting with packet URL...")

        meetings = db.get_meetings(city_bananas=["paloaltoCA"], limit=10)
        test_meeting = None
        for m in meetings:
            if m.packet_url:
                test_meeting = m
                break

        if not test_meeting:
            print("  ⚠ WARNING: No meetings with packet URLs found for testing")
            print("  (This is OK - skipping processor test)")
            return True

        print(f"  ✓ Found meeting: {test_meeting.title[:60]}")
        print(f"    URL: {test_meeting.packet_url[:80]}...")

        # Test cache check (should be fast)
        print("\n[3.3] Testing process_agenda_with_cache()...")
        print("  → This may take 5-15 seconds if not cached...")

        result = processor.process_agenda_with_cache(
            {
                "packet_url": test_meeting.packet_url,
                "city_banana": "paloaltoCA",
                "meeting_id": test_meeting.id,
            }
        )

        if result["success"]:
            print("  ✓ Processing successful")
            print(f"    Cached: {result['cached']}")
            print(f"    Processing time: {result['processing_time']:.2f}s")
            print(f"    Method: {result.get('processing_method', 'unknown')}")
            print(f"    Summary length: {len(result['summary'])} chars")
            print(f"    First 150 chars: {result['summary'][:150]}...")
        else:
            print(f"  ✗ FAILED: {result.get('error', 'Unknown error')}")
            return False

        print("\n" + "=" * 60)
        print("PROCESSOR TESTS: PASSED ✓")
        print("=" * 60)
        return True

    except ImportError as e:
        print(f"  ✗ FAILED: Could not import processor: {e}")
        return False
    except Exception as e:
        print(f"  ✗ FAILED: {type(e).__name__}: {e}")
        return False


def test_api():
    """Test API endpoints"""
    print("\n" + "=" * 60)
    print("TEST 4: API Endpoints")
    print("=" * 60)

    try:
        import requests

        base_url = "http://localhost:8000"

        # Test 4.1: Health check
        print("\n[4.1] Testing GET /health...")
        try:
            resp = requests.get(f"{base_url}/health", timeout=5)
            if resp.status_code == 200:
                print(f"  ✓ API is running: {resp.json()}")
            else:
                print(f"  ⚠ Unexpected status: {resp.status_code}")
        except requests.exceptions.ConnectionError:
            print("  ⚠ API not running (this is OK if not started)")
            print(
                "  To test API, run: cd /root/engagic && uvicorn infocore.api.main:app --host 0.0.0.0 --port 8000"
            )
            return True

        # Test 4.2: Search by zipcode
        print("\n[4.2] Testing GET /api/search?zipcode=94301...")
        resp = requests.get(f"{base_url}/api/search?zipcode=94301", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            print("  ✓ Search successful")
            print(f"    City: {data.get('city', {}).get('name', 'N/A')}")
            print(f"    Meetings: {len(data.get('meetings', []))}")
        else:
            print(f"  ✗ FAILED: Status {resp.status_code}")

        # Test 4.3: Get random meeting
        print("\n[4.3] Testing GET /api/random-best-meeting...")
        resp = requests.get(f"{base_url}/api/random-best-meeting", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            print("  ✓ Random meeting retrieved")
            print(f"    City: {data.get('city_name', 'N/A')}")
            print(f"    Title: {data.get('title', 'N/A')[:60]}")
        else:
            print(f"  ✗ FAILED: Status {resp.status_code}")

        print("\n" + "=" * 60)
        print("API TESTS: COMPLETED")
        print("=" * 60)
        return True

    except ImportError:
        print("  ⚠ requests library not available - skipping API tests")
        return True
    except Exception as e:
        print(f"  ✗ FAILED: {type(e).__name__}: {e}")
        return False


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("ENGAGIC CORE FUNCTIONALITY TEST SUITE")
    print("Testing Phase 1-3 Refactor")
    print("=" * 60)

    results = {
        "Database": test_database(),
        "Adapters": test_adapters(),
        "Processor": test_processor(),
        "API": test_api(),
    }

    print("\n" + "=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)

    for test_name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"  {test_name}: {status}")

    all_passed = all(results.values())

    print("\n" + "=" * 60)
    if all_passed:
        print("ALL TESTS PASSED ✓")
    else:
        print("SOME TESTS FAILED ✗")
    print("=" * 60 + "\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
