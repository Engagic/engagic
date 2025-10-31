#!/usr/bin/env python3
"""
Probe Granicus HTML Agenda Structure

Fetch and analyze Granicus AgendaViewer pages to understand structure for item-level parsing.
Goal: Map agenda items to their attachments (PDFs).

Usage:
    uv run scripts/probe_granicus_html.py [city_slug]

Example:
    uv run scripts/probe_granicus_html.py miamifl
"""

import sys
from bs4 import BeautifulSoup
from infocore.adapters.granicus_adapter import GranicusAdapter


def probe_granicus_html(city_slug: str):
    """Probe Granicus HTML agenda structure for a specific city"""

    print(f"Probing Granicus HTML agenda for: {city_slug}")
    print("=" * 80)

    with GranicusAdapter(city_slug) as adapter:
        # Fetch meetings
        meetings = list(adapter.fetch_meetings())

        print(f"Found {len(meetings)} meetings")

        if not meetings:
            print("No meetings found")
            return

        # Find a meeting with an AgendaViewer URL
        agenda_viewer_url = None

        for meeting in meetings[:10]:
            packet_url = meeting.get('packet_url', '')

            # Check if this meeting has an AgendaViewer page (not direct PDF)
            # We need to look at the original HTML to find AgendaViewer links
            print(f"\nMeeting: {meeting['title']}")
            print(f"  Start: {meeting['start']}")
            print(f"  Packet URL: {packet_url}")
            print(f"  Meeting ID: {meeting['meeting_id']}")

        print("\n" + "=" * 80)
        print("Fetching agenda list page to find AgendaViewer links...")
        print("=" * 80)

        # Fetch the main list page to find AgendaViewer links
        soup = adapter._fetch_html(adapter.list_url)

        # Find agenda links that point to AgendaViewer
        agenda_links = soup.find_all('a', href=True)
        agenda_viewer_links = [
            link for link in agenda_links
            if 'AgendaViewer.php' in link.get('href', '')
        ]

        print(f"\nFound {len(agenda_viewer_links)} AgendaViewer links")

        if not agenda_viewer_links:
            print("No AgendaViewer links found. This city may use direct PDF links only.")
            return

        # Take the first AgendaViewer link
        first_link = agenda_viewer_links[0]
        agenda_viewer_url = adapter.base_url + first_link['href'] if not first_link['href'].startswith('http') else first_link['href']

        print("\nAnalyzing first AgendaViewer URL:")
        print(f"  {agenda_viewer_url}")

        # Fetch and analyze the AgendaViewer page
        try:
            from urllib.parse import urljoin

            agenda_viewer_url = urljoin(adapter.base_url, first_link['href'])
            print(f"\nFetching AgendaViewer page: {agenda_viewer_url}")

            response = adapter._get(agenda_viewer_url)
            html_content = response.text

            print(f"HTML length: {len(html_content)} chars")

            # Parse structure
            soup = BeautifulSoup(html_content, 'html.parser')

            print("\n" + "=" * 80)
            print("HTML STRUCTURE ANALYSIS")
            print("=" * 80)

            # Look for agenda item containers
            selectors_to_try = [
                ('div', 'AgendaItem'),
                ('div', 'agendaItem'),
                ('div', 'agenda-item'),
                ('tr', 'AgendaRow'),
                ('tr', 'agendaRow'),
                ('section', None),
                ('article', None),
                ('h2', None),
                ('h3', None),
                ('h4', None),
            ]

            for tag, class_name in selectors_to_try:
                if class_name:
                    elements = soup.find_all(tag, class_=class_name)
                    if elements:
                        print(f"\n<{tag} class='{class_name}'>: {len(elements)} found")
                        if elements and len(elements) <= 20:
                            for i, elem in enumerate(elements[:3], 1):
                                text_preview = elem.get_text(strip=True)[:100]
                                print(f"  [{i}] {text_preview}...")
                else:
                    elements = soup.find_all(tag)
                    if elements and len(elements) < 50:
                        print(f"\n<{tag}>: {len(elements)} found")

            # Analyze links (potential attachments)
            print("\n" + "=" * 80)
            print("LINKS ANALYSIS")
            print("=" * 80)

            all_links = soup.find_all('a', href=True)
            print(f"Total links: {len(all_links)}")

            pdf_links = [link for link in all_links if '.pdf' in link['href'].lower()]
            print(f"PDF links: {len(pdf_links)}")

            metaviewer_links = [link for link in all_links if 'MetaViewer' in link['href']]
            print(f"MetaViewer links: {len(metaviewer_links)}")

            if pdf_links:
                print("\nFirst 5 PDF links:")
                for i, link in enumerate(pdf_links[:5], 1):
                    link_text = link.get_text(strip=True)
                    href = link['href']
                    print(f"  [{i}] '{link_text}' -> {href[:80]}")

            if metaviewer_links:
                print("\nFirst 5 MetaViewer links:")
                for i, link in enumerate(metaviewer_links[:5], 1):
                    link_text = link.get_text(strip=True)
                    href = link['href']
                    print(f"  [{i}] '{link_text}' -> {href[:80]}")

            # Look for table structures (common in Granicus)
            print("\n" + "=" * 80)
            print("TABLE STRUCTURE ANALYSIS")
            print("=" * 80)

            tables = soup.find_all('table')
            print(f"Total tables: {len(tables)}")

            for i, table in enumerate(tables[:3], 1):
                rows = table.find_all('tr')
                print(f"\nTable {i}: {len(rows)} rows")

                # Show first few rows
                for j, row in enumerate(rows[:3], 1):
                    cells = row.find_all(['td', 'th'])
                    cell_texts = [cell.get_text(strip=True)[:40] for cell in cells]
                    print(f"  Row {j}: {' | '.join(cell_texts)}")

            # Look for div structures with IDs
            print("\n" + "=" * 80)
            print("DIV STRUCTURES WITH IDs")
            print("=" * 80)

            divs_with_ids = soup.find_all('div', id=True)
            print(f"Total divs with IDs: {len(divs_with_ids)}")

            agenda_related_divs = [
                div for div in divs_with_ids
                if any(keyword in div.get('id', '').lower() for keyword in ['agenda', 'item', 'row'])
            ]

            if agenda_related_divs:
                print(f"\nAgenda-related divs: {len(agenda_related_divs)}")
                for div in agenda_related_divs[:5]:
                    div_id = div.get('id', '')
                    text_preview = div.get_text(strip=True)[:60]
                    print(f"  ID='{div_id}': {text_preview}...")

            # Save HTML for manual inspection
            output_file = f"/root/engagic/data/granicus_agenda_{city_slug}.html"
            with open(output_file, 'w') as f:
                f.write(html_content)
            print(f"\nFull HTML saved to: {output_file}")

            # Pretty print a sample section
            print("\n" + "=" * 80)
            print("SAMPLE HTML SNIPPET (first 2000 chars)")
            print("=" * 80)
            print(html_content[:2000])

        except Exception as e:
            print(f"\nError fetching AgendaViewer page: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        city_slug = sys.argv[1]
    else:
        # Default to Miami if no argument provided
        city_slug = "miamifl"

    probe_granicus_html(city_slug)
