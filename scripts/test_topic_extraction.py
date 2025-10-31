"""
Test Topic Extraction and Normalization

Quick test to verify topic extraction, normalization, and aggregation.
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infocore.processing.topic_normalizer import TopicNormalizer


def test_normalization():
    """Test topic normalization with various inputs"""
    print("Testing Topic Normalization\n" + "=" * 50)

    normalizer = TopicNormalizer()

    # Test cases: raw topics -> expected canonical
    test_cases = [
        (
            ["affordable housing", "zoning changes", "traffic safety"],
            ["housing", "transportation", "zoning"],  # traffic safety -> transportation
        ),
        (
            ["rezoning", "land use plan", "police budget"],
            ["public_safety", "zoning"],
        ),
        (
            ["climate action", "bike lanes", "parking regulations"],
            ["environment", "transportation"],
        ),
        (
            ["homelessness", "subsidized housing", "low-income housing"],
            ["housing"],  # Should all normalize to "housing"
        ),
        (
            ["city planning", "master plan", "general plan"],
            ["planning", "zoning"],  # All planning-related
        ),
    ]

    passed = 0
    failed = 0

    for raw_topics, expected in test_cases:
        result = normalizer.normalize(raw_topics)
        # Sort both for comparison (order doesn't matter)
        result_sorted = sorted(result)
        expected_sorted = sorted(expected)

        if result_sorted == expected_sorted:
            print(f"PASS: {raw_topics}")
            print(f"  -> {result}")
            passed += 1
        else:
            print(f"FAIL: {raw_topics}")
            print(f"  Expected: {expected_sorted}")
            print(f"  Got:      {result_sorted}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed")

    return failed == 0


def test_aggregation():
    """Test topic aggregation from multiple items"""
    print("\n\nTesting Topic Aggregation\n" + "=" * 50)

    # Simulate item-level topics (already normalized)
    items = [
        {"title": "Item 1", "topics": ["housing", "zoning"]},
        {"title": "Item 2", "topics": ["housing", "transportation"]},
        {"title": "Item 3", "topics": ["budget", "public_safety"]},
        {"title": "Item 4", "topics": ["housing"]},
    ]

    # Aggregate topics
    all_topics = []
    for item in items:
        all_topics.extend(item.get("topics", []))

    # Count frequency
    topic_counts = {}
    for topic in all_topics:
        topic_counts[topic] = topic_counts.get(topic, 0) + 1

    # Sort by frequency
    meeting_topics = sorted(
        topic_counts.keys(), key=lambda t: topic_counts[t], reverse=True
    )

    print(f"Item topics: {[item['topics'] for item in items]}")
    print(f"\nAggregated topics (by frequency): {meeting_topics}")
    print(f"Topic counts: {topic_counts}")

    # Verify housing is first (appears 3 times)
    assert meeting_topics[0] == "housing", "Most frequent topic should be first"
    print("\nAggregation working correctly")

    return True


def test_display_names():
    """Test display name lookup"""
    print("\n\nTesting Display Names\n" + "=" * 50)

    normalizer = TopicNormalizer()

    test_topics = [
        "housing",
        "public_safety",
        "economic_development",
        "environment",
    ]

    for topic in test_topics:
        display = normalizer.get_display_name(topic)
        print(f"{topic:20} → {display}")

    return True


def test_all_canonical_topics():
    """List all canonical topics"""
    print("\n\nAll Canonical Topics\n" + "=" * 50)

    normalizer = TopicNormalizer()
    all_topics = normalizer.get_all_canonical_topics()

    print(f"Total: {len(all_topics)} canonical topics\n")
    for topic in all_topics:
        display = normalizer.get_display_name(topic)
        print(f"  {topic:25} → {display}")

    return True


if __name__ == "__main__":
    print("Engagic Topic Extraction Test Suite\n")

    all_passed = True

    all_passed = test_normalization() and all_passed
    all_passed = test_aggregation() and all_passed
    all_passed = test_display_names() and all_passed
    all_passed = test_all_canonical_topics() and all_passed

    if all_passed:
        print("\n\n" + "=" * 50)
        print("ALL TESTS PASSED")
        print("=" * 50)
        sys.exit(0)
    else:
        print("\n\n" + "=" * 50)
        print("SOME TESTS FAILED")
        print("=" * 50)
        sys.exit(1)
