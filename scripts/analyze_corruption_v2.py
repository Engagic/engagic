#!/usr/bin/env python3
"""
Comprehensive city database corruption analysis v2
Enhanced to properly extract PrimeGov slugs from domain names
"""

import sqlite3
import json
import re
from collections import defaultdict
from urllib.parse import urlparse

DB_PATH = '/root/engagic/data/engagic.db'

def extract_slug_from_url(url, vendor):
    """Extract the actual slug/identifier from a packet URL based on vendor"""
    if not url:
        return None
    
    # Handle JSON arrays
    if url.startswith('['):
        try:
            urls = json.loads(url)
            if urls and len(urls) > 0:
                url = urls[0]
            else:
                return None
        except (json.JSONDecodeError, ValueError, TypeError):
            return None
    
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    path = parsed.path.lower()
    
    # CivicClerk pattern: {slug}.api.civicclerk.com
    if 'civicclerk.com' in domain:
        match = re.match(r'([^.]+)\.api\.civicclerk\.com', domain)
        if match:
            return ('civicclerk', match.group(1))
    
    # PrimeGov pattern: {slug}.primegov.com
    if 'primegov.com' in domain:
        # Pattern 1: {slug}.primegov.com/Public/CompiledDocument
        match = re.match(r'([^.]+)\.primegov\.com', domain)
        if match:
            return ('primegov', match.group(1))
    
    # CivicPlus pattern: Multiple patterns
    if 'civicplus.com' in domain or 'civicengage.com' in domain:
        # Pattern: {slug}.civicplus.com
        match = re.match(r'([^.]+)\.civicplus\.com', domain)
        if match:
            return ('civicplus', match.group(1))
        # Pattern: civicengage.com/{slug}
        match = re.search(r'civicengage\.com/([^/]+)', url)
        if match:
            return ('civicplus', match.group(1))
    
    # Granicus/Legistar pattern: Very complex
    if 'granicus.com' in domain or 'legistar.com' in domain or 'legistar1.com' in domain:
        # Pattern: {slug}.legistar.com or {slug}.legistar1.com
        match = re.match(r'([^.]+)\.legistar1?\.com', domain)
        if match:
            return ('granicus', match.group(1))
        # Pattern: S3 with granicus_production_attachments/{slug}/
        if 's3.amazonaws.com' in domain and 'granicus_production_attachments' in path:
            match = re.search(r'granicus_production_attachments/([^/]+)/', path)
            if match:
                return ('granicus', match.group(1))
    
    # NovusAgenda pattern: {slug}.novusagenda.com
    if 'novusagenda.com' in domain:
        match = re.match(r'([^.]+)\.novusagenda\.com', domain)
        if match:
            return ('novusagenda', match.group(1))
    
    return None

def analyze_city_meetings(conn, city):
    """Analyze meetings for a single city to determine if config is correct"""
    cursor = conn.cursor()
    
    # Get all meetings for this city
    cursor.execute("""
        SELECT id, packet_url 
        FROM meetings 
        WHERE banana = ?
    """, (city['banana'],))
    
    meetings = cursor.fetchall()
    
    if not meetings:
        return {
            'status': 'unverified',
            'reason': 'No meetings to verify against',
            'meeting_count': 0,
            'actual_slugs': [],
            'actual_vendors': [],
            'sample_urls': []
        }
    
    # Extract slugs from all packet URLs
    actual_slugs = []
    actual_vendors = []
    sample_urls = []
    
    for meeting_id, packet_url in meetings:
        if packet_url:
            extracted = extract_slug_from_url(packet_url, city['vendor'])
            if extracted:
                vendor, slug = extracted
                actual_slugs.append(slug)
                actual_vendors.append(vendor)
                if len(sample_urls) < 3:
                    sample_urls.append(packet_url)
    
    if not actual_slugs:
        return {
            'status': 'unverified',
            'reason': 'No packet URLs to verify',
            'meeting_count': len(meetings),
            'actual_slugs': [],
            'actual_vendors': [],
            'sample_urls': []
        }
    
    # Analyze the slugs
    unique_slugs = list(set(actual_slugs))
    unique_vendors = list(set(actual_vendors))
    configured_slug = city['slug']
    configured_vendor = city['vendor']
    
    # Check for corruption patterns
    if len(unique_vendors) > 1:
        return {
            'status': 'cross_contaminated',
            'reason': f'Multiple vendors in meetings: {unique_vendors}',
            'meeting_count': len(meetings),
            'actual_slugs': unique_slugs,
            'actual_vendors': unique_vendors,
            'configured_slug': configured_slug,
            'configured_vendor': configured_vendor,
            'sample_urls': sample_urls
        }
    
    if len(unique_vendors) == 1 and unique_vendors[0] != configured_vendor:
        return {
            'status': 'wrong_vendor',
            'reason': f'Configured {configured_vendor}, actually {unique_vendors[0]}',
            'meeting_count': len(meetings),
            'actual_slugs': unique_slugs,
            'actual_vendors': unique_vendors,
            'configured_slug': configured_slug,
            'configured_vendor': configured_vendor,
            'sample_urls': sample_urls
        }
    
    if len(unique_slugs) > 1:
        return {
            'status': 'cross_contaminated',
            'reason': f'Multiple slugs in meetings: {unique_slugs}',
            'meeting_count': len(meetings),
            'actual_slugs': unique_slugs,
            'actual_vendors': unique_vendors,
            'configured_slug': configured_slug,
            'configured_vendor': configured_vendor,
            'sample_urls': sample_urls
        }
    
    if len(unique_slugs) == 1 and unique_slugs[0] != configured_slug:
        return {
            'status': 'wrong_slug',
            'reason': f'Configured {configured_slug}, actually {unique_slugs[0]}',
            'meeting_count': len(meetings),
            'actual_slugs': unique_slugs,
            'actual_vendors': unique_vendors,
            'configured_slug': configured_slug,
            'configured_vendor': configured_vendor,
            'sample_urls': sample_urls
        }
    
    return {
        'status': 'correct',
        'reason': 'Configuration matches actual URLs',
        'meeting_count': len(meetings),
        'actual_slugs': unique_slugs,
        'actual_vendors': unique_vendors,
        'configured_slug': configured_slug,
        'configured_vendor': configured_vendor,
        'sample_urls': sample_urls
    }

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("="*80)
    print("COMPREHENSIVE CITY DATABASE CORRUPTION ANALYSIS v2")
    print("="*80)
    
    # Get all cities
    cursor.execute("SELECT banana, name, state, vendor, slug FROM cities ORDER BY vendor, name")
    cities = [dict(row) for row in cursor.fetchall()]
    
    print(f"\nTotal cities: {len(cities)}")
    
    # Categorize cities
    categorized = {
        'correct': [],
        'wrong_slug': [],
        'wrong_vendor': [],
        'cross_contaminated': [],
        'unverified': []
    }
    
    print("\nAnalyzing cities...")
    for i, city in enumerate(cities, 1):
        if i % 50 == 0:
            print(f"  Processed {i}/{len(cities)} cities...")
        
        analysis = analyze_city_meetings(conn, city)
        categorized[analysis['status']].append({
            'city': city,
            'analysis': analysis
        })
    
    print(f"  Processed {len(cities)}/{len(cities)} cities.\n")
    
    # Print summary statistics
    print("="*80)
    print("SUMMARY STATISTICS")
    print("="*80)
    for status, items in categorized.items():
        print(f"{status.upper().replace('_', ' ')}: {len(items)} cities")
    
    # Print detailed breakdowns by vendor
    print("\n" + "="*80)
    print("BREAKDOWN BY VENDOR")
    print("="*80)
    
    vendor_stats = defaultdict(lambda: defaultdict(int))
    for status, items in categorized.items():
        for item in items:
            vendor = item['city']['vendor']
            vendor_stats[vendor][status] += 1
    
    for vendor in sorted(vendor_stats.keys()):
        print(f"\n{vendor.upper()}:")
        stats = vendor_stats[vendor]
        total = sum(stats.values())
        for status in ['correct', 'wrong_slug', 'wrong_vendor', 'cross_contaminated', 'unverified']:
            count = stats.get(status, 0)
            if count > 0:
                pct = (count / total * 100) if total > 0 else 0
                print(f"  {status.replace('_', ' ').title()}: {count} ({pct:.1f}%)")
    
    # Detailed corruption reports
    print("\n" + "="*80)
    print("DETAILED CORRUPTION REPORTS")
    print("="*80)
    
    # Wrong slug - with sample URLs
    if categorized['wrong_slug']:
        print(f"\nWRONG SLUG ({len(categorized['wrong_slug'])} cities):")
        print("-" * 80)
        for item in sorted(categorized['wrong_slug'], key=lambda x: x['city']['vendor']):
            city = item['city']
            analysis = item['analysis']
            actual_slug = analysis['actual_slugs'][0] if analysis['actual_slugs'] else 'unknown'
            print(f"  {city['name']}, {city['state']} ({city['vendor']})")
            print(f"    Configured: {city['slug']}")
            print(f"    Actually:   {actual_slug}")
            print(f"    Meetings:   {analysis['meeting_count']}")
            if analysis['sample_urls']:
                print(f"    Sample URL: {analysis['sample_urls'][0][:100]}")
            print()
    
    # Wrong vendor - with sample URLs
    if categorized['wrong_vendor']:
        print(f"\nWRONG VENDOR ({len(categorized['wrong_vendor'])} cities):")
        print("-" * 80)
        for item in sorted(categorized['wrong_vendor'], key=lambda x: x['city']['name']):
            city = item['city']
            analysis = item['analysis']
            actual_vendor = analysis['actual_vendors'][0] if analysis['actual_vendors'] else 'unknown'
            actual_slug = analysis['actual_slugs'][0] if analysis['actual_slugs'] else 'unknown'
            print(f"  {city['name']}, {city['state']}")
            print(f"    Configured: {city['vendor']} / {city['slug']}")
            print(f"    Actually:   {actual_vendor} / {actual_slug}")
            print(f"    Meetings:   {analysis['meeting_count']}")
            if analysis['sample_urls']:
                print(f"    Sample URL: {analysis['sample_urls'][0][:100]}")
            print()
    
    # Cross contaminated - with sample URLs
    if categorized['cross_contaminated']:
        print(f"\nCROSS CONTAMINATED ({len(categorized['cross_contaminated'])} cities):")
        print("-" * 80)
        for item in sorted(categorized['cross_contaminated'], key=lambda x: x['city']['name']):
            city = item['city']
            analysis = item['analysis']
            print(f"  {city['name']}, {city['state']} ({city['vendor']})")
            print(f"    Configured: {city['slug']}")
            print(f"    Found vendors: {', '.join(analysis['actual_vendors'])}")
            print(f"    Found slugs:   {', '.join(analysis['actual_slugs'])}")
            print(f"    Meetings:      {analysis['meeting_count']}")
            print(f"    Reason:        {analysis['reason']}")
            if analysis['sample_urls']:
                for url in analysis['sample_urls'][:2]:
                    print(f"    Sample URL:    {url[:100]}")
            print()
    
    conn.close()
    
    # Generate SQL fix script
    print("\n" + "="*80)
    print("GENERATED SQL FIX COMMANDS")
    print("="*80)
    
    print("\n-- Wrong Slug Fixes")
    for item in categorized['wrong_slug']:
        city = item['city']
        analysis = item['analysis']
        actual_slug = analysis['actual_slugs'][0] if analysis['actual_slugs'] else 'unknown'
        if actual_slug != 'unknown':
            print(f"-- {city['name']}, {city['state']} ({city['vendor']})")
            print(f"UPDATE cities SET slug = '{actual_slug}' WHERE banana = '{city['banana']}';")
    
    print("\n-- Wrong Vendor Fixes")
    for item in categorized['wrong_vendor']:
        city = item['city']
        analysis = item['analysis']
        actual_vendor = analysis['actual_vendors'][0] if analysis['actual_vendors'] else 'unknown'
        actual_slug = analysis['actual_slugs'][0] if analysis['actual_slugs'] else 'unknown'
        if actual_vendor != 'unknown' and actual_slug != 'unknown':
            print(f"-- {city['name']}, {city['state']}")
            print(f"UPDATE cities SET vendor = '{actual_vendor}', slug = '{actual_slug}' WHERE banana = '{city['banana']}';")
    
    print("\n" + "="*80)
    print("ANALYSIS COMPLETE")
    print("="*80)

if __name__ == "__main__":
    main()
