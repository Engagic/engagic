"""CivicPlus sites that publish a document catalog instead of an agenda."""

from pathlib import Path

from vendors.adapters.parsers.civicplus_parser import (
    explode_document_catalog,
    parse_civicplus_html,
)

FIXTURE = Path(__file__).parent / "fixtures" / "civicplus_antioch_catalog.html"
BASE = "https://ca-antioch.civicplus.com"


def test_antioch_catalog_explodes_into_per_file_items():
    parsed = parse_civicplus_html(FIXTURE.read_text(), BASE)
    assert [i["title"] for i in parsed["items"]] == ["Agenda Packet", "Staff Reports"]

    catalog = explode_document_catalog(parsed["items"])
    assert catalog is not None
    assert catalog["packet_url"].endswith("/AgendaCenter/ViewFile/Item/658?fileID=5499")

    items = catalog["items"]
    assert len(items) == 15
    assert items[0]["agenda_number"] == "101"
    assert items[0]["title"] == "PROCLAMATIONS Suicide Prevention Month"
    assert items[0]["attachments"][0]["url"].endswith("fileID=5484")
    assert items[0]["vendor_item_id"] == "5484"
    consent = [i for i in items if i["agenda_number"] == "4F"][0]
    assert consent["title"] == "CONSENT CALENDAR APPROVAL OF COUNCIL WARRANTS"
    assert [i["sequence"] for i in items] == list(range(1, 16))
    # The packet is nowhere in the item list.
    assert not any("packet" in a["name"].lower() for i in items for a in i["attachments"])


def test_real_agenda_is_left_alone():
    items = [
        {"title": "Approve minutes", "attachments": [{"name": "minutes.pdf", "url": "u1"}]},
        {"title": "Agenda Packet", "attachments": [{"name": "packet.pdf", "url": "u2"}]},
    ]
    assert explode_document_catalog(items) is None


def test_catalog_without_numbered_files_is_left_alone():
    items = [
        {"title": "Agenda Packet", "attachments": [{"name": "090826-packet.pdf", "url": "u1"}]},
        {"title": "Staff Reports", "attachments": [{"name": "report.pdf", "url": "u2"}, {"name": "memo.pdf", "url": "u3"}]},
    ]
    assert explode_document_catalog(items) is None
