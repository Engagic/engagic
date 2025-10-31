#!/usr/bin/env python3
"""Try the Portal/Meeting endpoint - the actual HTML agenda view"""

from vendors.adapters.primegov_adapter import PrimeGovAdapter
from bs4 import BeautifulSoup

city_slug = "cityofpaloalto"

with PrimeGovAdapter(city_slug) as adapter:
    api_url = f"{adapter.base_url}/api/v2/PublicPortal/ListUpcomingMeetings"
    response = adapter._get(api_url)
    meetings = response.json()

    print(f"Testing Portal/Meeting endpoint for {len(meetings)} meetings...\n")

    for i, m in enumerate(meetings[:3], 1):  # Test first 3
        print(f"\n{'=' * 80}")
        print(f"[{i}] {m.get('title')}")

        # Find HTML Agenda document
        html_doc = next(
            (d for d in m.get('documentList', [])
             if 'HTML Agenda' in d.get('templateName', '')),
            None
        )

        if not html_doc:
            print("  No HTML Agenda")
            continue

        template_id = html_doc['templateId']

        # Try Portal/Meeting endpoint
        portal_url = f"{adapter.base_url}/Portal/Meeting?meetingTemplateId={template_id}"
        print(f"\nURL: {portal_url}")

        try:
            resp = adapter._get(portal_url, timeout=15)
            html = resp.text

            print(f"SUCCESS! {len(html)} chars")

            # Parse and look for agenda items
            soup = BeautifulSoup(html, 'html.parser')

            # Look for numbered items (agenda items start with numbers)
            print("\nLooking for agenda items...")

            # Try common patterns
            patterns_to_try = [
                ('div', 'agenda-item'),
                ('div', 'item'),
                ('li', None),
                ('tr', None)
            ]

            for tag, cls in patterns_to_try:
                if cls:
                    elements = soup.find_all(tag, class_=cls)
                else:
                    elements = soup.find_all(tag)

                if elements and len(elements) < 50:  # Reasonable number
                    print(f"  Found {len(elements)} <{tag} class='{cls}'> elements")

            # Look for text that looks like agenda items ("1.", "2.", etc.)
            potential_items = []
            for text_node in soup.find_all(text=True):
                text = text_node.strip()
                if text and len(text) > 5 and text[0].isdigit() and text[1:3] in ['. ', '.\t']:
                    potential_items.append(text[:80])

            print(f"\nFound {len(potential_items)} potential agenda items (start with number):")
            for item_text in potential_items[:5]:
                print(f"  - {item_text}")

            # Save for inspection
            filename = f"/root/engagic/data/portal_{template_id}.html"
            with open(filename, 'w') as f:
                f.write(html)
            print(f"\nSaved to: {filename}")

        except Exception as e:
            print(f"ERROR: {e}")
