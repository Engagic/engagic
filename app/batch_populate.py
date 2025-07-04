#!/usr/bin/env python3
"""
Complete batch population system for US cities database.
Combines zipcode data with vendor discovery for comprehensive city coverage.
"""

import json
import time
import argparse
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from dataclasses import asdict

from database import MeetingDatabase
from vendor_detector import VendorDetector, VendorMatch
from uszipcode import SearchEngine


class BatchPopulator:
    def __init__(self, max_workers: int = 5):
        self.db = MeetingDatabase()
        self.zipcode_search = SearchEngine()
        self.vendor_detector = VendorDetector()
        self.max_workers = max_workers
        
        # Thread-safe statistics
        self.stats_lock = threading.Lock()
        self.stats = {
            'total_processed': 0,
            'successful_stores': 0,
            'vendor_discoveries': 0,
            'errors': 0,
            'skipped_existing': 0
        }
    
    def update_stats(self, **kwargs):
        """Thread-safe statistics update"""
        with self.stats_lock:
            for key, value in kwargs.items():
                if key in self.stats:
                    self.stats[key] += value
    
    def get_stats(self) -> Dict:
        """Get current statistics"""
        with self.stats_lock:
            return self.stats.copy()
    
    def get_existing_cities(self) -> set:
        """Get set of existing cities to avoid duplicates"""
        try:
            existing = self.db.get_all_cities()
            return {f"{city['city_name'].lower()},{city['state'].lower()}" 
                   for city in existing}
        except Exception as e:
            print(f"Warning: Could not load existing cities: {e}")
            return set()
    
    def get_priority_cities(self) -> List[Dict]:
        """Get list of priority cities to process first"""
        # Focus on larger cities and state capitals first
        priority_cities = [
            # Major cities by population
            {'city_name': 'New York', 'state': 'NY'},
            {'city_name': 'Los Angeles', 'state': 'CA'},
            {'city_name': 'Chicago', 'state': 'IL'},
            {'city_name': 'Houston', 'state': 'TX'},
            {'city_name': 'Phoenix', 'state': 'AZ'},
            {'city_name': 'Philadelphia', 'state': 'PA'},
            {'city_name': 'San Antonio', 'state': 'TX'},
            {'city_name': 'San Diego', 'state': 'CA'},
            {'city_name': 'Dallas', 'state': 'TX'},
            {'city_name': 'San Jose', 'state': 'CA'},
            
            # State capitals
            {'city_name': 'Albany', 'state': 'NY'},
            {'city_name': 'Sacramento', 'state': 'CA'},
            {'city_name': 'Springfield', 'state': 'IL'},
            {'city_name': 'Austin', 'state': 'TX'},
            {'city_name': 'Boston', 'state': 'MA'},
            {'city_name': 'Denver', 'state': 'CO'},
            {'city_name': 'Atlanta', 'state': 'GA'},
            {'city_name': 'Seattle', 'state': 'WA'},
            {'city_name': 'Portland', 'state': 'OR'},
            {'city_name': 'Miami', 'state': 'FL'},
        ]
        
        return priority_cities
    
    def get_all_us_cities_optimized(self, min_population: int = 1000) -> List[Dict]:
        """Get all US cities optimized for size and relevance"""
        print(f"Fetching US cities with population >= {min_population}...")
        
        cities = []
        processed_cities = set()
        
        # Process states in order of population/importance
        states_ordered = [
            'CA', 'TX', 'FL', 'NY', 'PA', 'IL', 'OH', 'GA', 'NC', 'MI',
            'NJ', 'VA', 'WA', 'AZ', 'MA', 'TN', 'IN', 'MO', 'MD', 'WI',
            'CO', 'MN', 'SC', 'AL', 'LA', 'KY', 'OR', 'OK', 'CT', 'IA',
            'MS', 'AR', 'KS', 'UT', 'NV', 'NM', 'NE', 'WV', 'ID', 'HI',
            'NH', 'ME', 'MT', 'RI', 'DE', 'SD', 'ND', 'AK', 'VT', 'WY'
        ]
        
        for state in states_ordered:
            print(f"Processing state: {state}")
            
            try:
                # Get cities by state
                state_cities = self.zipcode_search.by_state(state)
                
                for zipcode_obj in state_cities:
                    if not zipcode_obj or not zipcode_obj.major_city:
                        continue
                    
                    city_name = zipcode_obj.major_city
                    city_key = f"{city_name.lower()},{state.lower()}"
                    
                    # Skip duplicates
                    if city_key in processed_cities:
                        continue
                    
                    # Filter by population
                    population = getattr(zipcode_obj, 'population', 0) or 0
                    if population < min_population:
                        continue
                    
                    processed_cities.add(city_key)
                    
                    cities.append({
                        'city_name': city_name,
                        'state': state,
                        'county': zipcode_obj.county,
                        'primary_zipcode': zipcode_obj.zipcode,
                        'population': population
                    })
                    
            except Exception as e:
                print(f"Error processing state {state}: {e}")
                continue
        
        # Sort by population (descending) to prioritize larger cities
        cities.sort(key=lambda x: x.get('population', 0), reverse=True)
        
        print(f"Found {len(cities)} cities to process")
        return cities
    
    def process_single_city(self, city_data: Dict, discover_vendor: bool = True) -> bool:
        """Process a single city with vendor discovery"""
        city_name = city_data['city_name']
        state = city_data['state']
        city_key = f"{city_name.lower()},{state.lower()}"
        
        try:
            # Basic city slug generation
            city_slug = self.generate_city_slug(city_name)
            vendor = None
            discovered_slug = None
            
            # Discover vendor if requested
            if discover_vendor:
                try:
                    vendor_match = self.vendor_detector.discover_vendor(city_name, state)
                    if vendor_match and vendor_match.confidence > 0.5:
                        vendor = vendor_match.vendor
                        discovered_slug = vendor_match.city_slug
                        self.update_stats(vendor_discoveries=1)
                except Exception as e:
                    print(f"Vendor discovery failed for {city_key}: {e}")
            
            # Prepare city entry
            entry_data = {
                'city': city_name,
                'state': state,
                'city_slug': discovered_slug or city_slug,
                'vendor': vendor,
                'county': city_data.get('county'),
                'primary_zipcode': city_data.get('primary_zipcode'),
                'all_zipcodes': [city_data.get('primary_zipcode')] if city_data.get('primary_zipcode') else [],
                'meetings': []
            }
            
            # Store in database
            self.db.store_city_entry(entry_data)
            self.update_stats(successful_stores=1)
            
            print(f"✓ {city_key} (vendor: {vendor or 'unknown'}, slug: {entry_data['city_slug']})")
            return True
            
        except Exception as e:
            print(f"✗ Failed to process {city_key}: {e}")
            self.update_stats(errors=1)
            return False
        finally:
            self.update_stats(total_processed=1)
    
    def generate_city_slug(self, city_name: str) -> str:
        """Generate basic city slug"""
        import re
        clean_name = city_name.lower()
        clean_name = re.sub(r'^(city of|town of|village of|borough of)\s+', '', clean_name)
        clean_name = re.sub(r'\s+(city|town|village|borough)$', '', clean_name)
        slug = re.sub(r'[^a-z0-9]', '', clean_name)
        return f"cityof{slug}" if slug else "unknown"
    
    def populate_batch_sequential(self, cities: List[Dict], discover_vendors: bool = True):
        """Process cities sequentially (more reliable for large batches)"""
        total = len(cities)
        existing_cities = self.get_existing_cities()
        
        print(f"Starting sequential processing of {total} cities...")
        print(f"Vendor discovery: {'enabled' if discover_vendors else 'disabled'}")
        
        for i, city_data in enumerate(cities, 1):
            city_key = f"{city_data['city_name'].lower()},{city_data['state'].lower()}"
            
            # Skip existing cities
            if city_key in existing_cities:
                print(f"[{i}/{total}] ⊘ Skipping existing: {city_key}")
                self.update_stats(skipped_existing=1, total_processed=1)
                continue
            
            print(f"[{i}/{total}] Processing: {city_key}")
            self.process_single_city(city_data, discover_vendors)
            
            # Progress report every 25 cities
            if i % 25 == 0:
                stats = self.get_stats()
                print(f"\n--- Progress Report ---")
                print(f"Processed: {stats['total_processed']}/{total}")
                print(f"Successful: {stats['successful_stores']}")
                print(f"Vendors found: {stats['vendor_discoveries']}")
                print(f"Errors: {stats['errors']}")
                print(f"Skipped: {stats['skipped_existing']}")
                print("----------------------\n")
    
    def populate_batch_parallel(self, cities: List[Dict], discover_vendors: bool = True):
        """Process cities in parallel (faster but more resource intensive)"""
        total = len(cities)
        existing_cities = self.get_existing_cities()
        
        # Filter out existing cities
        new_cities = [
            city for city in cities 
            if f"{city['city_name'].lower()},{city['state'].lower()}" not in existing_cities
        ]
        
        print(f"Starting parallel processing...")
        print(f"Total cities: {total}, New cities: {len(new_cities)}")
        print(f"Vendor discovery: {'enabled' if discover_vendors else 'disabled'}")
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_city = {
                executor.submit(self.process_single_city, city, discover_vendors): city
                for city in new_cities
            }
            
            # Process completed tasks
            for i, future in enumerate(as_completed(future_to_city), 1):
                city = future_to_city[future]
                city_key = f"{city['city_name']},{city['state']}"
                
                try:
                    success = future.result()
                    if success:
                        print(f"[{i}/{len(new_cities)}] ✓ {city_key}")
                    else:
                        print(f"[{i}/{len(new_cities)}] ✗ {city_key}")
                except Exception as e:
                    print(f"[{i}/{len(new_cities)}] ✗ {city_key}: {e}")
                    self.update_stats(errors=1, total_processed=1)
                
                # Progress report
                if i % 50 == 0:
                    stats = self.get_stats()
                    print(f"\n--- Progress Report ---")
                    print(f"Processed: {i}/{len(new_cities)}")
                    print(f"Successful: {stats['successful_stores']}")
                    print(f"Vendors found: {stats['vendor_discoveries']}")
                    print(f"Errors: {stats['errors']}")
                    print("----------------------\n")
    
    def run_full_population(self, 
                           min_population: int = 1000,
                           parallel: bool = False,
                           discover_vendors: bool = True,
                           priority_first: bool = True):
        """Run complete database population"""
        
        print("=== US Cities Database Population ===")
        
        cities_to_process = []
        
        # Add priority cities first
        if priority_first:
            print("Adding priority cities...")
            priority_cities = self.get_priority_cities()
            cities_to_process.extend(priority_cities)
        
        # Add all other cities
        print("Loading all US cities...")
        all_cities = self.get_all_us_cities_optimized(min_population)
        
        # Remove priority cities from all_cities to avoid duplicates
        if priority_first:
            priority_keys = {f"{c['city_name'].lower()},{c['state'].lower()}" 
                            for c in priority_cities}
            all_cities = [
                city for city in all_cities 
                if f"{city['city_name'].lower()},{city['state'].lower()}" not in priority_keys
            ]
        
        cities_to_process.extend(all_cities)
        
        print(f"Total cities to process: {len(cities_to_process)}")
        
        # Start processing
        start_time = time.time()
        
        if parallel:
            self.populate_batch_parallel(cities_to_process, discover_vendors)
        else:
            self.populate_batch_sequential(cities_to_process, discover_vendors)
        
        # Final statistics
        end_time = time.time()
        duration = end_time - start_time
        stats = self.get_stats()
        
        print(f"\n=== Population Complete ===")
        print(f"Duration: {duration/60:.1f} minutes")
        print(f"Total processed: {stats['total_processed']}")
        print(f"Successful stores: {stats['successful_stores']}")
        print(f"Vendor discoveries: {stats['vendor_discoveries']}")
        print(f"Errors: {stats['errors']}")
        print(f"Skipped existing: {stats['skipped_existing']}")
        print(f"Success rate: {stats['successful_stores']/max(stats['total_processed'], 1)*100:.1f}%")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Batch populate cities database')
    parser.add_argument('--min-population', type=int, default=1000,
                       help='Minimum population for cities (default: 1000)')
    parser.add_argument('--parallel', action='store_true',
                       help='Use parallel processing (faster but more resource intensive)')
    parser.add_argument('--no-vendors', action='store_true',
                       help='Skip vendor discovery (faster)')
    parser.add_argument('--no-priority', action='store_true',
                       help='Skip priority cities first')
    parser.add_argument('--test', action='store_true',
                       help='Test run with small subset of cities')
    
    args = parser.parse_args()
    
    populator = BatchPopulator(max_workers=3 if args.parallel else 1)
    
    if args.test:
        print("=== TEST RUN ===")
        test_cities = populator.get_priority_cities()[:5]
        if args.parallel:
            populator.populate_batch_parallel(test_cities, not args.no_vendors)
        else:
            populator.populate_batch_sequential(test_cities, not args.no_vendors)
    else:
        populator.run_full_population(
            min_population=args.min_population,
            parallel=args.parallel,
            discover_vendors=not args.no_vendors,
            priority_first=not args.no_priority
        )


if __name__ == "__main__":
    main()