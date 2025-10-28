#!/usr/bin/env python3
"""
Deep dive analysis: Check if any cities have meetings from multiple DIFFERENT cities
(true cross-contamination, not just wrong slug)
"""

import sqlite3
import json
import re
from urllib.parse import urlparse

DB_PATH = '/root/engagic/data/engagic.db'

def extract_slug_from_url(url):
    """Extract slug from any vendor URL"""
    if not url:
        return None
    
    if url.startswith('['):
        try:
            urls = json.loads(url)
            if urls and len(urls) > 0:
                url = urls[0]
        except:
            return None
    
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    
    # Extract subdomain (first part before first dot)
    if 'primegov.com' in domain:
        match = re.match(r'([^.]+)\.primegov\.com', domain)
        return match.group(1) if match else None
    
    if 'civicclerk.com' in domain:
        match = re.match(r'([^.]+)\.api\.civicclerk\.com', domain)
        return match.group(1) if match else None
    
    if 'legistar.com' in domain or 'legistar1.com' in domain:
        match = re.match(r'([^.]+)\.legistar1?\.com', domain)
        return match.group(1) if match else None
    
    if 'novusagenda.com' in domain:
        match = re.match(r'([^.]+)\.novusagenda\.com', domain)
        return match.group(1) if match else None
    
    if 'civicplus.com' in domain:
        match = re.match(r'([^.]+)\.civicplus\.com', domain)
        return match.group(1) if match else None
    
    # S3 Granicus pattern
    if 's3.amazonaws.com' in domain:
        match = re.search(r'granicus_production_attachments/([^/]+)/', url.lower())
        return match.group(1) if match else None
    
    return None

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("="*80)
    print("CROSS-CONTAMINATION DEEP DIVE")
    print("="*80)
    print("\nChecking for cities with meetings from multiple different slugs...")
    print("(This indicates meetings from City A stored under City B)\n")
    
    # Get all cities with meetings
    cursor.execute("""
        SELECT c.banana, c.name, c.state, c.vendor, c.slug, COUNT(m.id) as meeting_count
        FROM cities c
        JOIN meetings m ON c.banana = m.banana
        GROUP BY c.banana
        HAVING meeting_count > 0
        ORDER BY meeting_count DESC
    """)
    
    cities_with_meetings = cursor.fetchall()
    
    cross_contaminated = []
    
    for city_row in cities_with_meetings:
        city = dict(city_row)
        
        # Get all packet URLs for this city
        cursor.execute("""
            SELECT id, packet_url
            FROM meetings
            WHERE banana = ?
        """, (city['banana'],))
        
        meetings = cursor.fetchall()
        
        # Extract slugs from all URLs
        slugs_found = []
        for meeting in meetings:
            if meeting['packet_url']:
                slug = extract_slug_from_url(meeting['packet_url'])
                if slug:
                    slugs_found.append(slug)
        
        # Check if multiple unique slugs exist
        unique_slugs = list(set(slugs_found))
        
        if len(unique_slugs) > 1:
            cross_contaminated.append({
                'city': city,
                'slugs': unique_slugs,
                'slug_counts': {s: slugs_found.count(s) for s in unique_slugs}
            })
    
    if cross_contaminated:
        print(f"FOUND {len(cross_contaminated)} CROSS-CONTAMINATED CITIES:")
        print("-" * 80)
        for item in cross_contaminated:
            city = item['city']
            print(f"\n{city['name']}, {city['state']} ({city['vendor']})")
            print(f"  Configured slug: {city['slug']}")
            print(f"  Total meetings:  {city['meeting_count']}")
            print(f"  Slugs found:     {', '.join(item['slugs'])}")
            print("  Distribution:")
            for slug, count in sorted(item['slug_counts'].items(), key=lambda x: x[1], reverse=True):
                pct = (count / city['meeting_count'] * 100)
                print(f"    - {slug}: {count} meetings ({pct:.1f}%)")
    else:
        print("NO TRUE CROSS-CONTAMINATION FOUND")
        print("(All corrupted cities have consistent wrong slugs, not mixed sources)")
    
    # Santa Maria specific check
    print("\n" + "="*80)
    print("SPECIAL CHECK: Santa Maria, CA")
    print("="*80)
    cursor.execute("""
        SELECT id, packet_url, date, title
        FROM meetings
        WHERE banana = 'santamariaCA'
        ORDER BY date DESC
        LIMIT 10
    """)
    
    santa_maria_meetings = cursor.fetchall()
    print(f"\nSanta Maria has {len(santa_maria_meetings)} meetings:")
    for meeting in santa_maria_meetings:
        slug = extract_slug_from_url(meeting['packet_url'])
        print(f"  {meeting['date']}: {meeting['title'][:50]}")
        print(f"    URL slug: {slug}")
        print(f"    Full URL: {meeting['packet_url'][:100]}")
    
    conn.close()

if __name__ == "__main__":
    main()
