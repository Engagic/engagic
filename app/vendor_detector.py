#!/usr/bin/env python3
"""
Enhanced vendor detection system with multiple search strategies.
Improves accuracy of city council website discovery and vendor identification.
"""

import requests
import time
import re
from typing import Dict, List, Optional
from urllib.parse import urlparse, quote_plus
from dataclasses import dataclass


@dataclass
class VendorMatch:
    vendor: str
    city_slug: str
    confidence: float
    url: str
    detection_method: str


class VendorDetector:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }
        )

        # Rate limiting
        self.last_request_time = 0
        self.request_delay = 1.5

        # Vendor patterns with confidence scores
        self.vendor_patterns = {
            "primegov": {
                "domain_patterns": [r"(\w+)\.primegov\.com"],
                "path_patterns": [],
                "confidence_base": 0.95,
            },
            "legistar": {
                "domain_patterns": [r"(\w+)\.legistar\.com"],
                "path_patterns": [r"legistar\.com/(\w+)"],
                "confidence_base": 0.90,
            },
            "civicplus": {
                "domain_patterns": [r"(\w+)\.civicplus\.com"],
                "path_patterns": [r"civicplus\.com/(\w+)"],
                "confidence_base": 0.85,
            },
            "granicus": {
                "domain_patterns": [r"(\w+)\.granicus\.com"],
                "path_patterns": [r"granicus\.com/(\w+)"],
                "confidence_base": 0.85,
            },
            "municode": {
                "domain_patterns": [r"(\w+)\.municode\.com"],
                "path_patterns": [r"municode\.com/(\w+)"],
                "confidence_base": 0.80,
            },
            "civicweb": {
                "domain_patterns": [r"(\w+)\.civicweb\.net"],
                "path_patterns": [],
                "confidence_base": 0.80,
            },
            "swagit": {
                "domain_patterns": [r"(\w+)\.swagit\.com"],
                "path_patterns": [],
                "confidence_base": 0.75,
            },
        }

        # City website patterns (direct government sites)
        self.gov_patterns = [r"([\w-]+)\.gov", r"([\w-]+)\.org", r"([\w-]+)\.us"]

    def rate_limit(self):
        """Enforce rate limiting between requests"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.request_delay:
            time.sleep(self.request_delay - time_since_last)
        self.last_request_time = time.time()

    def normalize_city_name(self, city_name: str) -> List[str]:
        """Generate variations of city name for matching"""
        variations = []

        # Original name
        variations.append(city_name.lower())

        # Remove common prefixes/suffixes
        clean_name = city_name.lower()
        clean_name = re.sub(
            r"^(city of|town of|village of|borough of)\s+", "", clean_name
        )
        clean_name = re.sub(r"\s+(city|town|village|borough)$", "", clean_name)
        variations.append(clean_name)

        # Remove spaces and special characters
        no_spaces = re.sub(r"[^a-z0-9]", "", clean_name)
        variations.append(no_spaces)

        # With common prefixes
        variations.extend(
            [f"cityof{no_spaces}", f"city{no_spaces}", f"townof{no_spaces}"]
        )

        return list(set(variations))  # Remove duplicates

    def search_with_multiple_queries(self, city_name: str, state: str) -> List[str]:
        """Perform multiple search queries to find city council websites"""
        urls = []

        search_queries = [
            f"{city_name} {state} city council meetings",
            f"{city_name} {state} city government agendas",
            f"{city_name} {state} municipal meetings",
            f'"{city_name}" {state} site:primegov.com OR site:legistar.com',
            f"{city_name} {state} official website city hall",
        ]

        for query in search_queries:
            self.rate_limit()
            query_urls = self.perform_search(query)
            urls.extend(query_urls)

            # Stop if we found enough URLs
            if len(urls) >= 20:
                break

        return list(set(urls))  # Remove duplicates

    def perform_search(self, query: str) -> List[str]:
        """Perform a single search query and extract URLs"""
        try:
            search_url = f"https://www.google.com/search?q={quote_plus(query)}"
            response = self.session.get(search_url, timeout=10)
            response.raise_for_status()

            # Extract URLs from search results
            url_pattern = r'href="(https?://[^"]+)"'
            urls = re.findall(url_pattern, response.text)

            # Filter and clean URLs
            clean_urls = []
            for url in urls:
                # Skip Google's own URLs
                if "google.com" in url or "gstatic.com" in url:
                    continue

                # Decode URL if needed
                if url.startswith("/url?q="):
                    continue

                clean_urls.append(url)

            return clean_urls[:10]  # Return first 10 results

        except Exception as e:
            print(f"Search failed for query '{query}': {e}")
            return []

    def analyze_url_for_vendor(
        self, url: str, city_variations: List[str]
    ) -> Optional[VendorMatch]:
        """Analyze a URL to detect vendor and extract city slug"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            path = parsed.path.lower()

            # Check vendor patterns
            for vendor, patterns in self.vendor_patterns.items():
                # Check domain patterns
                for pattern in patterns["domain_patterns"]:
                    match = re.search(pattern, domain)
                    if match:
                        slug = match.group(1)
                        confidence = self.calculate_confidence(
                            slug, city_variations, patterns["confidence_base"]
                        )
                        return VendorMatch(
                            vendor=vendor,
                            city_slug=slug,
                            confidence=confidence,
                            url=url,
                            detection_method=f"domain_pattern:{pattern}",
                        )

                # Check path patterns
                for pattern in patterns["path_patterns"]:
                    match = re.search(pattern, f"{domain}{path}")
                    if match:
                        slug = match.group(1)
                        confidence = self.calculate_confidence(
                            slug, city_variations, patterns["confidence_base"] * 0.9
                        )
                        return VendorMatch(
                            vendor=vendor,
                            city_slug=slug,
                            confidence=confidence,
                            url=url,
                            detection_method=f"path_pattern:{pattern}",
                        )

            # Check for direct government sites
            for pattern in self.gov_patterns:
                match = re.search(pattern, domain)
                if match:
                    slug = match.group(1)
                    confidence = self.calculate_confidence(slug, city_variations, 0.60)
                    return VendorMatch(
                        vendor="direct",
                        city_slug=slug,
                        confidence=confidence,
                        url=url,
                        detection_method=f"gov_pattern:{pattern}",
                    )

        except Exception as e:
            print(f"Error analyzing URL {url}: {e}")

        return None

    def calculate_confidence(
        self, slug: str, city_variations: List[str], base_confidence: float
    ) -> float:
        """Calculate confidence score based on slug matching city variations"""
        slug_clean = slug.lower()

        # Exact match
        if slug_clean in city_variations:
            return base_confidence

        # Partial match
        for variation in city_variations:
            if variation in slug_clean or slug_clean in variation:
                return base_confidence * 0.8

        # Check for common patterns
        for variation in city_variations:
            # Remove common differences
            variation_clean = re.sub(r"[^a-z0-9]", "", variation)
            slug_super_clean = re.sub(r"[^a-z0-9]", "", slug_clean)

            if variation_clean == slug_super_clean:
                return base_confidence * 0.9

        # Default lower confidence for no match
        return base_confidence * 0.3

    def discover_vendor(self, city_name: str, state: str) -> Optional[VendorMatch]:
        """Main method to discover vendor for a city"""
        print(f"Discovering vendor for {city_name}, {state}")

        # Generate city name variations
        city_variations = self.normalize_city_name(city_name)
        print(f"City variations: {city_variations}")

        # Search for URLs
        urls = self.search_with_multiple_queries(city_name, state)
        print(f"Found {len(urls)} URLs to analyze")

        # Analyze URLs for vendor matches
        matches = []
        for url in urls:
            match = self.analyze_url_for_vendor(url, city_variations)
            if match:
                matches.append(match)

        if not matches:
            print("No vendor matches found")
            return None

        # Sort by confidence and return best match
        matches.sort(key=lambda x: x.confidence, reverse=True)
        best_match = matches[0]

        print(
            f"Best match: {best_match.vendor} (confidence: {best_match.confidence:.2f})"
        )
        print(f"City slug: {best_match.city_slug}")
        print(f"URL: {best_match.url}")
        print(f"Method: {best_match.detection_method}")

        return best_match

    def batch_discover_vendors(self, cities: List[Dict]) -> Dict[str, VendorMatch]:
        """Discover vendors for multiple cities"""
        results = {}

        for i, city in enumerate(cities, 1):
            city_key = f"{city['city_name']},{city['state']}"
            print(f"\n[{i}/{len(cities)}] Processing {city_key}")

            match = self.discover_vendor(city["city_name"], city["state"])
            if match:
                results[city_key] = match

            # Progress update
            if i % 10 == 0:
                print(f"\nProgress: {i}/{len(cities)} cities processed")
                print(f"Vendors found: {len(results)}")

        return results


def main():
    """Test the vendor detector"""
    detector = VendorDetector()

    # Test cities
    test_cities = [
        {"city_name": "Palo Alto", "state": "CA"},
        {"city_name": "Boston", "state": "MA"},
        {"city_name": "Austin", "state": "TX"},
        {"city_name": "Portland", "state": "OR"},
    ]

    results = detector.batch_discover_vendors(test_cities)

    print("\n\nResults Summary:")
    print(f"Cities processed: {len(test_cities)}")
    print(f"Vendors discovered: {len(results)}")

    for city_key, match in results.items():
        print(
            f"{city_key}: {match.vendor} ({match.city_slug}) - {match.confidence:.2f}"
        )


if __name__ == "__main__":
    main()
