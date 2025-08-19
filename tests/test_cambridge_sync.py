import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

#!/usr/bin/env python3
"""Test Cambridge sync to debug why meetings aren't being stored"""

import logging
from backend.adapters.all_adapters import GranicusAdapter
from backend.database import DatabaseManager
from backend.core.config import config

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize database
db = DatabaseManager(config.LOCATIONS_DB_PATH, config.MEETINGS_DB_PATH, config.ANALYTICS_DB_PATH)

# Get Cambridge meetings
adapter = GranicusAdapter("cambridgema")
meetings = list(adapter.all_meetings())

print(f"\nFound {len(meetings)} meetings:")
for i, meeting in enumerate(meetings):
    print(f"\n{i+1}. {meeting['title']}")
    print(f"   Date: {meeting['start']}")
    print(f"   ID: {meeting['meeting_id']}")
    print(f"   Packet: {meeting['packet_url']}")
    
    # Try to store it
    meeting_data = {
        "city_banana": "cambridgeMA",
        "meeting_name": meeting.get("title"),
        "packet_url": meeting.get("packet_url"),
        "meeting_date": meeting.get("start"),
        "meeting_id": meeting.get("meeting_id")
    }
    
    try:
        result = db.store_meeting_data(meeting_data)
        print(f"   Stored: {result}")
    except Exception as e:
        print(f"   ERROR storing: {e}")

# Check what's in the database
meetings_in_db = db.get_meetings_by_city("cambridgeMA")
print(f"\n\nMeetings in database: {len(meetings_in_db)}")