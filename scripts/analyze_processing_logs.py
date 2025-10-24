#!/usr/bin/env python3
"""
Analyze processing logs to track Tier 1 success/failure metrics

Usage:
    # Analyze recent logs
    python scripts/analyze_processing_logs.py

    # Analyze specific log file
    python scripts/analyze_processing_logs.py /path/to/engagic.log

    # Real-time monitoring
    tail -f /path/to/engagic.log | grep -E "\[(Tier1|Processing|Cache)\]"
"""

import sys
import re
from collections import defaultdict, Counter
from typing import Dict


def parse_log_line(line: str) -> Dict:
    """Parse a log line and extract structured data"""
    result = {}

    # Extract timestamp
    timestamp_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
    if timestamp_match:
        result['timestamp'] = timestamp_match.group(1)

    # Extract log level
    level_match = re.search(r'(INFO|WARNING|ERROR|DEBUG)', line)
    if level_match:
        result['level'] = level_match.group(1)

    # Extract component tag
    tag_match = re.search(r'\[([^\]]+)\]', line)
    if tag_match:
        result['component'] = tag_match.group(1)

    # Extract status
    status_match = re.search(r'\[.*?\]\s+(\w+)', line)
    if status_match:
        result['status'] = status_match.group(1)

    # Extract city
    city_match = re.search(r'-\s+([a-zA-Z]+[A-Z]{2})\s+-', line)
    if city_match:
        result['city'] = city_match.group(1)

    # Extract timing
    timing_match = re.search(r'(\d+\.\d+)s', line)
    if timing_match:
        result['duration'] = float(timing_match.group(1))

    # Extract character counts
    chars_match = re.search(r'\((\d+) chars', line)
    if chars_match:
        result['chars'] = int(chars_match.group(1))

    return result


def analyze_logs(log_file: str = None):
    """Analyze processing logs and print metrics"""

    # Metrics storage
    tier1_results = defaultdict(int)
    cache_results = defaultdict(int)
    city_stats = defaultdict(lambda: {'success': 0, 'failed': 0})
    failure_reasons = Counter()
    processing_times = []

    # Read logs
    if log_file:
        with open(log_file, 'r') as f:
            lines = f.readlines()
    else:
        # Read from stdin (for piping)
        lines = sys.stdin.readlines()

    # Parse each line
    for line in lines:
        if '[Tier1]' not in line and '[Cache]' not in line and '[Processing]' not in line:
            continue

        parsed = parse_log_line(line)

        # Track Tier 1 results
        if parsed.get('component') == 'Tier1':
            status = parsed.get('status')
            if status:
                tier1_results[status] += 1

            if status == 'SUCCESS' and parsed.get('duration'):
                processing_times.append(parsed['duration'])

            if status == 'FAILED' or status == 'REJECTED':
                if 'No text extracted' in line:
                    failure_reasons['no_text_extracted'] += 1
                elif 'Poor text quality' in line:
                    failure_reasons['poor_quality'] += 1
                elif 'Exception' in line:
                    failure_reasons['exception'] += 1
                elif 'REJECTED' in line:
                    failure_reasons['rejected'] += 1

        # Track cache results
        if parsed.get('component') == 'Cache':
            status = parsed.get('status')
            if status:
                cache_results[status] += 1

        # Track city stats
        if parsed.get('component') == 'Processing':
            city = parsed.get('city')
            status = parsed.get('status')
            if city and status:
                if status == 'SUCCESS':
                    city_stats[city]['success'] += 1
                elif status == 'FAILED':
                    city_stats[city]['failed'] += 1

    # Print report
    print("=" * 80)
    print("ENGAGIC PROCESSING METRICS")
    print("=" * 80)
    print()

    # Tier 1 metrics
    print("TIER 1 (FREE TIER) PERFORMANCE:")
    total_tier1 = sum(tier1_results.values())
    if total_tier1 > 0:
        success = tier1_results.get('SUCCESS', 0)
        failed = tier1_results.get('FAILED', 0)
        rejected = tier1_results.get('REJECTED', 0)
        success_rate = (success / total_tier1) * 100

        print(f"  Total attempts:  {total_tier1}")
        print(f"  Successes:       {success} ({success_rate:.1f}%)")
        print(f"  Failures:        {failed} ({(failed/total_tier1)*100:.1f}%)")
        print(f"  Rejected:        {rejected} ({(rejected/total_tier1)*100:.1f}%)")
        print()

        if processing_times:
            avg_time = sum(processing_times) / len(processing_times)
            min_time = min(processing_times)
            max_time = max(processing_times)
            print(f"  Processing time: avg={avg_time:.1f}s, min={min_time:.1f}s, max={max_time:.1f}s")
            print()

        print("  Failure breakdown:")
        for reason, count in failure_reasons.most_common():
            print(f"    {reason}: {count} ({(count/total_tier1)*100:.1f}%)")
    else:
        print("  No Tier 1 processing attempts found")
    print()

    # Cache metrics
    print("CACHE PERFORMANCE:")
    total_cache = sum(cache_results.values())
    if total_cache > 0:
        hits = cache_results.get('HIT', 0)
        misses = cache_results.get('MISS', 0)
        hit_rate = (hits / total_cache) * 100

        print(f"  Total requests:  {total_cache}")
        print(f"  Cache hits:      {hits} ({hit_rate:.1f}%)")
        print(f"  Cache misses:    {misses} ({(misses/total_cache)*100:.1f}%)")
    else:
        print("  No cache operations found")
    print()

    # City breakdown
    print("TOP CITIES BY ACTIVITY:")
    sorted_cities = sorted(
        city_stats.items(),
        key=lambda x: x[1]['success'] + x[1]['failed'],
        reverse=True
    )
    for city, stats in sorted_cities[:10]:
        total = stats['success'] + stats['failed']
        success_rate = (stats['success'] / total * 100) if total > 0 else 0
        print(f"  {city:20} - {total:3} docs - {success_rate:5.1f}% success")
    print()

    # Summary
    print("=" * 80)
    print("SUMMARY:")
    if total_tier1 > 0:
        actual_rate = (tier1_results.get('SUCCESS', 0) / total_tier1) * 100
        expected_rate = 60.0
        if actual_rate >= expected_rate:
            print(f"  SUCCESS RATE: {actual_rate:.1f}% (above expected {expected_rate}%)")
        else:
            print(f"  SUCCESS RATE: {actual_rate:.1f}% (below expected {expected_rate}%)")
            print(f"  ALERT: Success rate is {expected_rate - actual_rate:.1f}% below target")

    if total_cache > 0:
        hit_rate = (cache_results.get('HIT', 0) / total_cache) * 100
        print(f"  CACHE HIT RATE: {hit_rate:.1f}%")

    print("=" * 80)


if __name__ == "__main__":
    log_file = sys.argv[1] if len(sys.argv) > 1 else None
    analyze_logs(log_file)
