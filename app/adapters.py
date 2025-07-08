import re
import requests
import logging
from urllib.parse import urlencode
from datetime import datetime

logger = logging.getLogger("engagic")


class PrimeGovAdapter:
    def __init__(self, city_slug: str):
        if not city_slug:
            raise ValueError("city_slug required, e.g. 'cityofpaloalto'")
        self.slug = city_slug
        self.base = f"https://{self.slug}.primegov.com"
        logger.info(f"Initialized PrimeGov adapter for {city_slug}")

    def _packet_url(self, doc):
        q = urlencode(
            {
                "meetingTemplateId": doc["templateId"],
                "compileOutputType": doc["compileOutputType"],
            }
        )
        return f"https://{self.slug}.primegov.com/Public/CompiledDocument?{q}"

    def upcoming_packets(self):
        try:
            logger.debug(f"Fetching upcoming meetings from PrimeGov for {self.slug}")
            resp = requests.get(
                f"{self.base}/api/v2/PublicPortal/ListUpcomingMeetings", timeout=10
            )
            resp.raise_for_status()
            meetings = resp.json()
            logger.info(f"Retrieved {len(meetings)} meetings from PrimeGov for {self.slug}")
        except Exception as e:
            logger.error(f"Failed to fetch PrimeGov meetings for {self.slug}: {e}")
            raise
            
        for mtg in meetings:
            pkt = next(
                (d for d in mtg["documentList"] if "Packet" in d["templateName"]), None
            )
            if not pkt:
                continue

            yield {
                "meeting_id": mtg["id"],
                "title": mtg.get("title", ""),
                "start": mtg.get("dateTime", ""),
                "packet_url": self._packet_url(pkt),
            }


class CivicClerkAdapter:
    def __init__(self, city_slug: str):
        if not city_slug:
            raise ValueError("city_slug required, e.g. 'montpelliervt'")
        self.slug = city_slug
        self.base = f"https://{self.slug}.api.civicclerk.com"
        logger.info(f"Initialized CivicClerk adapter for {city_slug}")

    def _packet_url(self, doc):
        return f"https://{self.slug}.api.civicclerk.com/v1/Meetings/GetMeetingFileStream(fileId={doc['fileId']},plainText=false)"

    def upcoming_packets(self):
        try:
            logger.debug(f"Fetching upcoming meetings from CivicClerk for {self.slug}")
            current_date = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-3] + "Z"
            params = {
                "$filter": f"startDateTime gt {current_date}",
                "$orderby": "startDateTime asc, eventName asc",
            }
            response = requests.get(f"{self.base}/v1/Events", params=params)
            response.raise_for_status()
            data = response.json()
            meetings = data.get("value", [])
            logger.info(f"Retrieved {len(meetings)} meetings from CivicClerk for {self.slug}")
        except Exception as e:
            logger.error(f"Failed to fetch CivicClerk meetings for {self.slug}: {e}")
            raise
            
        for mtg in meetings:
            pkt = next(
                (
                    d
                    for d in mtg.get("publishedFiles", [])
                    if d.get("type") == "Agenda Packet"
                ),
                None,
            )
            if not pkt:
                continue

            yield {
                "meeting_id": mtg["id"],
                "title": mtg.get("eventName", ""),
                "start": mtg.get("startDateTime", ""),
                "packet_url": self._packet_url(pkt),
            }

# TODO: Test
class LegistarAdapter:
    def __init__(self, city_slug: str):
        self.city_slug = city_slug
        self.base = f"https://{city_slug}.legistar.com"
        
    def upcoming_packets(self):
        # Get calendar HTML
        resp = requests.get(f"{self.base}/Calendar.aspx")
        
        # Parse that ugly ass table
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Find all meeting rows
        for row in soup.find_all('tr', class_=['rgRow', 'rgAltRow']):
            # Extract meeting ID and GUID from links
            detail_link = row.find('a', href=re.compile(r'MeetingDetail\.aspx'))
            if detail_link:
                params = dict(re.findall(r'(\w+)=([^&]+)', detail_link['href']))
                meeting_id = params.get('ID')
                guid = params.get('GUID')
                
                # Check if agenda packet exists
                packet_link = row.find('a', id=re.compile('hypAgendaPacket'))
                if packet_link and 'Not available' not in packet_link.text:
                    yield {
                        'meeting_id': meeting_id,
                        'title': row.find('a', id=re.compile('hypBody')).text,
                        'start': row.find('td', class_='rgSorted').text,
                        'packet_url': f"{self.base}/View.ashx?M=AP&ID={meeting_id}&GUID={guid}"
                    }