"""Form-widget buttons with GoTo actions are agenda anchors, same as links."""

import fitz

from vendors.adapters.parsers import router
from vendors.adapters.parsers.pdf_links import page_links, widget_goto_links
from vendors.adapters.parsers.pdf_profile import profile_doc


def _packet_with_buttons(tmp_path, targets=(11, 19), pages=25):
    """Agenda on page 1 with one STAFF REPORT button per item, staff reports deeper in."""
    document = fitz.open()
    for _ in range(pages):
        document.new_page()
    agenda = document[0]
    y = 120
    for index, target in enumerate(targets, start=1):
        agenda.insert_text((72, y), f"{index}.", fontsize=11)
        agenda.insert_text((72, y + 14), f"APPROVAL OF ITEM NUMBER {index}", fontsize=11)
        agenda.insert_text((72, y + 28), "Recommended Action: approve.", fontsize=10)
        widget = fitz.Widget()
        widget.field_type = fitz.PDF_WIDGET_TYPE_BUTTON
        widget.field_name = "STAFF REPORT"
        widget.rect = fitz.Rect(400, y + 20, 520, y + 40)
        added = agenda.add_widget(widget)
        document.xref_set_key(
            added.xref, "A", f"<< /S /GoTo /D [{document.page_xref(target - 1)} 0 R /Fit] >>"
        )
        y += 90
    for target in targets:
        document[target - 1].insert_text((72, 100), f"Staff report starting page {target}", fontsize=11)
    path = tmp_path / "packet.pdf"
    path.write_bytes(document.tobytes())
    document.close()
    return str(path)


def test_widget_buttons_resolve_to_pages(tmp_path):
    path = _packet_with_buttons(tmp_path)
    document = fitz.open(path)
    links = widget_goto_links(document[0])
    assert [link["page"] for link in links] == [10, 18]
    assert all(link["kind"] == fitz.LINK_GOTO and link["widget"] for link in links)
    assert len(page_links(document[0])) == 2
    assert profile_doc(document).internal_links == 2
    document.close()


def test_pageref_rung_uses_buttons_as_item_anchors(tmp_path):
    path = _packet_with_buttons(tmp_path)
    result = router.chunk_pdf(path, ["v2:pageref"], None)
    assert result.winning_rung == "v2:pageref"
    assert [item["agenda_number"] for item in result.items] == ["1", "2"]
    assert result.items[0]["title"].startswith("APPROVAL OF ITEM NUMBER 1")
    assert result.items[0]["metadata"]["page_start"] == 11
    assert result.items[0]["metadata"]["page_end"] == 18
    assert result.items[1]["metadata"]["page_start"] == 19
    assert "Staff report starting page 11" in result.items[0]["body_text"]


def test_pages_without_widgets_are_unchanged(tmp_path):
    document = fitz.open()
    page = document.new_page()
    page.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(72, 72, 200, 90), "uri": "https://example.test/a.pdf"})
    path = tmp_path / "plain.pdf"
    path.write_bytes(document.tobytes())
    document.close()
    document = fitz.open(path)
    assert widget_goto_links(document[0]) == []
    assert [link["kind"] for link in page_links(document[0])] == [fitz.LINK_URI]
    document.close()
