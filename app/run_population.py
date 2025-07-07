from sqlalchemy import func
from uszipcode import SearchEngine, SimpleZipcode
from database import MeetingDatabase
import requests
import time
import re
from random import uniform
from urllib.parse import quote_plus

#db = MeetingDatabase()
search_session = requests.Session()
search_session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1'
})

vendor_names = ["granicus", "primegov", "legistar", "civicclerk", "novusagenda", "civicplus", "municode"]

with SearchEngine() as search:
    session = search.ses
    if session is not None:
        results = (
            session.query(
                SimpleZipcode.major_city,
                SimpleZipcode.state,
                func.sum(SimpleZipcode.population).label("population"),
            )
            .group_by(SimpleZipcode.major_city, SimpleZipcode.state)
            .order_by(func.sum(SimpleZipcode.population).desc())
            .limit(100)  # Start with 100 cities
            .all()
        )
        
        for city, state, pop in results:
            # Check if city already exists
            for vendor in vendor_names:
                time.sleep(uniform(.1, .3))
                
                query = quote_plus(f"{city},{state} {vendor}")
                print(f"querying with {query}")
                response = search_session.get(
                    f"https://www.google.com/search?q={query}",
                    timeout=10
                )
                
                # Look for URLs matching pattern: {city_slug}.{vendor}
                # This regex looks for URLs containing the vendor name
                pattern = rf'https?://([a-z0-9\-]+)\.{vendor}\.(com|gov|org|net)'
                matches = re.findall(pattern, response.text, re.IGNORECASE)

                city_lower = city.lower().replace(' ', '').replace('-', '')
                if any(part in city_slug for part in [city_lower, city_lower[:4]]):
                    print(f"for {city} we found {city_slug} and {vendor} using this url: {url}")
                    # Add to DB
                else:
                    print(f"SKIPPING: {city} -> {city_slug} doesn't match!")
                
                if matches:

                    city_slug = matches[0][0]  # Get the first match
                    url = f"https://{city_slug}.{vendor}.{matches[0][1]}"
                    
                    print(f"for {city} we found {city_slug} and {vendor} using this url: {url}")
                    
                    # Uncomment to actually add to database
                    # try:
                    #     db.add_city(
                    #         city_name=city,
                    #         state=state,
                    #         city_slug=city_slug,
                    #         vendor=vendor
                    #     )
                    # except Exception as e:
                    #     print(f"Error adding {city}: {e}")
                    
                    break  # Found a vendor for this city, move to next city