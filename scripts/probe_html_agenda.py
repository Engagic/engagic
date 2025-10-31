#!/usr/bin/env python3
"""
Probe HTML Agenda Structure - Phase 1 POC

Fetch HTML agendas from vendors to understand their structure.
Goal: Identify how to extract items + attachments from HTML.

Usage:
    python scripts/probe_html_agenda.py
"""

from vendors.adapters.primegov_adapter import PrimeGovAdapter

def probe_primegov_html():
    """Probe PrimeGov HTML agenda structure for Palo Alto"""
    city_slug = "cityofpaloalto"

    print(f"Probing PrimeGov HTML agenda for: {city_slug}")
    print("=" * 60)

    with PrimeGovAdapter(city_slug) as adapter:
        # Fetch raw meetings from API (not processed by adapter)
        upcoming_api_url = f"{adapter.base_url}/api/v2/PublicPortal/ListUpcomingMeetings"
        response = adapter._get(upcoming_api_url)
        raw_meetings = response.json()

        print(f"Found {len(raw_meetings)} raw upcoming meetings")

        if not raw_meetings:
            print("No meetings found")
            return

        # Take first meeting with HTML Agenda document
        raw_meeting = None
        for m in raw_meetings[:10]:
            doc_list = m.get('documentList', [])
            html_agenda = next((d for d in doc_list if 'HTML Agenda' in d.get('templateName', '')), None)
            if html_agenda:
                raw_meeting = m
                print(f"Found meeting with HTML Agenda: {m.get('title')}")
                break

        if not raw_meeting:
            print("No meetings with documentList found")
            return

        print(f"\nMeeting: {raw_meeting.get('title')}")
        print(f"Date: {raw_meeting.get('dateTime')}")
        print(f"Meeting ID: {raw_meeting.get('id')}")

        # Print all available document types
        print(f"\nAvailable documents ({len(raw_meeting.get('documentList', []))}):")
        print("=" * 60)
        for doc in raw_meeting.get('documentList', []):
            print(f"  - {doc.get('templateName')}")
            print(f"    templateId: {doc.get('templateId')}")
            print(f"    compileOutputType: {doc.get('compileOutputType')}")
            print(f"    compileStatus: {doc.get('compileStatus')}")
            print()

        # Find HTML Agenda document
        html_doc = next(
            (d for d in raw_meeting.get('documentList', []) if 'HTML Agenda' in d.get('templateName', '')),
            None
        )

        if html_doc:
            # Build HTML URL from the HTML Agenda document
            from urllib.parse import urlencode
            query = urlencode({
                'meetingTemplateId': html_doc['templateId'],
                'compileOutputType': html_doc['compileOutputType']
            })
            html_url = f"{adapter.base_url}/Public/CompiledDocument?{query}"
            print(f"\nHTML agenda URL: {html_url}")

            if True:  # Always try to fetch

                # Fetch HTML
                try:
                    response = adapter._get(html_url)
                    html_content = response.text

                    print(f"\nHTML length: {len(html_content)} chars")
                    print("\nFirst 1000 chars of HTML:")
                    print("-" * 60)
                    print(html_content[:1000])
                    print("-" * 60)

                    # Parse with BeautifulSoup
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(html_content, 'html.parser')

                    # Look for common agenda item patterns
                    print("\nSearching for agenda item patterns...")

                    # Check for various possible selectors
                    selectors_to_try = [
                        ('div', 'agenda-item'),
                        ('div', 'item'),
                        ('section', None),
                        ('article', None),
                        ('tr', None),  # Table rows
                        ('h2', None),  # Headers
                        ('h3', None),
                    ]

                    for tag, class_name in selectors_to_try:
                        if class_name:
                            elements = soup.find_all(tag, class_=class_name)
                            print(f"  <{tag} class='{class_name}'>: {len(elements)} found")
                        else:
                            elements = soup.find_all(tag)
                            print(f"  <{tag}>: {len(elements)} found")

                    # Look for links (attachments)
                    links = soup.find_all('a', href=True)
                    pdf_links = [link for link in links if '.pdf' in link['href'].lower()]
                    print(f"\nTotal links: {len(links)}")
                    print(f"PDF links: {len(pdf_links)}")

                    if pdf_links:
                        print("\nFirst 3 PDF links:")
                        for link in pdf_links[:3]:
                            print(f"  {link.get_text(strip=True)} -> {link['href'][:80]}")

                    # Save full HTML for manual inspection
                    output_file = f"/root/engagic/data/html_agenda_{city_slug}.html"
                    with open(output_file, 'w') as f:
                        f.write(html_content)
                    print(f"\nFull HTML saved to: {output_file}")

                except Exception as e:
                    print(f"Error fetching HTML: {e}")
                    import traceback
                    traceback.print_exc()


if __name__ == "__main__":
    probe_primegov_html()
