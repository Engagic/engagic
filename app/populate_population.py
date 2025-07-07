from sqlalchemy import func
from uszipcode import SearchEngine, SimpleZipcode
from playwright.sync_api import sync_playwright
import time
import json
import re
from random import uniform, choice
from urllib.parse import quote_plus

# pip install playwright
# playwright install chromium  # Run once to install browser

vendor_names = ["granicus", "primegov", "legistar", "civicclerk", "novusagenda", "civicplus", "municode"]

found_cities = []  # Track all discovered cities


def get_random_viewport():
    """Random viewport sizes to look more human"""
    viewports = [
        {'width': 1920, 'height': 1080},
        {'width': 1366, 'height': 768},
        {'width': 1536, 'height': 864},
        {'width': 1440, 'height': 900},
        {'width': 1280, 'height': 720},
    ]
    return choice(viewports)

def search_google_with_playwright(query):
    """Search Google using Playwright - undetectable AF"""
    with sync_playwright() as p:
        # Launch with stealth options
        browser = p.chromium.launch(
            headless=True,  # Set to False to watch the magic happen
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--no-sandbox',
            ]
        )
        
        # Random user agent
        user_agents = [
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',
        ]
        
        context = browser.new_context(
            viewport=get_random_viewport(),
            user_agent=choice(user_agents),
            locale='en-US',
            timezone_id='America/New_York',
        )
        
        # Add some stealth scripts
        context.add_init_script("""
            // Override the navigator.webdriver property
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // Mock plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            
            // Mock languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
        """)
        
        page = context.new_page()
        
        try:
            # Navigate to Google
            page.goto(f"https://www.google.com/search?q={query}", wait_until='networkidle')
            
            # Random human-like delay
            page.wait_for_timeout(int(uniform(500, 1500)))
            
            # Get the HTML
            html = page.content()
            
            return html
            
        finally:
            browser.close()


def extract_city_and_url(html, vendor):
    """Extract city slug and URL from various vendor patterns"""
    
    # Multiple patterns to catch different URL structures
    patterns = [
        # Standard: city_slug.vendor.com
        (rf'https?://([a-z0-9\-]+)\.{vendor}\.(com|gov|org|net)', 'standard'),
        # Vendor first with council: vendor.council.city_slug.gov
        (rf'https?://{vendor}\.council\.([a-z0-9\-]+)\.(com|gov|org|net)', 'council'),
        # Vendor first with any subdomain: vendor.subdomain.city_slug.gov
        (rf'https?://{vendor}\.[a-z0-9\-]+\.([a-z0-9\-]+)\.(com|gov|org|net)', 'subdomain'),
        # City first with vendor subdomain: city_slug.vendor.something.gov
        (rf'https?://([a-z0-9\-]+)\.{vendor}\.[a-z0-9\-]+\.(com|gov|org|net)', 'city_first'),
    ]
    
    for pattern, pattern_type in patterns:
        matches = re.findall(pattern, html, re.IGNORECASE)
        if matches:
            if pattern_type == 'standard':
                city_slug = matches[0][0]
                domain = matches[0][1]
                url = f"https://{city_slug}.{vendor}.{domain}"
            elif pattern_type == 'council':
                city_slug = matches[0][0]
                domain = matches[0][1]
                url = f"https://{vendor}.council.{city_slug}.{domain}"
            elif pattern_type == 'subdomain':
                city_slug = matches[0][1]
                domain = matches[0][2]
                # Try to find the actual URL in the HTML
                url_pattern = rf'https?://{vendor}\.[a-z0-9\-]+\.{city_slug}\.{domain}'
                url_match = re.search(url_pattern, html, re.IGNORECASE)
                url = url_match.group(0) if url_match else f"https://{vendor}.{city_slug}.{domain}"
            elif pattern_type == 'city_first':
                city_slug = matches[0][0]
                domain = matches[0][2]
                url = f"https://{city_slug}.{vendor}.{domain}"
            
            return city_slug, url
    
    return None, None


def validate_city_match(city, state, city_slug):
    """Validate if the city_slug matches the city name"""
    city_lower = city.lower().replace(' ', '').replace('-', '')
    
    # Special city mappings
    special_cases = {
        'newyork': ['nyc', 'newyorkc', 'newyorkcity'],
        'losangeles': ['lacity', 'losangelesca', 'la-city'],
        'sanfrancisco': ['sfgov', 'sf', 'sfo'],
        'philadelphia': ['phila', 'philadelphiapa'],
        'washingtondc': ['dc', 'dcgov', 'washdc'],
        'washington': ['dc', 'dcgov', 'washdc'],
        'saintlouis': ['stlouis', 'stl'],
        'saintpaul': ['stpaul'],
    }
    
    # Check if it's a special case
    city_key = city_lower.replace(' ', '')
    if city_key in special_cases:
        if any(special in city_slug for special in special_cases[city_key]):
            return True
    
    # Regular validation - check if city name or part of it is in the slug
    return any(part in city_slug for part in [city_lower, city_lower[:4]])


# Main script starts here
print("🚀 STARTING CITY DISCOVERY WITH PLAYWRIGHT 🚀")

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
            .offset(100)
            .limit(1000)  # Start with 100 cities
            .all()
        )
        
        found_count = 0
        
        for city, state, pop in results:
            city_found = False
            
            for vendor in vendor_names:
                if city_found:
                    break
                    
                # Random delay between searches
                time.sleep(uniform(2, 5))
                
                query = quote_plus(f"{city},{state} {vendor}")
                print(f"🔍 Searching: {city}, {state} - {vendor}")
                
                try:
                    html = search_google_with_playwright(query)
                    
                    # Extract city slug and URL using multiple patterns
                    city_slug, url = extract_city_and_url(html, vendor)
                    
                    if city_slug and url:
                        # Validate the match
                        if validate_city_match(city, state, city_slug):
                            found_cities.append({
                                'city_name': city,
                                'state': state,
                                'city_slug': city_slug,
                                'vendor': vendor,
                                'url': url,
                                'population': int(pop)
                            })
                            found_count += 1
                            city_found = True
                            
                            print(f"✅ FOUND: {city}, {state} → {city_slug} @ {vendor} ({url})")
                            break
                        else:
                            print(f"❌ SKIP: {city} → {city_slug} (doesn't match)")
                    
                except Exception as e:
                    print(f"⚠️ Error searching {city}, {state} - {vendor}: {e}")
                    time.sleep(10)  # Extra delay on error

print(f"\n🎉 Discovery complete! Found {found_count} cities with vendors")

# Save results to JSON
with open('discovered_cities.json', 'w') as f:
    json.dump(found_cities, f, indent=2)
print(f"💾 Saved {len(found_cities)} cities to discovered_cities.json")

# Print summary
print("\n📊 Summary by vendor:")
vendor_counts = {}
for city in found_cities:
    vendor = city['vendor']
    vendor_counts[vendor] = vendor_counts.get(vendor, 0) + 1

for vendor, count in sorted(vendor_counts.items(), key=lambda x: x[1], reverse=True):
    print(f"  {vendor}: {count} cities")