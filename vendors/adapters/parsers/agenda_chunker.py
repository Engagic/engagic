"""
Generalized chunker for Granicus/Legistar/CivicPlus municipal agenda PDFs.
Extracts agenda items with their text content and attachment URLs.

Designed for structural variance across municipalities:
- Different numbering schemes (1., 1.1, A., I., etc.)
- Bold/caps/underlined headers in various fonts
- Attachment links (Legistar S3, Granicus, or municipal hosting)
- Section wrappers (Consent Calendar, Public Hearings, Discussion, etc.)

Dependencies: PyMuPDF (fitz)

Returns pipeline-compatible dicts matching AgendaItemSchema / AttachmentSchema.

Usage:
    from vendors.adapters.parsers.agenda_chunker import parse_agenda_pdf
    result = parse_agenda_pdf("path/to/agenda.pdf")
    items = result["items"]  # List[dict] ready for pipeline
"""

import fitz
import re
import json
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from config import get_logger

logger = get_logger(__name__).bind(component="vendor")


# ---------------------------------------------------------------------------
# Internal data structures (used during extraction, converted at output)
# ---------------------------------------------------------------------------

@dataclass
class _Attachment:
    label: str
    url: str
    page: int      # 0-indexed
    bbox: list

@dataclass
class _AgendaItem:
    number: str                             # "4.3", "6.1", "1", "A", etc.
    title: str
    section: str                            # Parent section: "CONSENT CALENDAR", etc.
    body: str                               # Full text content
    recommended_action: str
    attachments: list = field(default_factory=list)  # List[_Attachment]
    page_start: int = 0                     # 1-indexed
    page_end: int = 0

@dataclass
class _AgendaMetadata:
    title: str = ""
    body_name: str = ""                     # "City Council", "Planning Commission"
    meeting_date: str = ""
    meeting_type: str = ""                  # "Regular Meeting", "Special Meeting"
    page_count: int = 0

@dataclass
class _ParsedAgenda:
    metadata: _AgendaMetadata = field(default_factory=_AgendaMetadata)
    sections: list = field(default_factory=list)
    items: list = field(default_factory=list)        # List[_AgendaItem]
    orphan_links: list = field(default_factory=list)  # List[_Attachment]


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

ITEM_NUM_RE = re.compile(
    r'^[\s]*'
    r'('
    r'\d{1,2}(?:\.\d{1,2}){1,3}'   # 4.3, 6.1.2, 1.2.3.4
    r'|\d{1,2}\.'                    # 1. 2.
    r'|[A-Z]\.'                      # A. B. C.
    r'|[a-z]\.'                      # a. b. c.
    r'|[IVXLC]+\.'                   # I. II. IV.
    r')'
    r'\s*'
)

SECTION_PATTERNS = [
    r'CALL\s+TO\s+ORDER',
    r'PUBLIC\s+COMMENTS?',
    r'CLOSED\s+SESSION',
    r'ROLL\s+CALL',
    r'PLEDGE\s+OF\s+ALLEGIANCE',
    r'REPORT\s+FROM\s+CLOSED\s+SESSION',
    r'SPECIAL\s+PRESENTATIONS?',
    r'ADDITIONS?,?\s+DELETIONS?,?\s+(?:AND\s+)?REORDERING(?:\s+TO\s+THE\s+AGENDA)?',
    r'COMMUNITY\s+INPUT',
    r'PUBLIC\s+INPUT',
    r'CONSENT\s+(?:CALENDAR|AGENDA)',
    r'PUBLIC\s+HEARING[S]?',
    r'(?:REGULAR\s+)?DISCUSSION(?:\s+ITEMS?)?',
    r'(?:REGULAR\s+)?ACTION(?:\s+ITEMS?)?',
    r'(?:REGULAR\s+)?BUSINESS(?:\s+ITEMS?)?',
    r'NEW\s+BUSINESS',
    r'OLD\s+BUSINESS',
    r'UNFINISHED\s+BUSINESS',
    r'CITY\s+MANAGER.{0,5}S?\s+REPORT',
    r'CITY\s+ATTORNEY.{0,5}S?\s+REPORT',
    r'ANNOUNCEMENTS?',
    r'COUNCIL\s+COMMENTS?',
    r'COMMITTEE\s+UPDATES?',
    r'BOARD\s+(?:MEMBER\s+)?COMMENTS?',
    r'STAFF\s+COMMUNICATIONS?',
    r'CORRESPONDENCE',
    r'ADJOURNMENT',
    r'RECESS',
    r'RECONVENE',
    # CivicPlus / Planning Commission patterns
    r'THESE\s+ITEMS\s+(?:WILL\s+)?REQUIRE',
    r'CONSENT\s*[-–—]\s*ITEMS\s+FOR\s+\w+',
    r'APPROVAL\s+OF\s+MINUTES',
    r'RULES\s+FOR\s+CONDUCTING',
    r'REGULAR\s+AGENDA',
    r'COMMUNICATIONS?$',
    r'DIRECTOR.{0,5}S?\s+COMMENTS?',
    r'COMMISSIONERS?.{0,5}\s+COMMENTS?',
    r'ADJOURN$',
]

SECTION_RE = re.compile(
    r'^\s*(?:\d{1,2}\.?\s+)?(' + '|'.join(SECTION_PATTERNS) + r')[:\s]*$',
    re.IGNORECASE
)

REC_ACTION_RE = re.compile(r'Recommended\s+Action\s*:', re.IGNORECASE)

ATTACHMENT_URL_PATTERNS = [
    r'legistarweb.*\.s3\.amazonaws\.com',
    r'granicus.*\.s3\.amazonaws\.com',
    r'granicus_production',
    r'hdlegisuite\.',
    r'civicplus\.',
    r'\.pdf$',
    r'\.docx?$',
    r'\.xlsx?$',
    r'/uploads?/attachment',
    r'/attachments/',
    r'/ViewFile/',
    r'/LinkClick\.aspx',
]
ATTACHMENT_URL_RE = re.compile('|'.join(ATTACHMENT_URL_PATTERNS), re.IGNORECASE)

# Matter file patterns: "2024-001", "BL2025-1005", "RS2024-12"
MATTER_FILE_RE = re.compile(
    r'(?:File\s+(?:ID|No\.?|Number|#)\s*:?\s*)'
    r'([A-Z]{0,3}\d{4}-\d{2,6})'
)

MATTER_FILE_STANDALONE_RE = re.compile(
    r'\b([A-Z]{1,3}\d{4}-\d{2,6})\b'
    r'|\bFile\s+ID:\s*(\S+)'
)


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

def _extract_page_text_with_positions(page):
    """Extract text as line-level entries with font metadata."""
    lines = []
    td = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
    for block in td.get("blocks", []):
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            spans = line.get("spans", [])
            if not spans:
                continue
            full_text = "".join(s["text"] for s in spans).strip()
            if not full_text:
                continue
            dominant = max(spans, key=lambda s: len(s["text"]))
            is_bold = bool(dominant["flags"] & 16)
            lines.append({
                "text": full_text,
                "bbox": list(line["bbox"]),
                "y0": line["bbox"][1],
                "y1": line["bbox"][3],
                "x0": line["bbox"][0],
                "is_bold": is_bold,
                "font_size": dominant["size"],
                "font_name": dominant["font"],
                "page": page.number,
            })
    lines.sort(key=lambda l: (l["y0"], l["x0"]))
    return lines


def _extract_links(page):
    """Extract all URI links from a page."""
    links = []
    for link in page.get_links():
        if link.get("kind") != 2:
            continue
        uri = link.get("uri", "")
        if not uri:
            continue
        bbox = link.get("from", fitz.Rect())
        display_text = _get_link_display_text(page, fitz.Rect(bbox))
        links.append({
            "url": uri,
            "label": display_text,
            "bbox": [bbox.x0, bbox.y0, bbox.x1, bbox.y1],
            "y_center": (bbox.y0 + bbox.y1) / 2,
            "page": page.number,
        })
    return links


def _get_link_display_text(page, link_rect):
    """Extract display text for a link by intersecting span bboxes."""
    td = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
    parts = []
    for block in td.get("blocks", []):
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                span_rect = fitz.Rect(span["bbox"])
                intersection = span_rect & link_rect
                if intersection.is_empty or intersection.width < 1:
                    continue
                span_y_center = (span_rect.y0 + span_rect.y1) / 2
                if link_rect.y0 <= span_y_center <= link_rect.y1:
                    text = span["text"].strip()
                    if text:
                        parts.append(text)
    return " ".join(parts) if parts else ""


def _is_section_header(text):
    return bool(SECTION_RE.match(text.strip()))


def _is_mostly_upper(text):
    alpha = [c for c in text if c.isalpha()]
    if not alpha:
        return True
    return sum(1 for c in alpha if c.isupper()) / len(alpha) > 0.7


def _extract_section_name(text):
    text = text.strip()
    text = re.sub(r'^\d+\.?\s*', '', text)
    text = re.sub(r'[:\s]+$', '', text)
    return text.upper()


def _match_item_number(text):
    m = ITEM_NUM_RE.match(text)
    if m:
        num = m.group(1).rstrip('.')
        remainder = text[m.end():].strip()
        return num, remainder
    return None, text


# Case/docket number patterns common in planning/zoning agendas
CASE_NUM_RE = re.compile(
    r'(?:Case|CUP|CS|TA|ZA|SUP|VAR|CPA|GPA|SP|DR|PM|TTM|TPM|ZC|PP|CDP|EIR)'
    r'[\s\-]*\d',
    re.IGNORECASE
)

# Consent-prefix patterns (CivicPlus style)
CONSENT_PREFIX_RE = re.compile(
    r'^CONSENT\s+(?:FOR\s+)?(?:APPROVAL|DEFERRAL|WITHDRAWAL|DENIAL)',
    re.IGNORECASE
)


def _is_likely_item_header(line, lines_context=None):
    """
    Heuristic: a line is an item header if it has an item number AND
    the remainder looks like an agenda item title (not procedural text).

    Also handles standalone number lines (e.g. "2.") where the title
    is on the following line(s), via lines_context.

    Returns (is_item, number, title_text, lines_consumed).
    lines_consumed = number of lines after this one used for the title.
    """
    num, remainder = _match_item_number(line["text"])
    if num is None:
        return False, None, None, 0

    # Sub-items (4.1, 6.1) are almost always agenda items
    if '.' in num:
        return True, num, remainder, 0

    # --- Remainder is present (number + text on same line) ---
    if remainder:
        alpha_chars = [c for c in remainder if c.isalpha()]
        if not alpha_chars:
            return False, None, None, 0

        # Strong signal: case/docket number in the text
        if CASE_NUM_RE.search(remainder):
            return True, num, remainder, 0

        # Strong signal: consent prefix
        if CONSENT_PREFIX_RE.match(remainder):
            return True, num, remainder, 0

        # Uppercase/bold heuristic for Granicus-style
        upper_ratio = sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars)
        if upper_ratio > 0.7 or line["is_bold"]:
            return True, num, remainder, 0

        # If it starts with a lowercase word and reads like a sentence,
        # it's probably procedural text (rules, instructions), not an item.
        if remainder[0].islower() or len(remainder) > 100:
            return False, None, None, 0

        return False, None, None, 0

    # --- Standalone number line (just "2.") ---
    # Look ahead in context for the title on the next line(s).
    if lines_context is not None:
        line_idx, all_lines, current_section = lines_context
        # Only treat as item if we're inside a recognized agenda section
        agenda_sections = {
            'CONSENT AGENDA', 'CONSENT CALENDAR', 'REGULAR AGENDA',
            'PUBLIC HEARINGS', 'DISCUSSION', 'ACTION', 'NEW BUSINESS',
            'OLD BUSINESS', 'UNFINISHED BUSINESS', 'SPECIAL PRESENTATIONS',
            'THESE ITEMS WILL REQUIRE APPROVAL BY COUNCIL',
            'THESE ITEMS REQUIRE ONLY PLANNING COMMISSION APPROVAL',
            'APPROVAL OF MINUTES',
        }
        in_agenda_section = any(
            s in (current_section or '').upper() for s in agenda_sections
        ) or (current_section or '').upper() in agenda_sections

        if not in_agenda_section:
            return False, None, None, 0

        # Grab title from next line(s)
        title_parts = []
        consumed = 0
        for j in range(line_idx + 1, min(line_idx + 5, len(all_lines))):
            next_text = all_lines[j]["text"].strip()
            if not next_text:
                consumed += 1
                continue
            # Stop if we hit another standalone number
            next_num, next_rem = _match_item_number(next_text)
            if next_num is not None and not next_rem:
                break
            # Stop if we hit a section header
            if _is_section_header(next_text) and (all_lines[j]["is_bold"] or _is_mostly_upper(next_text)):
                break
            title_parts.append(next_text)
            consumed = j - line_idx
            # If it has a case number or consent prefix, one line is enough
            if CASE_NUM_RE.search(next_text) or CONSENT_PREFIX_RE.match(next_text):
                break
            if len(title_parts) >= 2:
                break

        if title_parts:
            return True, num, " ".join(title_parts), consumed

    return False, None, None, 0


def _is_attachment_url(url):
    if not url:
        return False
    if ATTACHMENT_URL_RE.search(url):
        return True
    if re.search(r'\.(pdf|docx?|xlsx?|pptx?|csv|txt)(\?.*)?$', url, re.IGNORECASE):
        return True
    return False


def _looks_like_attachment_label(text, all_links, page, y0):
    for link in all_links:
        if link["page"] == page and abs(link["y_center"] - y0) < 15:
            return True
    return False


def _attachment_type(url: str) -> str:
    """Classify attachment type from URL for AttachmentSchema."""
    url_lower = url.lower()
    if '.pdf' in url_lower:
        return 'pdf'
    if any(ext in url_lower for ext in ['.doc', '.docx']):
        return 'doc'
    if any(ext in url_lower for ext in ['.xls', '.xlsx']):
        return 'spreadsheet'
    return 'unknown'


def _extract_matter_file(title: str, body: str) -> Optional[str]:
    """Try to extract a matter file number from title or body text."""
    for text in [title, body[:500] if body else ""]:
        m = MATTER_FILE_RE.search(text)
        if m:
            return m.group(1)
    # Fallback: look for standalone patterns like "BL2025-1005"
    m = MATTER_FILE_STANDALONE_RE.search(title)
    if m:
        return m.group(1) or m.group(2)
    return None


# ---------------------------------------------------------------------------
# Metadata extraction
# ---------------------------------------------------------------------------

def _extract_meeting_metadata(lines, meta):
    """Extract meeting metadata from the first ~30 lines."""
    first_lines = [l["text"] for l in lines[:30]]
    joined = "\n".join(first_lines)

    body_patterns = [
        r'(CITY\s+COUNCIL)',
        r'(PLANNING\s+COMMISSION)',
        r'(BOARD\s+OF\s+SUPERVISORS)',
        r'(TOWN\s+COUNCIL)',
        r'(VILLAGE\s+BOARD)',
        r'(BOARD\s+OF\s+(?:DIRECTORS|TRUSTEES))',
    ]
    for pat in body_patterns:
        m = re.search(pat, joined, re.IGNORECASE)
        if m:
            meta.body_name = m.group(1).title()
            break

    type_patterns = [
        (r'REGULAR\s+MEETING', "Regular Meeting"),
        (r'SPECIAL\s+MEETING', "Special Meeting"),
        (r'ADJOURNED\s+(?:REGULAR\s+)?MEETING', "Adjourned Meeting"),
        (r'EMERGENCY\s+MEETING', "Emergency Meeting"),
        (r'STUDY\s+SESSION', "Study Session"),
        (r'WORKSHOP', "Workshop"),
    ]
    for pat, label in type_patterns:
        if re.search(pat, joined, re.IGNORECASE):
            meta.meeting_type = label
            break

    date_patterns = [
        r'(\w+day,?\s+\w+\s+\d{1,2},?\s+\d{4})',
        r'(\w+\s+\d{1,2},?\s+\d{4})',
        r'(\d{1,2}/\d{1,2}/\d{4})',
    ]
    for pat in date_patterns:
        m = re.search(pat, joined, re.IGNORECASE)
        if m:
            meta.meeting_date = m.group(1).strip()
            break

    for l in lines[:10]:
        if l["is_bold"] and l["font_size"] >= 14:
            meta.title = l["text"].strip()
            break
    if not meta.title:
        meta.title = "Agenda"


def _infer_section(item_number):
    return "GENERAL"


# ---------------------------------------------------------------------------
# Link-to-item assignment
# ---------------------------------------------------------------------------

def _find_owning_item(link, item_boundaries, all_lines):
    """Assign a link to the nearest preceding item on the same or earlier page."""
    link_page = link["page"]
    link_y = link["y_center"]

    best = None
    for bi in range(len(item_boundaries)):
        bp = item_boundaries[bi]["page"]
        by = item_boundaries[bi]["y0"]

        if bp < link_page:
            best = bi
        elif bp == link_page and by <= link_y:
            best = bi

    if best is not None and best + 1 < len(item_boundaries):
        next_bp = item_boundaries[best + 1]["page"]
        next_by = item_boundaries[best + 1]["y0"]
        if link_page > next_bp or (link_page == next_bp and link_y >= next_by):
            return _find_owning_item_strict(link, item_boundaries)
    return best


def _find_owning_item_strict(link, item_boundaries):
    """Fallback: find which item range the link falls within."""
    link_page = link["page"]
    link_y = link["y_center"]

    for bi in range(len(item_boundaries)):
        bp = item_boundaries[bi]["page"]
        by = item_boundaries[bi]["y0"]

        if bi + 1 < len(item_boundaries):
            ep = item_boundaries[bi + 1]["page"]
            ey = item_boundaries[bi + 1]["y0"]
        else:
            ep = link_page + 1
            ey = 9999

        after_start = (link_page > bp) or (link_page == bp and link_y >= by)
        before_end = (link_page < ep) or (link_page == ep and link_y < ey)

        if after_start and before_end:
            return bi
    return None


# ---------------------------------------------------------------------------
# Main parser (internal)
# ---------------------------------------------------------------------------

def _parse_agenda_internal(pdf_path: str) -> _ParsedAgenda:
    """Parse a PDF into internal dataclass representation."""
    doc = fitz.open(pdf_path)
    result = _ParsedAgenda()

    result.metadata.page_count = doc.page_count

    # Collect all lines and links across pages
    all_lines = []
    all_links = []

    for page in doc:
        all_lines.extend(_extract_page_text_with_positions(page))
        all_links.extend(_extract_links(page))

    # Pass 1: Metadata from first page
    _extract_meeting_metadata(all_lines, result.metadata)

    # Pass 2: Identify sections and items
    current_section = ""
    items = []
    item_boundaries = []
    skip_until = -1  # Skip lines already consumed as titles

    for i, line in enumerate(all_lines):
        if i <= skip_until:
            continue

        text = line["text"]

        if _is_section_header(text) and (line["is_bold"] or _is_mostly_upper(text)):
            section_name = _extract_section_name(text)
            current_section = section_name
            if section_name not in result.sections:
                result.sections.append(section_name)
            continue

        is_item, num, title_text, lines_consumed = _is_likely_item_header(
            line, lines_context=(i, all_lines, current_section)
        )
        if is_item and num and title_text:
            full_title = title_text
            title_end_index = i + lines_consumed

            # For inline number+title (lines_consumed==0), try multi-line extension
            if lines_consumed == 0:
                for j in range(i + 1, min(i + 4, len(all_lines))):
                    next_line = all_lines[j]
                    nt = next_line["text"].strip()
                    if _match_item_number(nt)[0] is not None:
                        break
                    if _is_section_header(nt) and next_line["is_bold"]:
                        break
                    if REC_ACTION_RE.search(nt):
                        break
                    if _looks_like_attachment_label(nt, all_links, next_line["page"], next_line["y0"]):
                        break
                    if (next_line["is_bold"] == line["is_bold"]
                        and abs(next_line["font_size"] - line["font_size"]) < 0.5
                        and _is_mostly_upper(nt)):
                        full_title += " " + nt
                        title_end_index = j
                    else:
                        break

            skip_until = title_end_index

            section = current_section or _infer_section(num)
            item = _AgendaItem(
                number=num,
                title=full_title.rstrip(':').strip(),
                section=section,
                body="",
                recommended_action="",
                page_start=line["page"] + 1,
            )
            items.append(item)
            item_boundaries.append({
                "index": len(items) - 1,
                "page": line["page"],
                "y0": line["y0"],
                "line_index": title_end_index,
            })

    # Pass 3: Collect body text for each item
    for bi in range(len(item_boundaries)):
        start_li = item_boundaries[bi]["line_index"] + 1
        if bi + 1 < len(item_boundaries):
            end_li = item_boundaries[bi + 1]["line_index"]
        else:
            end_li = len(all_lines)

        body_parts = []
        rec_action_parts = []
        in_rec_action = False

        for li in range(start_li, end_li):
            lt = all_lines[li]["text"]

            if _is_section_header(lt):
                break

            if REC_ACTION_RE.search(lt):
                in_rec_action = True
                after = REC_ACTION_RE.split(lt, 1)[-1].strip()
                if after:
                    rec_action_parts.append(after)
                body_parts.append(lt)
                continue

            if in_rec_action:
                if _looks_like_attachment_label(lt, all_links, all_lines[li]["page"], all_lines[li]["y0"]):
                    in_rec_action = False
                else:
                    rec_action_parts.append(lt)

            body_parts.append(lt)
            items[bi].page_end = all_lines[li]["page"] + 1

        items[bi].body = "\n".join(body_parts).strip()
        items[bi].recommended_action = " ".join(rec_action_parts).strip()
        if not items[bi].page_end:
            items[bi].page_end = items[bi].page_start

    # Pass 4: Assign links to items by position
    assigned_links = set()

    for link in all_links:
        if not _is_attachment_url(link["url"]):
            continue

        best_item = _find_owning_item(link, item_boundaries, all_lines)
        if best_item is not None:
            items[best_item].attachments.append(_Attachment(
                label=link["label"],
                url=link["url"],
                page=link["page"],
                bbox=link["bbox"],
            ))
            assigned_links.add(id(link))
        else:
            result.orphan_links.append(_Attachment(
                label=link["label"],
                url=link["url"],
                page=link["page"],
                bbox=link["bbox"],
            ))

    result.items = items
    doc.close()
    return result


# ---------------------------------------------------------------------------
# Public API - returns pipeline-compatible dicts
# ---------------------------------------------------------------------------

def parse_agenda_pdf(pdf_path: str) -> Dict[str, Any]:
    """
    Parse a Granicus/Legistar agenda PDF into pipeline-compatible item dicts.

    Returns dict matching the format expected by the adapter/orchestrator:
    {
        "items": [
            {
                "vendor_item_id": "4.3",
                "title": "...",
                "sequence": 1,
                "agenda_number": "4.3",
                "body_text": "...",
                "attachments": [{"name": "...", "url": "...", "type": "pdf"}],
                "matter_file": "2024-001" or None,
                "metadata": {"section": "CONSENT CALENDAR", ...},
            },
            ...
        ],
        "metadata": {"body_name": "...", "meeting_date": "...", ...},
    }
    """
    parsed = _parse_agenda_internal(pdf_path)

    pipeline_items: List[Dict[str, Any]] = []
    for idx, item in enumerate(parsed.items):
        pipeline_item: Dict[str, Any] = {
            "vendor_item_id": item.number,
            "title": item.title,
            "sequence": idx + 1,
            "agenda_number": item.number,
            "attachments": [
                {
                    "name": att.label or "Attachment",
                    "url": att.url,
                    "type": _attachment_type(att.url),
                }
                for att in item.attachments
            ],
        }

        if item.body:
            pipeline_item["body_text"] = item.body

        matter_file = _extract_matter_file(item.title, item.body)
        if matter_file:
            pipeline_item["matter_file"] = matter_file

        item_metadata: Dict[str, Any] = {}
        if item.section:
            item_metadata["section"] = item.section
        if item.recommended_action:
            item_metadata["recommended_action"] = item.recommended_action
        if item.page_start:
            item_metadata["page_start"] = item.page_start
            item_metadata["page_end"] = item.page_end
        if item_metadata:
            pipeline_item["metadata"] = item_metadata

        pipeline_items.append(pipeline_item)

    result = {
        "items": pipeline_items,
        "metadata": {
            "body_name": parsed.metadata.body_name,
            "meeting_date": parsed.metadata.meeting_date,
            "meeting_type": parsed.metadata.meeting_type,
            "page_count": parsed.metadata.page_count,
        },
    }

    if parsed.orphan_links:
        result["orphan_links"] = [
            {"name": att.label, "url": att.url, "type": _attachment_type(att.url)}
            for att in parsed.orphan_links
        ]

    logger.debug(
        "parsed agenda pdf",
        item_count=len(pipeline_items),
        section_count=len(parsed.sections),
        orphan_links=len(parsed.orphan_links),
        page_count=parsed.metadata.page_count,
    )

    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m vendors.adapters.parsers.agenda_chunker <path_to_pdf> [--json] [--items-only]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    as_json = "--json" in sys.argv
    items_only = "--items-only" in sys.argv

    result = parse_agenda_pdf(pdf_path)
    items = result["items"]
    meta = result["metadata"]

    if as_json:
        if items_only:
            print(json.dumps(items, indent=2, ensure_ascii=False))
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"{'=' * 60}")
        print(f"{meta.get('body_name', '')} | {meta.get('meeting_type', '')} | {meta.get('meeting_date', '')}")
        print(f"{meta.get('page_count', 0)} pages | {len(items)} items")
        print(f"{'=' * 60}")

        for item in items:
            print(f"\n{'─' * 60}")
            section = (item.get("metadata") or {}).get("section", "")
            print(f"[{section}] {item.get('agenda_number', '')}  {item['title']}")
            if item.get("matter_file"):
                print(f"  Matter: {item['matter_file']}")
            rec = (item.get("metadata") or {}).get("recommended_action", "")
            if rec:
                preview = rec[:120] + ("..." if len(rec) > 120 else "")
                print(f"  Rec. Action: {preview}")
            atts = item.get("attachments", [])
            if atts:
                print(f"  Attachments ({len(atts)}):")
                for att in atts:
                    print(f"    - {att['name']}")
                    print(f"      {att['url']}")
            else:
                print(f"  Attachments: none")

        orphans = result.get("orphan_links", [])
        if orphans:
            print(f"\n{'─' * 60}")
            print(f"ORPHAN LINKS ({len(orphans)}):")
            for att in orphans:
                print(f"  {att['name']} -> {att['url']}")
