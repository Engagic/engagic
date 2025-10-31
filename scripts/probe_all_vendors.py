#!/usr/bin/env python3
"""Probe all vendors for HTML agenda capabilities"""

from vendors.adapters.civicclerk_adapter import CivicClerkAdapter
from vendors.adapters.granicus_adapter import GranicusAdapter
from vendors.adapters.novusagenda_adapter import NovusAgendaAdapter
from vendors.adapters.civicplus_adapter import CivicPlusAdapter
from bs4 import BeautifulSoup

def probe_civicclerk():
    """Test CivicClerk - Amarillo, TX"""
    print("\n" + "="*80)
    print("TESTING: CivicClerk (Amarillo, TX)")
    print("="*80)

    with CivicClerkAdapter("amarillotx") as adapter:
        meetings = list(adapter.fetch_meetings())

        if not meetings:
            print("No meetings found")
            return

        first = meetings[0]
        print(f"\nMeeting: {first['title']}")
        print(f"URL: {first.get('packet_url', 'NO URL')}")

        # Check if there's HTML in the packet_url or if we need another endpoint
        if 'packet_url' in first:
            try:
                response = adapter._get(first['packet_url'])
                content_type = response.headers.get('Content-Type', '')

                print(f"Content-Type: {content_type}")
                print(f"Length: {len(response.content)} bytes")

                if 'html' in content_type.lower():
                    soup = BeautifulSoup(response.text, 'html.parser')

                    # Look for agenda item patterns
                    patterns = [
                        ('div', 'agenda-item'),
                        ('div', 'item'),
                        ('tr', 'agenda-row'),
                        ('section', None)
                    ]

                    for tag, cls in patterns:
                        if cls:
                            elements = soup.find_all(tag, class_=cls)
                        else:
                            elements = soup.find_all(tag)

                        if elements and len(elements) < 50:
                            print(f"  Found {len(elements)} <{tag} class='{cls}'>")

            except Exception as e:
                print(f"Error fetching: {e}")

def probe_granicus():
    """Test Granicus - Acworth, GA"""
    print("\n" + "="*80)
    print("TESTING: Granicus (Acworth, GA)")
    print("="*80)

    with GranicusAdapter("acworth-ga") as adapter:
        meetings = list(adapter.fetch_meetings())

        if not meetings:
            print("No meetings found")
            return

        first = meetings[0]
        print(f"\nMeeting: {first['title']}")
        print(f"Meeting ID: {first.get('meeting_id')}")

        # Granicus meeting detail URL format
        meeting_id = first.get('meeting_id')
        if meeting_id:
            # Try the agenda viewer URL (from existing _extract_pdfs_from_agenda_viewer)
            detail_url = f"{adapter.base_url}/AgendaViewer.aspx?MeetingID={meeting_id}"
            print(f"Detail URL: {detail_url}")

            try:
                response = adapter._get(detail_url, timeout=10)
                html = response.text
                soup = BeautifulSoup(html, 'html.parser')

                print(f"HTML length: {len(html)} chars")

                # Look for agenda item patterns
                patterns = [
                    ('div', 'agenda-item'),
                    ('div', 'agendaItem'),
                    ('tr', 'AgendaRow'),
                    ('div', 'catAgendaRow')
                ]

                for tag, cls in patterns:
                    elements = soup.find_all(tag, class_=cls)
                    if elements:
                        print(f"  Found {len(elements)} <{tag} class='{cls}'>")

                # Save for inspection
                with open('/root/engagic/data/granicus_detail.html', 'w') as f:
                    f.write(html)
                print("  Saved to: /root/engagic/data/granicus_detail.html")

            except Exception as e:
                print(f"Error: {e}")

def probe_novusagenda():
    """Test NovusAgenda - Ankeny, IA"""
    print("\n" + "="*80)
    print("TESTING: NovusAgenda (Ankeny, IA)")
    print("="*80)

    with NovusAgendaAdapter("ankeny") as adapter:
        meetings = list(adapter.fetch_meetings())

        if not meetings:
            print("No meetings found")
            return

        first = meetings[0]
        print(f"\nMeeting: {first['title']}")
        print(f"URL: {first.get('packet_url', 'NO URL')}")

        # NovusAgenda might have HTML meeting pages
        meeting_id = first.get('meeting_id')
        if meeting_id:
            # Try meeting detail page
            detail_url = f"{adapter.base_url}/Meeting.aspx?Id={meeting_id}"
            print(f"Detail URL: {detail_url}")

            try:
                response = adapter._get(detail_url, timeout=10)
                html = response.text
                soup = BeautifulSoup(html, 'html.parser')

                print(f"HTML length: {len(html)} chars")

                # Look for agenda items
                patterns = [
                    ('div', 'AgendaItem'),
                    ('div', 'agenda-item'),
                    ('tr', None)
                ]

                for tag, cls in patterns:
                    if cls:
                        elements = soup.find_all(tag, class_=cls)
                    else:
                        elements = soup.find_all(tag)

                    if elements and len(elements) < 100:
                        print(f"  Found {len(elements)} <{tag} class='{cls}'>")

                with open('/root/engagic/data/novusagenda_detail.html', 'w') as f:
                    f.write(html)
                print("  Saved to: /root/engagic/data/novusagenda_detail.html")

            except Exception as e:
                print(f"Error: {e}")

def probe_civicplus():
    """Test CivicPlus - Adrian, MI"""
    print("\n" + "="*80)
    print("TESTING: CivicPlus (Adrian, MI)")
    print("="*80)

    with CivicPlusAdapter("mi-adrianlibrary") as adapter:
        meetings = list(adapter.fetch_meetings())

        if not meetings:
            print("No meetings found")
            return

        first = meetings[0]
        print(f"\nMeeting: {first['title']}")
        print(f"URL: {first.get('packet_url', 'NO URL')}")

        if 'packet_url' in first:
            try:
                response = adapter._get(first['packet_url'], timeout=10)
                content_type = response.headers.get('Content-Type', '')

                print(f"Content-Type: {content_type}")

                if 'html' in content_type.lower():
                    soup = BeautifulSoup(response.text, 'html.parser')
                    print(f"HTML length: {len(response.text)} chars")

                    patterns = [
                        ('div', 'agenda-item'),
                        ('div', 'agendaItem'),
                        ('tr', 'catAgendaRow')
                    ]

                    for tag, cls in patterns:
                        elements = soup.find_all(tag, class_=cls)
                        if elements:
                            print(f"  Found {len(elements)} <{tag} class='{cls}'>")

                    with open('/root/engagic/data/civicplus_detail.html', 'w') as f:
                        f.write(response.text)
                    print("  Saved to: /root/engagic/data/civicplus_detail.html")

            except Exception as e:
                print(f"Error: {e}")


if __name__ == "__main__":
    probe_civicclerk()
    probe_granicus()
    probe_novusagenda()
    probe_civicplus()

    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print("Check saved HTML files in data/ to analyze structure")
