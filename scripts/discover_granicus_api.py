"""
Granicus API Discovery Tool

Mission: Find hidden APIs, undocumented endpoints, and data sources.
We refuse to accept HTML scraping when APIs might exist.

Strategies:
1. Common API endpoint patterns
2. Legistar API compatibility test (many Granicus cities are Legistar in disguise)
3. AJAX/XHR endpoint discovery from page source
4. RSS/iCal/JSON feed detection
5. ViewPublisher parameter fuzzing
6. JavaScript variable inspection for embedded data
"""

import requests
import json
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin
from bs4 import BeautifulSoup


class GranicusAPIDiscovery:
    """Aggressive API discovery for Granicus cities"""

    def __init__(self, slug: str, verbose: bool = True):
        self.slug = slug
        self.base_url = f"https://{slug}.granicus.com"
        self.verbose = verbose
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })

        self.discoveries = {
            'api_endpoints': [],
            'legistar_compatible': False,
            'legistar_slug': None,
            'ajax_endpoints': [],
            'data_feeds': [],
            'viewpublisher_params': {},
            'embedded_data': {},
            'success': False
        }

    def discover_all(self) -> Dict:
        """Run all discovery methods"""
        self.log(f"\n{'='*60}")
        self.log(f"GRANICUS API DISCOVERY: {self.slug}")
        self.log(f"{'='*60}\n")

        # Strategy 1: Test if it's Legistar in disguise
        self.test_legistar_compatibility()

        # Strategy 2: Common API patterns
        self.test_api_endpoints()

        # Strategy 3: Inspect ViewPublisher page for AJAX calls
        self.inspect_viewpublisher_page()

        # Strategy 4: Look for data feeds
        self.discover_feeds()

        # Strategy 5: Fuzz ViewPublisher parameters
        self.fuzz_viewpublisher_params()

        # Report findings
        self.report_findings()

        return self.discoveries

    def test_legistar_compatibility(self):
        """
        Test if this Granicus city responds to Legistar API calls.
        Many Granicus cities are Legistar underneath!
        """
        self.log("\n[1] TESTING LEGISTAR COMPATIBILITY")
        self.log("-" * 40)

        # Common Legistar slug patterns from Granicus subdomain
        slug_variations = [
            self.slug,  # Direct match
            self.slug.replace('-', ''),  # Remove dashes
            self.slug.replace('_', ''),  # Remove underscores
            self.slug.split('-')[0],  # First part if hyphenated
            self.slug.split('_')[0],  # First part if underscored
        ]

        for test_slug in slug_variations:
            api_url = f"https://webapi.legistar.com/v1/{test_slug}/events"
            params = {"$top": 1}

            try:
                response = self.session.get(api_url, params=params, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list) and len(data) > 0:
                        self.log(f"✓ LEGISTAR API WORKS! Slug: {test_slug}")
                        self.log(f"  URL: {api_url}")
                        self.log(f"  Sample event: {data[0].get('EventBodyName', 'N/A')}")
                        self.discoveries['legistar_compatible'] = True
                        self.discoveries['legistar_slug'] = test_slug
                        self.discoveries['success'] = True
                        return
                    else:
                        self.log(f"  × {test_slug}: API responded but no events")
                else:
                    self.log(f"  × {test_slug}: HTTP {response.status_code}")
            except Exception as e:
                self.log(f"  × {test_slug}: {type(e).__name__}")

        self.log("✗ Not Legistar compatible")

    def test_api_endpoints(self):
        """Test common API endpoint patterns"""
        self.log("\n[2] TESTING API ENDPOINTS")
        self.log("-" * 40)

        endpoints = [
            # Granicus-specific patterns
            f"{self.base_url}/api/meetings",
            f"{self.base_url}/api/v1/meetings",
            f"{self.base_url}/api/v2/meetings",
            f"{self.base_url}/api/events",
            f"{self.base_url}/api/upcoming",
            f"{self.base_url}/api/agendas",

            # Common REST patterns
            f"{self.base_url}/api/public/meetings",
            f"{self.base_url}/api/portal/meetings",
            f"{self.base_url}/rest/meetings",
            f"{self.base_url}/rest/v1/meetings",

            # Data endpoints
            f"{self.base_url}/data/meetings.json",
            f"{self.base_url}/meetings.json",
            f"{self.base_url}/api/meetings.json",
        ]

        for endpoint in endpoints:
            try:
                response = self.session.get(endpoint, timeout=5)
                if response.status_code == 200:
                    # Check if it's JSON
                    try:
                        data = response.json()
                        self.log(f"✓ FOUND API: {endpoint}")
                        self.log(f"  Type: {type(data).__name__}")
                        if isinstance(data, list):
                            self.log(f"  Items: {len(data)}")
                        self.discoveries['api_endpoints'].append({
                            'url': endpoint,
                            'type': type(data).__name__,
                            'sample': str(data)[:200]
                        })
                        self.discoveries['success'] = True
                    except json.JSONDecodeError:
                        # Maybe XML or other format
                        if 'xml' in response.headers.get('content-type', '').lower():
                            self.log(f"✓ FOUND XML: {endpoint}")
                            self.discoveries['api_endpoints'].append({
                                'url': endpoint,
                                'type': 'xml'
                            })
                elif response.status_code == 404:
                    pass  # Expected
                else:
                    self.log(f"  ? {endpoint}: HTTP {response.status_code}")
            except requests.RequestException:
                pass  # Expected for non-existent endpoints

        if not self.discoveries['api_endpoints']:
            self.log("✗ No API endpoints found")

    def inspect_viewpublisher_page(self):
        """
        Inspect ViewPublisher page source for:
        - AJAX endpoint URLs in JavaScript
        - Embedded JSON data
        - API calls made by the page
        """
        self.log("\n[3] INSPECTING VIEWPUBLISHER PAGE")
        self.log("-" * 40)

        # First discover view_id
        view_id = self._discover_view_id()
        if not view_id:
            self.log("✗ Could not discover view_id")
            return

        url = f"{self.base_url}/ViewPublisher.php?view_id={view_id}"
        self.log(f"Fetching: {url}")

        try:
            response = self.session.get(url, timeout=15)
            html = response.text

            # Look for AJAX endpoints in JavaScript
            ajax_patterns = [
                r'ajax.*?url.*?["\']([^"\']+)["\']',
                r'fetch\(["\']([^"\']+)["\']',
                r'\.get\(["\']([^"\']+)["\']',
                r'\.post\(["\']([^"\']+)["\']',
                r'XMLHttpRequest.*?open\(["\']GET["\'],\s*["\']([^"\']+)["\']',
            ]

            for pattern in ajax_patterns:
                matches = re.findall(pattern, html, re.IGNORECASE)
                for match in matches:
                    if match.startswith('http') or match.startswith('/'):
                        endpoint = urljoin(self.base_url, match)
                        if endpoint not in self.discoveries['ajax_endpoints']:
                            self.log(f"✓ Found AJAX endpoint: {endpoint}")
                            self.discoveries['ajax_endpoints'].append(endpoint)

            # Look for embedded JSON data
            json_patterns = [
                r'var\s+meetings\s*=\s*(\{.*?\}|\[.*?\]);',
                r'var\s+events\s*=\s*(\{.*?\}|\[.*?\]);',
                r'var\s+data\s*=\s*(\{.*?\}|\[.*?\]);',
            ]

            for pattern in json_patterns:
                matches = re.findall(pattern, html, re.DOTALL)
                for match in matches:
                    try:
                        data = json.loads(match)
                        self.log(f"✓ Found embedded JSON data")
                        self.discoveries['embedded_data']['meetings'] = data
                        self.discoveries['success'] = True
                    except json.JSONDecodeError:
                        pass

            # Look for API base URLs
            api_base_patterns = [
                r'apiUrl\s*=\s*["\']([^"\']+)["\']',
                r'API_BASE\s*=\s*["\']([^"\']+)["\']',
                r'baseUrl\s*=\s*["\']([^"\']+)["\']',
            ]

            for pattern in api_base_patterns:
                matches = re.findall(pattern, html, re.IGNORECASE)
                for match in matches:
                    self.log(f"✓ Found API base URL: {match}")
                    self.discoveries['ajax_endpoints'].append(match)

            if not self.discoveries['ajax_endpoints'] and not self.discoveries['embedded_data']:
                self.log("✗ No AJAX endpoints or embedded data found")

        except Exception as e:
            self.log(f"✗ Error inspecting page: {e}")

    def discover_feeds(self):
        """Look for RSS, iCal, JSON feeds"""
        self.log("\n[4] DISCOVERING DATA FEEDS")
        self.log("-" * 40)

        view_id = self._discover_view_id()

        # Granicus-specific RSS patterns
        feed_patterns = [
            f"{self.base_url}/ViewPublisherRSS.php?view_id={view_id}&mode=agendas",
            f"{self.base_url}/ViewPublisherRSS.php?view_id={view_id}&mode=minutes",
            f"{self.base_url}/rss",
            f"{self.base_url}/feed",
            f"{self.base_url}/rss.xml",
            f"{self.base_url}/feed.xml",
            f"{self.base_url}/meetings.rss",
            f"{self.base_url}/meetings.ical",
            f"{self.base_url}/calendar.ics",
            f"{self.base_url}/agendas.rss",
        ]

        for feed_url in feed_patterns:
            try:
                response = self.session.get(feed_url, timeout=5)
                if response.status_code == 200:
                    content_type = response.headers.get('content-type', '').lower()
                    if any(t in content_type for t in ['xml', 'rss', 'atom', 'calendar']):
                        self.log(f"✓ FOUND FEED: {feed_url}")
                        self.log(f"  Type: {content_type}")

                        # Parse RSS to see what's in it
                        if 'xml' in content_type or 'rss' in content_type:
                            soup = BeautifulSoup(response.content, 'xml')
                            items = soup.find_all('item')
                            self.log(f"  Items: {len(items)}")
                            if items:
                                first_item = items[0]
                                title = first_item.find('title')
                                pub_date = first_item.find('pubDate')
                                self.log(f"  Sample: {title.text if title else 'N/A'}")
                                self.log(f"  Date: {pub_date.text if pub_date else 'N/A'}")

                        self.discoveries['data_feeds'].append({
                            'url': feed_url,
                            'type': content_type,
                            'item_count': len(items) if 'items' in locals() else None
                        })
                        self.discoveries['success'] = True
            except requests.RequestException:
                pass

        if not self.discoveries['data_feeds']:
            self.log("✗ No data feeds found")

    def fuzz_viewpublisher_params(self):
        """Test ViewPublisher.php with various parameters"""
        self.log("\n[5] FUZZING VIEWPUBLISHER PARAMETERS")
        self.log("-" * 40)

        view_id = self._discover_view_id()
        if not view_id:
            return

        base_url = f"{self.base_url}/ViewPublisher.php"

        # Try various parameters
        param_tests = [
            {'view_id': view_id, 'filter': 'upcoming'},
            {'view_id': view_id, 'filter': 'future'},
            {'view_id': view_id, 'type': 'upcoming'},
            {'view_id': view_id, 'status': 'upcoming'},
            {'view_id': view_id, 'date_from': '2025-01-01'},
            {'view_id': view_id, 'format': 'json'},
            {'view_id': view_id, 'output': 'json'},
            {'view_id': view_id, 'limit': '10'},
        ]

        for params in param_tests:
            try:
                response = self.session.get(base_url, params=params, timeout=5)
                # Check if response is different from base (indicates parameter worked)
                if response.status_code == 200:
                    # Check for JSON response
                    try:
                        data = response.json()
                        self.log(f"✓ PARAMS RETURNED JSON: {params}")
                        self.discoveries['viewpublisher_params'] = params
                        self.discoveries['success'] = True
                    except json.JSONDecodeError:
                        # Check if content length is significantly different
                        pass
            except requests.RequestException:
                pass

        if not self.discoveries['viewpublisher_params']:
            self.log("✗ No useful ViewPublisher parameters found")

    def _discover_view_id(self) -> Optional[int]:
        """Quick view_id discovery"""
        for i in range(1, 10):
            try:
                url = f"{self.base_url}/ViewPublisher.php?view_id={i}"
                response = self.session.get(url, timeout=5)
                if response.status_code == 200 and 'Meeting' in response.text:
                    return i
            except:
                continue
        return None

    def report_findings(self):
        """Generate comprehensive report"""
        self.log("\n" + "="*60)
        self.log("DISCOVERY REPORT")
        self.log("="*60 + "\n")

        if self.discoveries['success']:
            self.log("🎉 SUCCESS! Found working data sources:\n")

            if self.discoveries['legistar_compatible']:
                self.log(f"✓ LEGISTAR API COMPATIBLE")
                self.log(f"  Slug: {self.discoveries['legistar_slug']}")
                self.log(f"  URL: https://webapi.legistar.com/v1/{self.discoveries['legistar_slug']}/events")
                self.log(f"  RECOMMENDATION: Switch vendor to 'legistar'\n")

            if self.discoveries['api_endpoints']:
                self.log(f"✓ API ENDPOINTS ({len(self.discoveries['api_endpoints'])})")
                for endpoint in self.discoveries['api_endpoints']:
                    self.log(f"  - {endpoint['url']}")
                self.log("")

            if self.discoveries['ajax_endpoints']:
                self.log(f"✓ AJAX ENDPOINTS ({len(self.discoveries['ajax_endpoints'])})")
                for endpoint in self.discoveries['ajax_endpoints']:
                    self.log(f"  - {endpoint}")
                self.log("")

            if self.discoveries['data_feeds']:
                self.log(f"✓ DATA FEEDS ({len(self.discoveries['data_feeds'])})")
                for feed in self.discoveries['data_feeds']:
                    self.log(f"  - {feed['url']} ({feed['type']})")
                self.log("")

            if self.discoveries['embedded_data']:
                self.log(f"✓ EMBEDDED DATA")
                self.log(f"  Found JavaScript data structures in page source")
                self.log("")

        else:
            self.log("⚠ NO API FOUND - HTML scraping required")
            self.log("  Recommendation: Parse 'Upcoming Programs' section in HTML")

    def log(self, message: str):
        """Conditional logging"""
        if self.verbose:
            print(message)


def main():
    """Test discovery on known Granicus cities"""
    import sys

    if len(sys.argv) > 1:
        slugs = sys.argv[1:]
    else:
        # Test cities
        slugs = [
            'addison',      # Addison, IL
            'cambridge',    # Cambridge, MA (might be Legistar)
            'santamonica',  # Santa Monica, CA
        ]

    results = {}

    for slug in slugs:
        discoverer = GranicusAPIDiscovery(slug, verbose=True)
        results[slug] = discoverer.discover_all()

        # Save results
        output_file = f"data/granicus_discovery_{slug}.json"
        with open(output_file, 'w') as f:
            json.dump(results[slug], f, indent=2)
        print(f"\n💾 Saved results to {output_file}")
        print("\n" + "="*60 + "\n")

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    for slug, result in results.items():
        status = "✓ API FOUND" if result['success'] else "✗ HTML ONLY"
        legistar = " (LEGISTAR!)" if result['legistar_compatible'] else ""
        print(f"{slug}: {status}{legistar}")


if __name__ == "__main__":
    main()
