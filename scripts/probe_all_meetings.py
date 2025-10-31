#!/usr/bin/env python3
"""Probe all Palo Alto meetings - see what's actually available"""

from vendors.adapters.primegov_adapter import PrimeGovAdapter

city_slug = "cityofpaloalto"

with PrimeGovAdapter(city_slug) as adapter:
    api_url = f"{adapter.base_url}/api/v2/PublicPortal/ListUpcomingMeetings"
    response = adapter._get(api_url)
    meetings = response.json()

    print(f"Total meetings: {len(meetings)}\n")
    print("=" * 80)

    for i, m in enumerate(meetings, 1):
        print(f"\n[{i}] {m.get('title')}")
        print(f"Date: {m.get('dateTime')}")
        print(f"ID: {m.get('id')}")

        doc_list = m.get('documentList', [])
        print(f"Documents ({len(doc_list)}):")

        for doc in doc_list:
            print(f"  - {doc.get('templateName')}")
            print(f"    ID: {doc.get('templateId')}")
            print(f"    Type: {doc.get('compileOutputType')}")
            print(f"    Status: {doc.get('compileStatus')}")

        print("-" * 80)
