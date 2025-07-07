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