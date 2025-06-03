import requests
from urllib.parse import urlencode
from datetime import datetime, timezone

class PrimeGovAdapter:
    def __init__(self, city_slug: str):
        if not city_slug:
            raise ValueError("city_slug required, e.g. 'cityofpaloalto'")
        self.slug = city_slug
        self.base   = f"https://{self.slug}.primegov.com"

    def _packet_url(self, doc):
        q = urlencode({
            "meetingTemplateId": doc["templateId"],
            "compileOutputType": doc["compileOutputType"],
        })
        return f"https://{self.slug}.primegov.com/Public/CompiledDocument?{q}"

    def upcoming_packets(self):
        resp = requests.get(f"{self.base}/api/v2/PublicPortal/ListUpcomingMeetings", timeout=10)
        resp.raise_for_status()
        for mtg in resp.json():
            pkt = next((d for d in mtg["documentList"]
                        if "Packet" in d["templateName"]), None)
            if not pkt:
                continue

            yield {
                "meeting_id": mtg["id"],
                "title":      mtg["title"],
                "start":      mtg["dateTime"],
                "packet_url": self._packet_url(pkt)
            }