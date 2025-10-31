"""
Test Granicus adapter across multiple cities to validate pattern consistency
"""

import sys
sys.path.insert(0, '/Users/origami/engagic')

from vendors.adapters.granicus_adapter import GranicusAdapter
from bs4 import BeautifulSoup
import requests

# Test cities from different regions
TEST_CITIES = [
    ('addison', 'Addison, IL'),
    ('santamonica', 'Santa Monica, CA'),
    ('bellevue', 'Bellevue, WA'),
    ('paloalto', 'Palo Alto, CA'),
    ('cambridge', 'Cambridge, MA'),
]

def analyze_city_structure(slug, name):
    """Analyze HTML structure for upcoming meetings section"""
    print(f"\n{'='*60}")
    print(f"Testing: {name} ({slug})")
    print('='*60)

    try:
        # Fetch HTML
        base_url = f"https://{slug}.granicus.com"

        # Try to discover view_id
        view_id = None
        for i in range(1, 10):
            try:
                url = f"{base_url}/ViewPublisher.php?view_id={i}"
                response = requests.get(url, timeout=10)
                if response.status_code == 200 and 'Meeting' in response.text:
                    view_id = i
                    break
            except:
                continue

        if not view_id:
            print(f"✗ Could not discover view_id")
            return None

        url = f"{base_url}/ViewPublisher.php?view_id={view_id}"
        print(f"URL: {url}")

        response = requests.get(url, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Check for upcoming section patterns
        patterns_found = []

        # Pattern 1: id="upcoming"
        upcoming_by_id = soup.find("div", {"id": "upcoming"})
        if upcoming_by_id:
            patterns_found.append("div#upcoming")
            links = upcoming_by_id.find_all("a", href=True)
            agenda_links = [l for l in links if "AgendaViewer" in l.get("href", "")]
            print(f"✓ Found div#upcoming with {len(agenda_links)} agenda links")

        # Pattern 2: class="archive" id="upcoming"
        upcoming_by_class = soup.find("div", {"class": "archive", "id": "upcoming"})
        if upcoming_by_class:
            patterns_found.append("div.archive#upcoming")

        # Pattern 3: Heading with "upcoming" text
        upcoming_headings = soup.find_all(["h1", "h2", "h3", "h4"],
                                         string=lambda t: t and "upcoming" in t.lower())
        if upcoming_headings:
            patterns_found.append(f"heading: '{upcoming_headings[0].get_text(strip=True)}'")
            print(f"✓ Found heading: '{upcoming_headings[0].get_text(strip=True)}'")

        # Pattern 4: Look for "future" or "scheduled" alternatives
        future_headings = soup.find_all(["h1", "h2", "h3", "h4"],
                                       string=lambda t: t and any(word in t.lower()
                                                                  for word in ["future", "scheduled", "coming"]))
        if future_headings:
            for h in future_headings:
                patterns_found.append(f"heading: '{h.get_text(strip=True)}'")
                print(f"✓ Found heading: '{h.get_text(strip=True)}'")

        # Count total agenda links on page
        all_agenda_links = soup.find_all("a", href=lambda h: h and "AgendaViewer" in h)
        print(f"Total agenda links on page: {len(all_agenda_links)}")

        # Test our adapter
        print(f"\nTesting adapter...")
        adapter = GranicusAdapter(slug)
        meetings = list(adapter.fetch_meetings())
        print(f"✓ Adapter returned {len(meetings)} meetings")

        result = {
            'slug': slug,
            'name': name,
            'view_id': view_id,
            'patterns': patterns_found,
            'total_links': len(all_agenda_links),
            'adapter_meetings': len(meetings),
            'success': len(meetings) <= 20  # Reasonable threshold
        }

        if len(meetings) <= 20:
            print(f"✓ SUCCESS: Reasonable meeting count")
        else:
            print(f"✗ WARNING: Got {len(meetings)} meetings (might be processing history)")

        return result

    except Exception as e:
        print(f"✗ ERROR: {e}")
        return None

def main():
    print("GRANICUS MULTI-CITY PATTERN ANALYSIS")
    print("="*60)

    results = []
    for slug, name in TEST_CITIES:
        result = analyze_city_structure(slug, name)
        if result:
            results.append(result)

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    successful = [r for r in results if r and r['success']]
    print(f"\nSuccessful: {len(successful)}/{len(results)}")

    # Pattern consistency
    all_patterns = set()
    for r in results:
        if r:
            all_patterns.update(r['patterns'])

    print(f"\nPatterns found across cities:")
    for pattern in sorted(all_patterns):
        cities_with_pattern = [r['name'] for r in results if r and pattern in r['patterns']]
        print(f"  {pattern}: {len(cities_with_pattern)} cities")
        print(f"    {', '.join(cities_with_pattern)}")

    # Recommendations
    print("\n" + "="*60)
    print("RECOMMENDATIONS")
    print("="*60)

    if 'div#upcoming' in all_patterns:
        print("✓ div#upcoming is a common pattern - primary target")
    if any('heading' in p for p in all_patterns):
        print("✓ Heading-based detection needed as fallback")
    if len(successful) < len(results):
        print("⚠ Some cities need alternative approaches")

if __name__ == "__main__":
    main()
