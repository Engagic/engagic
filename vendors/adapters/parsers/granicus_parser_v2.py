"""
Granicus HTML Parser v2 -- anchor-first extraction

Same philosophy as agenda_chunker_v2: find invariant anchors first (links),
discover item structure from DOM proximity. One unified parser replaces
six format-specific ones (AgendaOnline, AgendaViewer, GeneratedAgendaViewer,
S3 grid, Questys, legacy).

Algorithm (HTML equivalent of chunker v2's URL path):
1. Collect all anchor links (document links + item identifiers)
2. Pre-compute link ancestry for O(1) containment checks
3. For each link, walk up DOM to find its item-boundary element
   (the point where sibling elements also contain other items' links)
4. Find the item-level parent (common parent of all boundary elements)
5. Walk parent's children sequentially, building items:
   - Heading/table/numbered-text -> new item
   - Links without title -> continuation (attachments for previous item)
   - Section keyword text -> section boundary
   - Multiple title-bearing sub-elements -> container (recurse)

Dependencies: BeautifulSoup4
"""

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Set, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from config import get_logger
from vendors.utils.attachments import classify_attachment_type
from parsing.participation import parse_participation_info

logger = get_logger(__name__).bind(component="vendor")


# ---------------------------------------------------------------------------
# Link detection (content-based, not format-specific)
# ---------------------------------------------------------------------------

_DOCUMENT_URL_RE = re.compile(
    r'MetaViewer'
    r'|\.pdf(?:\?|$)'
    r'|\.docx?(?:\?|$)'
    r'|s3\.amazonaws\.com'
    r'|cloudfront\.net'
    r'|Documents\.htm'
    r'|DownloadFile'
    r'|/attachments/'
    r'|/uploads?/attachment'
    r'|/ViewFile/',
    re.IGNORECASE,
)

_ITEM_ID_RE = re.compile(r'loadAgendaItem', re.IGNORECASE)


@dataclass
class _AnchorLink:
    """A link found in the HTML with classification metadata."""
    element: Tag
    url: str
    text: str
    is_document: bool
    is_item_id: bool
    item_id: str = ""


def _collect_anchor_links(soup: BeautifulSoup, base_url: str) -> List[_AnchorLink]:
    """Find all links that serve as structural anchors.

    Document links (MetaViewer, PDFs, S3, etc.) and item identifier links
    (loadAgendaItem) are the invariants across all Granicus HTML formats.
    """
    links = []
    seen_urls = set()

    for a in soup.find_all('a'):
        href = a.get('href', '') or ''
        onclick = a.get('onclick', '') or ''
        text = a.get_text(strip=True)

        is_doc = bool(_DOCUMENT_URL_RE.search(href))
        is_item = bool(_ITEM_ID_RE.search(href) or _ITEM_ID_RE.search(onclick))

        if not is_doc and not is_item:
            continue

        full_url = href
        if href.startswith('//'):
            full_url = 'https:' + href
        elif href and not href.startswith(('http', 'javascript', '#')):
            full_url = urljoin(base_url, href) if base_url else href

        if is_doc and full_url in seen_urls:
            continue
        if is_doc:
            seen_urls.add(full_url)

        item_id = ""
        if is_item:
            match = re.search(r'loadAgendaItem\((\d+)', href + ' ' + onclick)
            if match:
                item_id = match.group(1)

        links.append(_AnchorLink(
            element=a, url=full_url, text=text,
            is_document=is_doc, is_item_id=is_item, item_id=item_id,
        ))

    return links


# ---------------------------------------------------------------------------
# DOM proximity: find item boundaries
# ---------------------------------------------------------------------------

def _build_link_ancestry(links: List[_AnchorLink]) -> Set[int]:
    """Pre-compute set of element IDs for all ancestors of link elements.

    Enables O(1) 'does this element contain any anchor link?' checks
    during boundary detection, instead of walking descendants.
    """
    ancestry = set()
    for link in links:
        current = link.element
        while current:
            ancestry.add(id(current))
            current = getattr(current, 'parent', None)
            if current and not hasattr(current, 'name'):
                break
    return ancestry


def _find_item_boundary(element: Tag, link_ancestry: Set[int]) -> Tag:
    """Walk up from a link element to its item-boundary container.

    The item boundary is the element at the DOM level where sibling
    elements also contain anchor links -- the divergence point.
    This is the HTML equivalent of chunker v2's spatial link clustering.

    Confidence: 7/10 -- works for all tested formats, may need
    tuning for deeply nested or unconventional layouts.
    """
    current = element
    while current.parent and hasattr(current.parent, 'name') and current.parent.name:
        parent = current.parent
        for sibling in parent.children:
            if sibling is current or not isinstance(sibling, Tag):
                continue
            if id(sibling) in link_ancestry:
                return current
        current = parent
    return current


def _lowest_common_ancestor(a: Tag, b: Tag) -> Optional[Tag]:
    """Find the lowest common ancestor of two DOM elements."""
    ancestors_a = set()
    current = a
    while current:
        ancestors_a.add(id(current))
        current = getattr(current, 'parent', None)

    current = b
    while current:
        if id(current) in ancestors_a:
            return current
        current = getattr(current, 'parent', None)
    return None


def _find_item_parent(
    links: List[_AnchorLink],
    link_ancestry: Set[int],
) -> Optional[Tag]:
    """Find the DOM element whose children represent agenda items.

    Uses boundary detection on all links, then finds the container
    that holds all boundary elements. When boundaries share a single
    parent, that parent is the item-level container. When boundaries
    have multiple parents (e.g. items split across section blockquotes),
    finds their lowest common ancestor so the walk can recurse into
    each section.
    """
    parent_map: Dict[int, Tag] = {}

    for link in links:
        boundary = _find_item_boundary(link.element, link_ancestry)
        if boundary.parent and hasattr(boundary.parent, 'name') and boundary.parent.name:
            pid = id(boundary.parent)
            parent_map[pid] = boundary.parent

    if not parent_map:
        return None

    unique_parents = list(parent_map.values())

    if len(unique_parents) == 1:
        return unique_parents[0]

    # Multiple parents: find their lowest common ancestor
    # so the walk can discover section containers and recurse
    lca = unique_parents[0]
    for p in unique_parents[1:]:
        lca = _lowest_common_ancestor(lca, p)
        if lca is None:
            break

    return lca


# ---------------------------------------------------------------------------
# Title and number extraction (generic, not format-specific)
# ---------------------------------------------------------------------------

_ITEM_NUM_RE = re.compile(
    r'^\s*'
    r'('
    r'\d{1,3}(?:\.\d{1,3}){0,3}'
    r'|[A-Z]\.\d{1,3}'
    r'|[A-Z]\.'
    r'|\d{1,3}\.'
    r'|\(\d{1,2}\)'
    r'|\([a-z]\)'
    r')'
    r'[\s\t.:]*'
)

_SECTION_KEYWORDS = frozenset({
    'CALL TO ORDER', 'PUBLIC COMMENTS', 'PUBLIC COMMENT',
    'CLOSED SESSION', 'ROLL CALL', 'PLEDGE OF ALLEGIANCE',
    'INVOCATION', 'CONSENT CALENDAR', 'CONSENT AGENDA',
    'PUBLIC HEARINGS', 'PUBLIC HEARING', 'PUBLIC PARTICIPATION',
    'DISCUSSION', 'ACTION ITEMS', 'NEW BUSINESS', 'OLD BUSINESS',
    'UNFINISHED BUSINESS', 'ANNOUNCEMENTS', 'ADJOURNMENT',
    'COUNCIL COMMENTS', 'BOARD COMMENTS', 'STAFF COMMUNICATIONS',
    'CORRESPONDENCE', 'REPORTS', 'REGULAR AGENDA', 'SPECIAL PRESENTATIONS',
    'RECESS', 'RECONVENE', 'APPROVAL OF MINUTES', 'BUSINESS',
    'RESOLUTIONS', 'ORDINANCES', 'AGREEMENTS', 'BUSINESS CALENDAR',
    'LEASES/CONTRACTS/LEGAL', 'OTHER BUSINESS', 'OPEN SESSION',
    'LAND ACKNOWLEDGEMENT', 'COMMISSIONER COMMENTS',
    'CONSENT FOR APPROVAL', 'DISCUSSION CALENDAR',
})

_PROCEDURAL = frozenset({
    'call to order', 'call meeting to order', 'call roll', 'roll call',
    'pledge of allegiance', 'flag salute', 'invocation',
    'adjournment', 'adjourn', 'recess', 'reconvene', 'other business',
    'interpreter services', 'council reports',
})

_MATTER_FILE_RE = re.compile(r'File\s+ID:\s*([A-Z]{0,3}\d{4}-\d{2,6})')


def _extract_item_number(text: str) -> Tuple[str, str]:
    """Extract item number prefix. Returns (number, remainder)."""
    text = text.strip()
    if '\t' in text:
        parts = text.split('\t', 1)
        m = _ITEM_NUM_RE.match(parts[0])
        if m:
            return m.group(1).rstrip('.'), parts[1].strip() or text
    m = _ITEM_NUM_RE.match(text)
    if m:
        return m.group(1).rstrip('.'), text[m.end():].strip()
    return "", text


def _is_section_header(text: str) -> bool:
    """Check if text matches a known section header pattern."""
    if not text:
        return False
    cleaned = text.strip().rstrip(':').strip()
    cleaned = re.sub(r'^\d+\.?\s*', '', cleaned)
    cleaned = re.sub(r'^[A-Z]\.\s*', '', cleaned)
    # Strip trailing qualifiers like "Estimated Time: 5 minutes"
    cleaned = re.sub(r'\s+Estimated\s+Time.*$', '', cleaned, flags=re.IGNORECASE)
    return cleaned.upper() in _SECTION_KEYWORDS


def _is_procedural(text: str) -> bool:
    if not text:
        return False
    return text.strip().lower().rstrip('.') in _PROCEDURAL


def _clean_section_name(text: str) -> str:
    cleaned = text.strip().rstrip(':').strip()
    cleaned = re.sub(r'^\d+\.?\s*', '', cleaned)
    cleaned = re.sub(r'^[A-Z]\.\s*', '', cleaned)
    cleaned = re.sub(r'\s*\(.*\)\s*$', '', cleaned)
    cleaned = re.sub(r'\s+Estimated\s+Time.*$', '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip().upper()


def _is_descendant_of(element: Tag, ancestor: Tag) -> bool:
    current = element.parent
    while current:
        if current is ancestor:
            return True
        current = getattr(current, 'parent', None)
    return False


def _extract_title_from_element(element: Tag) -> Tuple[str, str]:
    """Extract title and item number from a DOM element.

    Returns (title, number). Empty strings if no title found.

    Priority: headings > table cells > item-identifier links > numbered text.
    Document-link-only elements (blockquotes with MetaViewer) return empty,
    falling through to the continuation path.
    """
    # 1. Heading tags (h2-h6)
    for h in element.find_all(['h2', 'h3', 'h4', 'h5', 'h6'], recursive=True):
        text = h.get_text(strip=True)
        if text and len(text) > 2:
            number, title = _extract_item_number(text)
            if title:
                return title, number

    # 2. Table with numbered first cell
    table = element if element.name == 'table' else element.find('table', recursive=True)
    if table:
        row = table.find('tr')
        if row:
            cells = row.find_all('td')
            if len(cells) >= 2:
                num_text = cells[0].get_text(strip=True).rstrip('.')
                title_text = cells[1].get_text(strip=True)
                if num_text and len(num_text) <= 10 and (
                    num_text.replace('.', '').isdigit()
                    or re.match(r'^[A-Za-z]\.?\d*\.?$', num_text)
                ):
                    clean_title = title_text
                    if 'File ID:' in title_text:
                        clean_title = title_text.split('File ID:')[0].strip()
                    if clean_title:
                        return clean_title, num_text

    # 3. Item-identifier links (loadAgendaItem)
    for a in element.find_all('a', recursive=True):
        onclick = a.get('onclick', '') or ''
        href = a.get('href', '') or ''
        if _ITEM_ID_RE.search(onclick) or _ITEM_ID_RE.search(href):
            text = a.get_text(strip=True)
            if text and len(text) > 3:
                number, title = _extract_item_number(text)
                return title or text, number

    # 4. Numbered text prefix (paragraphs, divs)
    # Only if the element has structural content (links, bold), not bare text
    direct_text = element.get_text(strip=True)
    if direct_text and element.find(['a', 'b', 'strong', 'table']):
        number, title = _extract_item_number(direct_text)
        if number and title and len(title) > 5:
            return title, number

    return "", ""


# ---------------------------------------------------------------------------
# Attachment and metadata extraction
# ---------------------------------------------------------------------------

def _make_attachment(link: _AnchorLink, base_url: str) -> Dict[str, Any]:
    url = link.url
    name = link.text or 'Attachment'
    att_type = classify_attachment_type(url) if url else 'unknown'
    if url and url.lower().endswith('documents.htm'):
        att_type = 'html'
    att = {'name': name, 'url': url, 'type': att_type}
    meta_match = re.search(r'meta_id=(\d+)', url)
    if meta_match:
        att['meta_id'] = meta_match.group(1)
    return att


def _extract_vendor_item_id(links: List[_AnchorLink], number: str) -> str:
    for link in links:
        if link.is_item_id and link.item_id:
            return link.item_id
    return number


# ---------------------------------------------------------------------------
# Core: walk DOM and build items
# ---------------------------------------------------------------------------

def _walk_and_build_items(
    parent: Tag,
    links: List[_AnchorLink],
    link_ancestry: Set[int],
    base_url: str,
    depth: int = 0,
) -> List[Dict[str, Any]]:
    """Walk parent's children sequentially, building items from anchors and titles.

    This is the HTML equivalent of chunker v2's URL path:
    - Anchor links define items (like hyperlinks in PDF)
    - Walk between link groups to find headings
    - Each (heading + following link cluster) = one item
    - Links without preceding heading = continuation of previous item

    Handles nested section containers by recursing (depth-limited to 4).
    """
    if depth > 4:
        return []

    children = [c for c in parent.children
                 if isinstance(c, Tag) and c.get_text(strip=True)]

    if not children:
        return []

    # Map each anchor link to the direct child it lives under
    child_link_map: Dict[int, List[_AnchorLink]] = defaultdict(list)
    for link in links:
        for child in children:
            if link.element is child or _is_descendant_of(link.element, child):
                child_link_map[id(child)].append(link)
                break

    items: List[Dict[str, Any]] = []
    current_section = ""
    current_item: Optional[Dict[str, Any]] = None
    sequence = 0

    for child in children:
        child_links = child_link_map.get(id(child), [])
        title, number = _extract_title_from_element(child)
        text = child.get_text(strip=True)

        # Section header detection
        if _is_section_header(title or text):
            if current_item:
                items.append(current_item)
                current_item = None
            current_section = _clean_section_name(title or text)
            continue

        # Skip procedural items
        if title and _is_procedural(title):
            continue

        # Container check: does this element hold multiple sub-items?
        # Must run BEFORE single-item detection, because a container
        # element (section blockquote, malformed td) may itself have
        # a title from its first child table, but should be recursed
        # into rather than treated as one item.
        # Check children and grandchildren (depth 2) to handle cases
        # where items are inside a nested blockquote.
        if child_links:
            sub_title_count = 0
            for sub in child.children:
                if not isinstance(sub, Tag):
                    continue
                st, _ = _extract_title_from_element(sub)
                if st:
                    sub_title_count += 1
                for subsub in sub.children:
                    if isinstance(subsub, Tag):
                        sst, _ = _extract_title_from_element(subsub)
                        if sst:
                            sub_title_count += 1

            if sub_title_count >= 2:
                if current_item:
                    items.append(current_item)
                    current_item = None
                sub_items = _walk_and_build_items(
                    child, child_links, link_ancestry, base_url, depth + 1,
                )
                for si in sub_items:
                    # Only propagate parent section if sub-item has none
                    if current_section and not si.get('metadata', {}).get('section'):
                        si.setdefault('metadata', {})['section'] = current_section
                    sequence += 1
                    si['sequence'] = sequence
                items.extend(sub_items)
                continue

        # Single item: element has a title
        if title:
            if current_item:
                items.append(current_item)

            sequence += 1
            doc_links = [l for l in child_links if l.is_document]
            vendor_id = _extract_vendor_item_id(child_links, number) or str(sequence)
            attachments = [_make_attachment(l, base_url) for l in doc_links]

            current_item = {
                'vendor_item_id': vendor_id,
                'title': title,
                'sequence': sequence,
                'agenda_number': number,
                'attachments': attachments,
            }

            m = _MATTER_FILE_RE.search(text)
            if m:
                current_item['matter_file'] = m.group(1)

            if current_section:
                current_item.setdefault('metadata', {})['section'] = current_section

            rec_match = re.search(r'Recommendation:\s*(.+?)(?=\n|Contact|$)', text)
            if rec_match:
                current_item.setdefault('metadata', {})['recommendation'] = rec_match.group(1).strip()

            continue

        # Continuation: has links but no title -- attach to previous item
        if child_links and current_item:
            doc_links = [l for l in child_links if l.is_document]
            current_item['attachments'].extend(
                _make_attachment(l, base_url) for l in doc_links
            )
            continue

        # No title, no links -- skip

    if current_item:
        items.append(current_item)

    return items


# ---------------------------------------------------------------------------
# Council member extraction (reused from v1 logic, simplified)
# ---------------------------------------------------------------------------

def _extract_council_members(soup: BeautifulSoup) -> List[str]:
    """Extract council member names from header spans (blue-styled text)."""
    members = []
    seen = set()

    blue_spans = soup.find_all(
        'span', style=lambda x: x and '#0070c2' in x.lower() if x else False,
    )

    current_name = []
    role_keywords = [
        'mayor', 'vice mayor', 'council member', 'councilmember',
        'president', 'vice president',
    ]

    for span in blue_spans:
        text = span.get_text(strip=True)
        if not text or text == ',':
            continue

        is_role = any(kw in text.lower() for kw in role_keywords)

        if is_role:
            if current_name:
                full_name = ' '.join(current_name)
                if text.lower() not in full_name.lower():
                    full_name = f"{full_name}, {text}"
                if full_name not in seen:
                    members.append(full_name)
                    seen.add(full_name)
                current_name = []
        else:
            current_name.append(text)

    if current_name:
        full_name = ' '.join(current_name)
        if full_name not in seen:
            members.append(full_name)

    return members


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_granicus_html_v2(html: str, base_url: str = "") -> Dict[str, Any]:
    """Parse any Granicus HTML format using anchor-first extraction.

    Same output contract as v1 parsers: {participation: {...}, items: [...]}.

    Works across all known Granicus HTML formats without URL-based format
    dispatch: AgendaOnline, AgendaViewer, GeneratedAgendaViewer, S3 grid,
    Questys, and legacy formats.
    """
    soup = BeautifulSoup(html, 'html.parser')

    # Phase 1: Collect all anchor links
    anchor_links = _collect_anchor_links(soup, base_url)

    if not anchor_links:
        logger.debug("v2 no anchor links found", vendor="granicus")
        return {'participation': {}, 'items': []}

    # Phase 2: Pre-compute link ancestry + find item-level parent
    link_ancestry = _build_link_ancestry(anchor_links)
    item_parent = _find_item_parent(anchor_links, link_ancestry)

    if not item_parent:
        logger.debug("v2 no item parent found", vendor="granicus")
        return {'participation': {}, 'items': []}

    # Phase 3: Walk and build items
    items = _walk_and_build_items(
        item_parent, anchor_links, link_ancestry, base_url,
    )

    # Phase 4: Extract participation info
    page_text = soup.get_text(separator=' ', strip=True)
    participation_info = parse_participation_info(page_text)
    participation = participation_info.model_dump() if participation_info else {}
    members = _extract_council_members(soup)
    if members:
        participation['members'] = members

    logger.debug(
        "v2 parsed granicus html",
        vendor="granicus",
        item_count=len(items),
        anchor_count=len(anchor_links),
    )

    return {'participation': participation, 'items': items}


# ---------------------------------------------------------------------------
# CLI for testing and comparison
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python -m vendors.adapters.parsers.granicus_parser_v2 <html_file> [--json] [--compare]")
        sys.exit(1)

    html_path = sys.argv[1]
    as_json = "--json" in sys.argv
    compare = "--compare" in sys.argv

    with open(html_path, "r", errors="replace") as f:
        html = f.read()

    result = parse_granicus_html_v2(html)
    items = result.get("items", [])

    if compare:
        from vendors.adapters.parsers.granicus_parser import (
            parse_agendaonline_html,
            parse_agendaviewer_html,
            parse_generated_agendaviewer_html,
            parse_granicus_s3_html,
            parse_questys_html,
        )

        v1_results = {}
        parsers = [
            ("agendaonline", lambda h: parse_agendaonline_html(h, "")),
            ("agendaviewer", parse_agendaviewer_html),
            ("generated", parse_generated_agendaviewer_html),
            ("s3", parse_granicus_s3_html),
            ("questys", lambda h: parse_questys_html(h, "")),
        ]
        for name, parser in parsers:
            try:
                r = parser(html)
                v1_results[name] = len(r.get("items", []))
            except Exception:
                v1_results[name] = -1

        print(f"{'=' * 60}")
        print(f"  v2:              {len(items):3d} items")
        for name, count in v1_results.items():
            label = f"v1 {name}"
            print(f"  {label:17s} {count:3d} items")
        print(f"{'=' * 60}")
        print()

    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"{'=' * 60}")
        print(f"{len(items)} items found")
        print(f"{'=' * 60}")

        for item in items:
            section = (item.get("metadata") or {}).get("section", "")
            atts = len(item.get("attachments", []))
            num = item.get("agenda_number", "")
            title = item["title"][:65]
            print(f"  [{section:25s}] {num:6s} {title}")
            if atts:
                for att in item["attachments"]:
                    print(f"  {'':34s} -> {att['name'][:50]}")
            if item.get("matter_file"):
                print(f"  {'':34s} matter: {item['matter_file']}")
