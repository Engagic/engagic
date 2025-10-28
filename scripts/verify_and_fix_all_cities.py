#!/usr/bin/env python3
"""
Verify and fix all city configurations in the database.

Tests each city's vendor/slug combo, detects cross-contamination,
and generates SQL fix statements.
"""

import sqlite3
import requests
import sys
import time
from typing import Optional, Dict, List, Tuple
from urllib.parse import urlparse

# Confidence: 8/10 - Aggressive verification with fallback patterns

DB_PATH = "data/engagic.db"
TIMEOUT = 10
REQUEST_DELAY = 0.5  # Be polite to servers


# Vendor-specific URL patterns and test strategies
VENDOR_PATTERNS = {
    "primegov": {
        "base_url": lambda slug: f"https://{slug}.primegov.com",
        "test_path": "/api/v2/PublicPortal/ListUpcomingMeetings",
        "success_indicators": [200, 302],  # 302 to login page is OK
    },
    "granicus": {
        "base_url": lambda slug: f"https://{slug}.granicus.com",
        "test_path": "/ViewPublisher.php?view_id=1",
        "success_indicators": [200],
    },
    "legistar": {
        "base_url": lambda slug: f"https://webapi.legistar.com/v1/{slug}",
        "test_path": "/events",
        "success_indicators": [200, 400],  # 400 is OK (bad query params, but endpoint exists)
    },
    "civicclerk": {
        "base_url": lambda slug: f"https://{slug}.api.civicclerk.com",
        "test_path": "/v1/Events",
        "success_indicators": [200, 400],
    },
    "novusagenda": {
        "base_url": lambda slug: f"https://{slug}.novusagenda.com",
        "test_path": "/agendapublic",
        "success_indicators": [200],
    },
    "civicplus": {
        "base_url": lambda slug: f"https://{slug}.civicplus.com",
        "test_path": "/",
        "success_indicators": [200, 301, 302],
    },
    "civicweb": {
        "base_url": lambda slug: f"https://{slug}.civicweb.net",
        "test_path": "/",
        "success_indicators": [200, 301, 302],
    },
    "iqm2": {
        "base_url": lambda slug: f"https://{slug}.iqm2.com",
        "test_path": "/",
        "success_indicators": [200, 301, 302],
    },
    "municode": {
        "base_url": lambda slug: f"https://{slug}.municodemeetings.com",
        "test_path": "/",
        "success_indicators": [200, 301, 302],
    },
}


def test_city_config(vendor: str, slug: str) -> Tuple[bool, int, str]:
    """
    Test if a vendor/slug combination works.

    Returns:
        (success, status_code, error_message)
    """
    if vendor not in VENDOR_PATTERNS:
        return False, 0, f"Unknown vendor: {vendor}"

    # Special handling for Granicus - use adapter's discovery logic
    if vendor == "granicus":
        return test_granicus_city(slug)

    pattern = VENDOR_PATTERNS[vendor]
    base_url = pattern["base_url"](slug)
    test_url = base_url + pattern["test_path"]

    try:
        response = requests.get(
            test_url,
            timeout=TIMEOUT,
            allow_redirects=True,
            headers={"User-Agent": "EngagicCityVerifier/1.0"}
        )

        if response.status_code in pattern["success_indicators"]:
            return True, response.status_code, ""
        else:
            return False, response.status_code, f"Unexpected status: {response.status_code}"

    except requests.exceptions.Timeout:
        return False, 0, "Timeout"
    except requests.exceptions.ConnectionError as e:
        return False, 0, f"Connection error: {str(e)[:100]}"
    except Exception as e:
        return False, 0, f"Error: {str(e)[:100]}"


def test_granicus_city(slug: str) -> Tuple[bool, int, str]:
    """
    Test Granicus city by attempting view_id discovery.

    Returns:
        (success, status_code, error_message)
    """
    import json
    import os
    from datetime import datetime

    base_url = f"https://{slug}.granicus.com"
    current_year = str(datetime.now().year)

    # Check cache first
    cache_file = "data/granicus_view_ids.json"
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                view_id_cache = json.load(f)

            if base_url in view_id_cache:
                cached_view_id = view_id_cache[base_url]
                # Verify cached view_id still works
                test_url = f"{base_url}/ViewPublisher.php?view_id={cached_view_id}"
                try:
                    response = requests.get(test_url, timeout=TIMEOUT,
                                          headers={"User-Agent": "EngagicCityVerifier/1.0"})
                    if response.status_code == 200 and "ViewPublisher" in response.text:
                        return True, 200, f"(cached view_id={cached_view_id})"
                except:
                    pass  # Cache invalid, will discover below
        except:
            pass  # Cache file corrupt, ignore

    # Try first 50 view_ids (balance between thoroughness and speed)
    for view_id in range(1, 51):
        try:
            test_url = f"{base_url}/ViewPublisher.php?view_id={view_id}"
            response = requests.get(
                test_url,
                timeout=TIMEOUT,
                headers={"User-Agent": "EngagicCityVerifier/1.0"}
            )

            if response.status_code == 200:
                # Check if it actually has meeting content
                if ("ViewPublisher" in response.text and
                    ("Meeting" in response.text or "Agenda" in response.text)):
                    return True, 200, f"(discovered view_id={view_id})"

        except Exception:
            continue

    # If no view_id found, it's broken
    return False, 404, "No valid view_id found (tested 1-50)"


def try_slug_variations(vendor: str, city_name: str, state: str, current_slug: str) -> Optional[str]:
    """
    Try common slug variations to find a working config.

    Returns:
        Working slug or None
    """
    # Generate candidate slugs
    city_clean = city_name.lower().replace(" ", "").replace("-", "").replace("'", "")
    city_with_state = f"{city_clean}{state.upper()}"
    city_of = f"cityof{city_clean}"

    candidates = [
        city_clean,
        city_of,
        city_with_state,
        f"cityof{city_clean}{state.lower()}",
        city_name.lower().replace(" ", ""),
        city_name.lower().replace(" ", "-"),
    ]

    # Remove duplicates and current slug
    candidates = [c for c in dict.fromkeys(candidates) if c != current_slug]

    for candidate in candidates[:5]:  # Limit attempts
        # For Granicus, use quick test (just view_id=1) to avoid 50x slowdown
        if vendor == "granicus":
            success, status, _ = test_granicus_quick(candidate)
        else:
            success, status, _ = test_city_config(vendor, candidate)
        if success:
            return candidate
        time.sleep(REQUEST_DELAY)

    return None


def test_granicus_quick(slug: str) -> Tuple[bool, int, str]:
    """Quick Granicus test for slug variations - only tests view_id=1"""
    base_url = f"https://{slug}.granicus.com"
    test_url = f"{base_url}/ViewPublisher.php?view_id=1"

    try:
        response = requests.get(test_url, timeout=TIMEOUT,
                              headers={"User-Agent": "EngagicCityVerifier/1.0"})
        if response.status_code == 200 and "ViewPublisher" in response.text:
            return True, 200, "(quick test view_id=1)"
    except:
        pass

    return False, 404, "Quick test failed"


def detect_cross_contamination(db_conn, banana: str, vendor: str, slug: str) -> List[str]:
    """
    Check if meetings for this city have packet URLs from wrong vendor/slug.

    Returns:
        List of contamination issues
    """
    cursor = db_conn.execute(
        "SELECT packet_url FROM meetings WHERE banana = ? AND packet_url IS NOT NULL LIMIT 10",
        (banana,)
    )

    issues = []
    expected_domains = {
        "primegov": f"{slug}.primegov.com",
        "granicus": [f"{slug}.granicus.com", "s3.amazonaws.com"],  # Granicus uses S3 too
        "legistar": ["legistar.granicus.com", "legistar1.granicus.com", "legistar2.granicus.com"],
        "civicclerk": f"{slug}.api.civicclerk.com",
        "novusagenda": f"{slug}.novusagenda.com",
        "civicplus": f"{slug}.civicplus.com",
    }

    expected = expected_domains.get(vendor, [])
    if isinstance(expected, str):
        expected = [expected]

    for row in cursor:
        packet_url = row[0]
        if not packet_url:
            continue

        # Extract domain
        if packet_url.startswith("http"):
            domain = urlparse(packet_url).netloc
        else:
            # Partial URL like //s3.amazonaws.com/...
            parts = packet_url.split("/")
            domain = parts[2] if len(parts) > 2 else ""

        # Check if domain matches expectations
        domain_matches = any(exp in domain for exp in expected)
        if not domain_matches and domain:
            issues.append(f"Wrong domain in packet_url: {domain} (expected: {expected})")

    return issues


def main():
    print("=" * 80)
    print("ENGAGIC CITY CONFIGURATION VERIFICATION & FIX TOOL")
    print("=" * 80)
    print()

    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute(
        "SELECT banana, name, state, vendor, slug FROM cities ORDER BY vendor, name"
    )
    cities = cursor.fetchall()

    print(f"Loaded {len(cities)} cities from database\n")

    # Results tracking
    results = {
        "working": [],
        "broken": [],
        "cross_contaminated": [],
        "fixed": [],
    }

    sql_fixes = []

    # Test each city
    for i, (banana, name, state, vendor, slug) in enumerate(cities, 1):
        print(f"[{i}/{len(cities)}] {name}, {state} ({vendor}:{slug})", end=" ... ")
        sys.stdout.flush()

        # Test current config
        success, status, error = test_city_config(vendor, slug)

        if success:
            print(f"OK ({status})")
            results["working"].append((banana, name, state, vendor, slug))

            # Check for cross-contamination even if config works
            contamination = detect_cross_contamination(conn, banana, vendor, slug)
            if contamination:
                print(f"  WARNING: Cross-contamination detected:")
                for issue in contamination:
                    print(f"    - {issue}")
                results["cross_contaminated"].append((banana, name, state, vendor, slug, contamination))

        else:
            print(f"FAIL ({error})")
            results["broken"].append((banana, name, state, vendor, slug, error))

            # Try variations
            print(f"  Trying slug variations...", end=" ")
            sys.stdout.flush()
            new_slug = try_slug_variations(vendor, name, state, slug)

            if new_slug:
                print(f"FOUND: {new_slug}")
                sql_fixes.append(
                    f"UPDATE cities SET slug='{new_slug}', updated_at=CURRENT_TIMESTAMP WHERE banana='{banana}'; -- {name}, {state}"
                )
                results["fixed"].append((banana, name, state, vendor, slug, new_slug))
            else:
                print("No working slug found")

        time.sleep(REQUEST_DELAY)

    # Print summary
    print("\n" + "=" * 80)
    print("VERIFICATION SUMMARY")
    print("=" * 80)
    print(f"Total cities: {len(cities)}")
    print(f"Working configs: {len(results['working'])}")
    print(f"Broken configs: {len(results['broken'])}")
    print(f"Cross-contaminated: {len(results['cross_contaminated'])}")
    print(f"Auto-fixed: {len(results['fixed'])}")
    print()

    # Output broken configs
    if results["broken"]:
        print("=" * 80)
        print("BROKEN CONFIGS (Manual Research Needed)")
        print("=" * 80)
        for banana, name, state, vendor, slug, error in results["broken"]:
            print(f"- {name}, {state} ({vendor}:{slug})")
            print(f"  Error: {error}")
            print(f"  Banana: {banana}")
        print()

    # Output cross-contamination issues
    if results["cross_contaminated"]:
        print("=" * 80)
        print("CROSS-CONTAMINATION DETECTED")
        print("=" * 80)
        for banana, name, state, vendor, slug, issues in results["cross_contaminated"]:
            print(f"- {name}, {state} ({vendor}:{slug})")
            for issue in issues:
                print(f"  {issue}")
        print()

    # Output SQL fixes
    if sql_fixes:
        print("=" * 80)
        print("SQL FIXES (Copy and execute these)")
        print("=" * 80)
        print("BEGIN TRANSACTION;")
        for fix in sql_fixes:
            print(fix)
        print("COMMIT;")
        print()

        # Also save to file
        with open("scripts/auto_generated_fixes.sql", "w") as f:
            f.write("-- Auto-generated SQL fixes from verify_and_fix_all_cities.py\n")
            f.write("-- Generated: " + time.strftime("%Y-%m-%d %H:%M:%S") + "\n\n")
            f.write("BEGIN TRANSACTION;\n\n")
            for fix in sql_fixes:
                f.write(fix + "\n")
            f.write("\nCOMMIT;\n")
        print(f"SQL fixes saved to: scripts/auto_generated_fixes.sql")

    conn.close()

    print("\n" + "=" * 80)
    print("VERIFICATION COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
