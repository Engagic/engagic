import requests
from urllib.parse import urlencode
from datetime import datetime


class PrimeGovAdapter:
    def __init__(self, city_slug: str):
        if not city_slug:
            raise ValueError("city_slug required, e.g. 'cityofpaloalto'")
        self.slug = city_slug
        self.base = f"https://{self.slug}.primegov.com"

    def _packet_url(self, doc):
        q = urlencode(
            {
                "meetingTemplateId": doc["templateId"],
                "compileOutputType": doc["compileOutputType"],
            }
        )
        return f"https://{self.slug}.primegov.com/Public/CompiledDocument?{q}"

    def upcoming_packets(self):
        resp = requests.get(
            f"{self.base}/api/v2/PublicPortal/ListUpcomingMeetings", timeout=10
        )
        resp.raise_for_status()
        for mtg in resp.json():
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

    def _packet_url(self, doc):
        return f"https://{self.slug}.api.civicclerk.com/v1/Meetings/GetMeetingFileStream(fileId={doc['fileId']},plainText=false)"
    
    def upcoming_packets(self):
        current_date = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-3] + "Z"
        params = {
            "$filter": f"startDateTime gt {current_date}",
            "$orderby": "startDateTime asc, eventName asc"
        }
        response = requests.get(
            f"{self.base}/v1/Events", params=params
        )
        response.raise_for_status()
        response = response.json()
        for mtg in response.get("value", []):
            pkt = next(
                (d for d in mtg.get("publishedFiles", []) if d.get("type") == "Agenda Packet"), None
            )
            if not pkt:
                continue

            yield {
                "meeting_id": mtg["id"],
                "title": mtg.get("eventName", ""),
                "start": mtg.get("startDateTime", ""),
                "packet_url": self._packet_url(pkt),
            }


