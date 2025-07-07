import requests
import re
import time
import logging
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote_plus, urljoin, urlparse
from random import uniform
from database import MeetingDatabase
from uszipcode import SearchEngine

logger = logging.getLogger("engagic")

class CityDiscovery:
    def __init__(self):
        self.db = MeetingDatabase()
        self.session = requests.Session()
        # TODO: confidence level 8 - Google blocking mitigation through headers
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        
        # Vendor configurations with search patterns and URL regex
        self.vendors = {
            'primegov': {
                'search_term': 'primegov',
                'url_pattern': r'https://([^\.]+)\.primegov\.com',
                'site_filter': 'site:primegov.com'
            },
            'civicclerk': {
                'search_term': 'civicclerk',
                'url_pattern': r'https://([^\.]+)\.api\.civicclerk\.com',
                'site_filter': 'site:civicclerk.com'
            }
        }
        
        logger.info("Initialized CityDiscovery with vendor patterns")

    def google_search(self, query: str, num_results: int = 10) -> List[str]:
        """
        Search Google and return URLs from results
        TODO: confidence level 7 - Basic Google scraping, may need refinement
        """
        try:
            # Encode the query for URL
            encoded_query = quote_plus(query)
            search_url = f"https://www.google.com/search?q={encoded_query}&num={num_results}"
            
            logger.debug(f"Searching Google for: {query}")
            
            # Add random delay to avoid rate limiting
            time.sleep(uniform(1, 3))
            
            response = self.session.get(search_url, timeout=10)
            response.raise_for_status()
            
            # Extract URLs from search results
            # TODO: confidence level 6 - Regex may need updates as Google changes HTML
            url_pattern = r'href="(/url\?q=)?([^"&]+)'
            urls = []
            
            for match in re.finditer(url_pattern, response.text):
                url = match.group(2) if match.group(1) else match.group(2)
                # Filter out Google internal URLs
                if url.startswith('http') and not any(domain in url for domain in ['google.com', 'youtube.com', 'facebook.com']):
                    urls.append(url)
            
            logger.debug(f"Found {len(urls)} URLs for query: {query}")
            return urls[:num_results]
            
        except Exception as e:
            logger.error(f"Google search failed for query '{query}': {e}")
            return []

    def extract_city_slug(self, url: str, vendor: str) -> Optional[str]:
        """
        Extract city_slug from vendor-specific URLs
        TODO: confidence level 9 - URL patterns are well-defined
        """
        if vendor not in self.vendors:
            return None
            
        pattern = self.vendors[vendor]['url_pattern']
        match = re.search(pattern, url)
        
        if match:
            city_slug = match.group(1)
            logger.debug(f"Extracted city_slug '{city_slug}' from {url}")
            return city_slug
        
        return None

    def discover_city_vendor(self, city_name: str, state: str) -> List[Tuple[str, str]]:
        """
        Discover vendor and city_slug for a given city
        Returns list of (vendor, city_slug) tuples
        TODO: confidence level 8 - Core discovery logic
        """
        discoveries = []
        
        for vendor, config in self.vendors.items():
            # Try multiple search patterns for better coverage
            search_queries = [
                f"{city_name} {state} {config['search_term']}",
                f"{city_name} {config['search_term']} city council",
                f"{city_name} {state} {config['site_filter']}"
            ]
            
            for query in search_queries:
                try:
                    urls = self.google_search(query, num_results=5)
                    
                    for url in urls:
                        city_slug = self.extract_city_slug(url, vendor)
                        if city_slug:
                            # TODO: confidence level 7 - Basic validation of city_slug
                            if self.validate_city_slug(city_slug, vendor):
                                discoveries.append((vendor, city_slug))
                                logger.info(f"Discovered {city_name}, {state}: {vendor} -> {city_slug}")
                                break
                    
                    if discoveries:
                        break  # Stop searching once we find a match
                        
                except Exception as e:
                    logger.error(f"Error searching for {city_name}, {state} with {vendor}: {e}")
                    continue
        
        return discoveries

    def validate_city_slug(self, city_slug: str, vendor: str) -> bool:
        """
        Basic validation of discovered city_slug
        TODO: confidence level 6 - Could test actual API endpoints
        """
        # Basic sanity checks
        if not city_slug or len(city_slug) < 3:
            return False
            
        if not re.match(r'^[a-z0-9]+$', city_slug):
            return False
            
        # TODO: Could add actual API endpoint testing here
        return True

    def populate_from_zipcode_data(self, limit: int = 100) -> Dict[str, int]:
        """
        Main function to populate cities database from zipcode data
        TODO: confidence level 8 - Main orchestration function
        """
        logger.info(f"Starting city population from zipcode data, limit: {limit}")
        
        stats = {
            'processed': 0,
            'discovered': 0,
            'added': 0,
            'errors': 0
        }
        
        # Get cities from zipcode database
        with SearchEngine() as search:
            session = search.ses
            if session is None:
                logger.error("Failed to initialize zipcode search engine")
                return stats
                
            # Get top cities by population
            from sqlalchemy import func
            from uszipcode import SimpleZipcode
            
            results = (
                session.query(
                    SimpleZipcode.major_city,
                    SimpleZipcode.state,
                    func.sum(SimpleZipcode.population).label("population"),
                )
                .group_by(SimpleZipcode.major_city, SimpleZipcode.state)
                .order_by(func.sum(SimpleZipcode.population).desc())
                .limit(limit)
                .all()
            )
            
            logger.info(f"Processing {len(results)} cities from zipcode database")
            
            for city, state, population in results:
                try:
                    stats['processed'] += 1
                    
                    # Skip if city already exists in database
                    existing = self.db.get_city_by_name(city, state)
                    if existing:
                        logger.debug(f"Skipping existing city: {city}, {state}")
                        continue
                    
                    # Discover vendor and city_slug
                    discoveries = self.discover_city_vendor(city, state)
                    
                    if discoveries:
                        stats['discovered'] += 1
                        
                        # Add first discovery to database
                        vendor, city_slug = discoveries[0]
                        
                        try:
                            city_id = self.db.add_city(
                                city_name=city,
                                state=state,
                                city_slug=city_slug,
                                vendor=vendor,
                                county=None  # TODO: Could extract from zipcode data
                            )
                            stats['added'] += 1
                            logger.info(f"Added city {city}, {state} -> {vendor}:{city_slug} (ID: {city_id})")
                            
                        except Exception as e:
                            logger.error(f"Failed to add city {city}, {state}: {e}")
                            stats['errors'] += 1
                    else:
                        logger.debug(f"No vendor discovered for {city}, {state}")
                        
                except Exception as e:
                    logger.error(f"Error processing city {city}, {state}: {e}")
                    stats['errors'] += 1
                    
                # Rate limiting between cities
                time.sleep(uniform(2, 5))
                
                # Progress logging
                if stats['processed'] % 10 == 0:
                    logger.info(f"Progress: {stats['processed']}/{limit} cities processed, {stats['discovered']} discovered, {stats['added']} added")
        
        logger.info(f"City population completed: {stats}")
        return stats

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    discovery = CityDiscovery()
    
    # Test with a small batch first
    stats = discovery.populate_from_zipcode_data(limit=10)
    print(f"Discovery stats: {stats}")