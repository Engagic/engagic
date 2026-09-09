"""Page links that include form-widget navigation.

PyMuPDF's page.get_links() returns Link annotations only. CivicPlus agenda
packets (Antioch CA) draw their "STAFF REPORT" buttons as AcroForm push
buttons whose /A action is a GoTo into the packet. Those buttons are the
agenda's item structure -- one per item, each pointing at that item's staff
report -- and every link-based rung was blind to them. This module is the
one place that sees both, so the profiler and the chunkers agree on what a
page links to.
"""

import re
from typing import Any, Dict, List, Optional

import fitz

_REF_RE = re.compile(r"^\s*(\d+)\s+0\s+R")
_DEST_FIRST_REF_RE = re.compile(r"\[\s*(\d+)\s+0\s+R")


def _page_index_by_xref(doc: fitz.Document) -> Dict[int, int]:
    return {doc.page_xref(index): index for index in range(doc.page_count)}


def _resolve_goto_target(doc: fitz.Document, widget_xref: int, page_by_xref: Dict[int, int]) -> Optional[int]:
    """0-indexed page a widget's GoTo action lands on, or None."""
    kind, value = doc.xref_get_key(widget_xref, "A")
    if kind == "xref":
        match = _REF_RE.match(value)
        if not match:
            return None
        action_xref = int(match.group(1))
        subtype = doc.xref_get_key(action_xref, "S")[1]
        dest = doc.xref_get_key(action_xref, "D")[1]
    elif kind == "dict":
        subtype_match = re.search(r"/S\s*/(\w+)", value)
        dest_match = re.search(r"/D\s*(\[.*?\])", value)
        subtype = f"/{subtype_match.group(1)}" if subtype_match else ""
        dest = dest_match.group(1) if dest_match else ""
    else:
        return None
    if subtype != "/GoTo" or not dest:
        return None
    ref = _DEST_FIRST_REF_RE.match(dest)
    if not ref:
        return None
    return page_by_xref.get(int(ref.group(1)))


def widget_goto_links(page: fitz.Page) -> List[Dict[str, Any]]:
    """Form buttons on this page that navigate within the document, as link dicts."""
    widgets = list(page.widgets())
    doc = page.parent
    if not widgets or doc is None:
        return []
    page_by_xref = _page_index_by_xref(doc)
    links: List[Dict[str, Any]] = []
    for widget in widgets:
        target = _resolve_goto_target(doc, widget.xref, page_by_xref)
        if target is None:
            continue
        links.append(
            {
                "kind": fitz.LINK_GOTO,
                "page": target,
                "from": fitz.Rect(widget.rect),
                "widget": True,
                "widget_label": widget.field_name or "",
            }
        )
    return links


def page_links(page: fitz.Page) -> List[Dict[str, Any]]:
    """page.get_links() plus widget GoTo buttons, same dict shape."""
    return list(page.get_links()) + widget_goto_links(page)
