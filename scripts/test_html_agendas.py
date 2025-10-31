#!/usr/bin/env python3
"""Try fetching HTML agenda for each meeting to see which ones work"""

from vendors.adapters.primegov_adapter import PrimeGovAdapter
from urllib.parse import urlencode

city_slug = "cityofpaloalto"

with PrimeGovAdapter(city_slug) as adapter:
    api_url = f"{adapter.base_url}/api/v2/PublicPortal/ListUpcomingMeetings"
    response = adapter._get(api_url)
    meetings = response.json()

    print(f"Testing {len(meetings)} meetings for HTML agendas...\n")
    print("=" * 80)

    for i, m in enumerate(meetings, 1):
        print(f"\n[{i}] {m.get('title')}")

        # Find HTML Agenda document
        html_doc = next(
            (d for d in m.get('documentList', [])
             if 'HTML Agenda' in d.get('templateName', '')),
            None
        )

        if not html_doc:
            print("  No HTML Agenda document")
            continue

        # Build URL
        query = urlencode({
            'meetingTemplateId': html_doc['templateId'],
            'compileOutputType': html_doc['compileOutputType']
        })
        url = f"{adapter.base_url}/Public/CompiledDocument?{query}"

        print(f"  URL: {url}")

        # Try fetching
        try:
            resp = adapter._get(url, timeout=10)
            html = resp.text

            # Check if it's the "Document Not Found" page
            if 'Document Not Found' in html:
                print("  ❌ Document Not Found")
            else:
                print(f"  ✓ SUCCESS! ({len(html)} chars)")

                # Save it
                filename = f"/root/engagic/data/html_agenda_{html_doc['templateId']}.html"
                with open(filename, 'w') as f:
                    f.write(html)
                print(f"  Saved to: {filename}")

        except Exception as e:
            print(f"  ❌ Error: {e}")
