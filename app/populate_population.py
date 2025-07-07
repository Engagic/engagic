from sqlalchemy import func
from uszipcode import SearchEngine, SimpleZipcode
from playwright.sync_api import sync_playwright
import time
import re
from random import uniform, choice
from urllib.parse import quote_plus

# pip install playwright
# playwright install chromium  # Run once to install browser

vendor_names = ["granicus", "primegov", "legistar", "civicclerk", "novusagenda", "civicplus", "municode"]

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
            .limit(100)  # Start with 100 cities
            .all()
        )
        
        found_count = 0
        
        for city, state, pop in results:
            for vendor in vendor_names:
                # Random delay between searches
                time.sleep(uniform(2, 5))
                
                query = quote_plus(f"{city},{state} {vendor}")
                print(f"🔍 Searching: {city}, {state} - {vendor}")
                
                try:
                    html = search_google_with_playwright(query)
                    
                    # Look for URLs matching pattern: {city_slug}.{vendor}
                    pattern = rf'https?://([a-z0-9\-]+)\.{vendor}\.(com|gov|org|net)'
                    matches = re.findall(pattern, html, re.IGNORECASE)
                    
                    if matches:
                        city_slug = matches[0][0]  # Get the first match
                        url = f"https://{city_slug}.{vendor}.{matches[0][1]}"
                        
                        # Validate the match
                        city_lower = city.lower().replace(' ', '').replace('-', '')
                        if any(part in city_slug for part in [city_lower, city_lower[:4]]):
                            print(f"✅ FOUND: {city} → {city_slug} @ {vendor} ({url})")
                            found_count += 1
                            
                            # Uncomment to actually add to database
                            # from database import MeetingDatabase
                            # db = MeetingDatabase()
                            # try:
                            #     db.add_city(
                            #         city_name=city,
                            #         state=state,
                            #         city_slug=city_slug,
                            #         vendor=vendor
                            #     )
                            # except Exception as e:
                            #     print(f"❌ Error adding {city}: {e}")
                            
                            break  # Found a vendor for this city, move to next city
                        else:
                            print(f"❌ SKIP: {city} → {city_slug} (doesn't match)")
                    
                except Exception as e:
                    print(f"⚠️ Error searching {city}, {state} - {vendor}: {e}")
                    time.sleep(10)  # Extra delay on error

print(f"\n🎉 DISCOVERY COMPLETE! Found {found_count} cities with vendors")