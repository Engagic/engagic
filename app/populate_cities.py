#!/usr/bin/env python3
"""
Database population script for all US cities.
Populates the cities table with comprehensive zipcode data and discovers city council websites.
"""

import time
import requests
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse, quote_plus
from uszipcode import SearchEngine
from database import MeetingDatabase
import re


class CityPopulator:
    def __init__(self):
        self.db = MeetingDatabase()
        self.zipcode_search = SearchEngine()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
        # Rate limiting
        self.last_search_time = 0
        self.search_delay = 1.0  # seconds between searches
        
    def get_all_us_cities(self) -> List[Dict]:
        """Get all cities in the US with population > 1000 to focus on viable municipalities"""
        print("Fetching all US cities from zipcode database...")
        
        cities = []
        processed_cities = set()
        
        # Get all zipcodes and group by city
        for state in ['AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA', 
                     'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
                     'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
                     'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
                     'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY']:
            
            print(f"Processing state: {state}")
            zipcode_results = self.zipcode_search.by_state(state)
            
            for zipcode_obj in zipcode_results:
                if not zipcode_obj or not zipcode_obj.major_city:
                    continue
                    
                city_name = zipcode_obj.major_city
                city_key = f"{city_name.lower()},{state.lower()}"
                
                # Skip if we've already processed this city
                if city_key in processed_cities:
                    continue
                    
                # Filter by population if available
                if hasattr(zipcode_obj, 'population') and zipcode_obj.population:
                    if zipcode_obj.population < 1000:
                        continue
                
                processed_cities.add(city_key)
                
                cities.append({
                    'city_name': city_name,
                    'state': state,
                    'county': zipcode_obj.county,
                    'primary_zipcode': zipcode_obj.zipcode,
                    'population': getattr(zipcode_obj, 'population', None)
                })
                
        print(f"Found {len(cities)} unique cities to process")
        return cities
    
    def create_city_slug(self, city_name: str) -> str:
        """Generate a city slug from city name"""
        # Remove common prefixes and suffixes
        clean_name = city_name.lower()
        clean_name = re.sub(r'^(city of|town of|village of|borough of)\s+', '', clean_name)
        clean_name = re.sub(r'\s+(city|town|village|borough)$', '', clean_name)
        
        # Remove special characters and spaces
        slug = re.sub(r'[^a-z0-9]', '', clean_name)
        
        # Add common prefixes based on patterns
        if slug and not slug.startswith('cityof'):
            slug = f"cityof{slug}"
            
        return slug
    
    def search_city_council_website(self, city_name: str, state: str) -> Tuple[Optional[str], Optional[str]]:
        """Search for city council website and extract vendor/slug info"""
        
        # Rate limiting
        current_time = time.time()
        time_since_last = current_time - self.last_search_time
        if time_since_last < self.search_delay:
            time.sleep(self.search_delay - time_since_last)
        
        query = f"{city_name} {state} city council meetings"
        search_url = f"https://www.google.com/search?q={quote_plus(query)}"
        
        try:
            response = self.session.get(search_url, timeout=10)
            response.raise_for_status()
            
            # Extract URLs from search results (basic regex parsing)
            urls = re.findall(r'href="(https?://[^"]+)"', response.text)
            
            for url in urls[:5]:  # Check first 5 results
                vendor, slug = self.analyze_url_for_vendor(url, city_name)
                if vendor and slug:
                    return vendor, slug
                    
        except Exception as e:
            print(f"Search failed for {city_name}, {state}: {e}")
        
        finally:
            self.last_search_time = time.time()
            
        return None, None
    
    def analyze_url_for_vendor(self, url: str, city_name: str) -> Tuple[Optional[str], Optional[str]]:
        """Analyze URL to detect vendor and extract city slug"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # Known vendor patterns
            vendor_patterns = {
                'primegov.com': 'primegov',
                'legistar.com': 'legistar', 
                'civicplus.com': 'civicplus',
                'municode.com': 'municode',
                'granicus.com': 'granicus',
                'civicweb.net': 'civicweb',
                'swagit.com': 'swagit'
            }
            
            # Check for vendor patterns in domain
            for pattern, vendor in vendor_patterns.items():
                if pattern in domain:
                    # Extract city slug from subdomain or path
                    if vendor == 'primegov':
                        # Format: cityname.primegov.com
                        slug = domain.split('.')[0]
                        return vendor, slug
                    elif vendor == 'legistar':
                        # Format: cityname.legistar.com or legistar.com/cityname
                        if domain.count('.') > 1:
                            slug = domain.split('.')[0]
                        else:
                            path_parts = parsed.path.strip('/').split('/')
                            slug = path_parts[0] if path_parts else None
                        return vendor, slug
                    else:
                        # For other vendors, try to extract from subdomain or path
                        if domain.count('.') > 1:
                            slug = domain.split('.')[0]
                        else:
                            path_parts = parsed.path.strip('/').split('/')
                            slug = path_parts[0] if path_parts else None
                        return vendor, slug
            
            # Check for city-specific domains (city.gov, cityofname.org, etc.)
            if any(suffix in domain for suffix in ['.gov', '.org', '.us']):
                if city_name.lower().replace(' ', '') in domain.replace('-', '').replace('_', ''):
                    # This might be a direct city website
                    return 'direct', domain.split('.')[0]
                    
        except Exception as e:
            print(f"Error analyzing URL {url}: {e}")
            
        return None, None
    
    def populate_single_city(self, city_data: Dict) -> bool:
        """Populate database with single city data"""
        city_name = city_data['city_name']
        state = city_data['state']
        
        print(f"Processing: {city_name}, {state}")
        
        # Generate basic city slug
        city_slug = self.create_city_slug(city_name)
        
        # Search for vendor info
        vendor, discovered_slug = self.search_city_council_website(city_name, state)
        
        # Use discovered slug if available, otherwise use generated one
        final_slug = discovered_slug if discovered_slug else city_slug
        
        # Prepare city entry
        entry_data = {
            'city': city_name,
            'state': state,
            'city_slug': final_slug,
            'vendor': vendor,
            'county': city_data.get('county'),
            'primary_zipcode': city_data.get('primary_zipcode'),
            'all_zipcodes': [city_data.get('primary_zipcode')] if city_data.get('primary_zipcode') else [],
            'meetings': []
        }
        
        # Store in database
        try:
            self.db.store_city_entry(entry_data)
            print(f"✓ Stored: {city_name}, {state} (vendor: {vendor or 'unknown'}, slug: {final_slug})")
            return True
        except Exception as e:
            print(f"✗ Failed to store {city_name}, {state}: {e}")
            return False
    
    def populate_all_cities(self, limit: Optional[int] = None):
        """Populate database with all US cities"""
        cities = self.get_all_us_cities()
        
        if limit:
            cities = cities[:limit]
            
        total = len(cities)
        success_count = 0
        
        print(f"\nStarting population of {total} cities...")
        
        for i, city_data in enumerate(cities, 1):
            print(f"\n[{i}/{total}] ", end="")
            
            if self.populate_single_city(city_data):
                success_count += 1
                
            # Progress update every 50 cities
            if i % 50 == 0:
                print(f"\nProgress: {i}/{total} cities processed ({success_count} successful)")
                
        print("\n\nPopulation complete!")
        print(f"Total cities processed: {total}")
        print(f"Successfully stored: {success_count}")
        print(f"Failed: {total - success_count}")
    
    def update_missing_vendors(self):
        """Update cities that don't have vendor information"""
        print("Updating cities with missing vendor information...")
        
        all_cities = self.db.get_all_cities()
        missing_vendor_cities = [city for city in all_cities if not city.get('vendor')]
        
        print(f"Found {len(missing_vendor_cities)} cities without vendor info")
        
        for i, city in enumerate(missing_vendor_cities, 1):
            print(f"[{i}/{len(missing_vendor_cities)}] Updating {city['city_name']}, {city['state']}")
            
            vendor, slug = self.search_city_council_website(city['city_name'], city['state'])
            
            if vendor:
                # Update the city entry
                city['vendor'] = vendor
                if slug:
                    city['city_slug'] = slug
                    
                try:
                    self.db.store_city_entry(city)
                    print(f"✓ Updated vendor: {vendor}, slug: {slug}")
                except Exception as e:
                    print(f"✗ Failed to update: {e}")
            else:
                print("✗ No vendor found")


def main():
    """Main execution function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Populate cities database')
    parser.add_argument('--limit', type=int, help='Limit number of cities to process (for testing)')
    parser.add_argument('--update-vendors', action='store_true', help='Update missing vendor info only')
    
    args = parser.parse_args()
    
    populator = CityPopulator()
    
    if args.update_vendors:
        populator.update_missing_vendors()
    else:
        populator.populate_all_cities(limit=args.limit)


if __name__ == "__main__":
    main()