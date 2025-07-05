from adapters import CivicClerkAdapter
import requests
from datetime import datetime

burlintest = CivicClerkAdapter("montpeliervt")
current_date = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-3] + "Z"
params = {
    "$filter": f"startDateTime gt {current_date}",
    "$orderby": "startDateTime asc, eventName asc"
    }
response = requests.get("https://montpeliervt.api.civicclerk.com/v1/Events", params=params)
data = response.json()
print("Testing CivicClerk adapter for Burlington, VT...")
print(f"Raw API returned {len(data.get('value', []))} meetings")


if data.get('value'):
    first_meeting = data['value'][0]
    print(f"First meeting files: {len(first_meeting.get('publishedFiles', []))}")
    for i, file in enumerate(first_meeting.get('publishedFiles', [])):
        print(f"  File {i+1}: {file.keys()}")
        if 'Agenda Packet' in file:
            print(f"    Has Agenda Packet key: {file['Agenda Packet']}")

            print("\nNow testing adapter...")
            print("=" * 50)

burlintest = CivicClerkAdapter("montpeliervt")
meetings = list(burlintest.upcoming_packets())
print(f"Found {len(meetings)} meetings")
print(f"Found {len(meetings)} meetings")

for i, meeting in enumerate(meetings):
    print(f"Meeting {i+1}:")
    print(f"  ID: {meeting['meeting_id']}")
    print(f"  Title: {meeting['title']}")
