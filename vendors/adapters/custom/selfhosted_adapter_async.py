"""
Self-hosted public bodies: agencies that publish meetings on their own site.

State boards, regional regulators, pension funds, grid operators and transit
authorities mostly sit off the vendor circuit. Their sites are hand-edited,
but they reduce to one model: a meeting is a dated group of document links.
Two page shapes cover every site onboarded so far:

  index    One page (optionally one per year) lists meetings, each row a date
           plus its agenda/minutes/report documents.
  detail   The index links to one page per meeting (``meeting_href`` regex);
           that page lists the item documents.

Pages parse with lxml: hand-edited HTML leaves <p> unclosed, and html.parser
then nests every later block inside the first paragraph.

Nothing is located by site-specific selector. A listing row is the smallest
ancestor of a document link whose text holds exactly one date, which finds
list items, table rows and multi-column grids alike. Items on a detail page
are keyed anchor-first: the item number a document carries in its own label
or URL ("Item 03", "5.1 ...", item04c, /item4/), falling back to the heading
the link sits under. A row's "Agenda Items"/"Supporting Materials" page is
followed the same way. Agenda PDFs without item documents go through the
ordinary chunker cascade, which follows their hyperlinks to staff reports.

Each site is an entry in selfhosted_sites.json keyed by slug (the site's
domain prefix, plus the path segment when one domain hosts several bodies).
Adding a body is a registry entry, not a class.
"""

import asyncio
import base64
import csv
import hashlib
import html as html_lib
import io
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from config import config
from exceptions import VendorHTTPError
from pipeline.protocols import MetricsCollector
from vendors.adapters.base_adapter_async import AsyncBaseAdapter, logger
from vendors.utils.documents import looks_like_minutes


SITES_FILE = Path(config.DB_DIR) / "selfhosted_sites.json"
MAX_PAGES = 40

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_MONTH_RE = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"

# Text dates. "September 14, 16, 2026" and "April 20-21, 2026" take the first day.
_TEXT_DAY_RE = re.compile(
    r"\b" + _MONTH_RE + r"(?:\s+|-)(\d{1,2})(?:st|nd|rd|th)?(?:\s*(?:[-–,&]|and)\s*\d{1,2}(?:st|nd|rd|th)?)*,?\s+(\d{4})", re.I)
_TEXT_DAY_FIRST_RE = re.compile(r"(?<!\d)(\d{1,2})\s+" + _MONTH_RE + r",?\s+(\d{4})", re.I)
_TEXT_NUMERIC_RE = re.compile(r"(?<![\d/-])(\d{1,2})([/-])(\d{1,2})\2(\d{4}|\d{2})(?![\d/-])")
_TEXT_ISO_RE = re.compile(r"(?<!\d)(20\d{2})-(\d{2})-(\d{2})(?!\d)")
_MONTH_DAY_RE = re.compile(r"\b" + _MONTH_RE + r"\s+(\d{1,2})(?!\d)", re.I)
_TEXT_MONTH_RE = re.compile(r"\b" + _MONTH_RE + r",?\s+(\d{4})", re.I)

# URL dates, tried in order. Each names the (year, month, day) groups.
_URL_DATE_PATTERNS: List[Tuple[re.Pattern, Tuple[int, int, Optional[int]]]] = [
    (re.compile(r"(?<!\d)(20\d{2})[-_.]?(\d{2})[-_.]?(\d{2})(?!\d)"), (1, 2, 3)),
    (re.compile(r"(?<!\d)(\d{2})[-_.]?(\d{2})[-_.]?(20\d{2})(?!\d)"), (3, 1, 2)),
    (re.compile(r"(?<!\d)(\d{1,2})[-_.](\d{1,2})[-_.](20\d{2}|\d{2})(?!\d)"), (3, 1, 2)),
    (re.compile(r"(?<![\d.])(\d{2})(\d{2})(\d{2})(?=[a-z_-]|$)", re.I), (3, 1, 2)),
    (re.compile(r"(?<!\d)(20\d{2})[-_/]?(\d{2})(?![\d/])"), (1, 2, None)),
    (re.compile(r"(?<!\d)(\d{2})_(20\d{2})(?!\d)"), (2, 1, None)),
]
# "board-meeting-september-16-17-2026": month, day(s), year.
_URL_MONTH_DAY_RE = re.compile(_MONTH_RE + r"[-_](\d{1,2})(?:[-_]\d{1,2})*[-_](20\d{2})(?!\d)", re.I)
# "oct2026", "oct26", "2026/september/". A two-digit year must touch the month,
# or "september-16" reads as 2016.
_URL_MONTH_NAME_RE = re.compile(r"(?:(20\d{2})/)?" + _MONTH_RE + r"(?:[-_/]?(20\d{2})|(\d{2}))?(?!\d)", re.I)

_DOC_EXT_RE = re.compile(r"\.(pdf|docx?|xlsx?|pptx?|rtf)$", re.I)
# Translations duplicate the English record; the corpus keeps one language.
_TRANSLATION_RE = re.compile(r"espa[nñ]ol|spanish|temario|aviso|revisado|traducci|d[ií]a\s+\d", re.I)
_TRANSLATION_TOKEN_RE = re.compile(r"(?:^|[-_.+\s])(sp|esp|es|span)(?:[-_.+\s]|$)", re.I)
_AGENDA_RE = re.compile(r"\bagenda\b|(?<=\d)ag(?=[_.\-]|$)", re.I)
_NOT_AGENDA_RE = re.compile(r"future\s+agenda|agenda\s+request|draft\s+agenda\s+for|agenda[\s_-]*items?", re.I)
# Non-document links in a row that lead to the meeting's item documents.
_MATERIALS_RE = re.compile(
    r"agenda\s+items|meeting\s+materials|supporting\s+materials|backup\s+materials?|^presentations$|"
    r"(?:board|meeting|agenda)\s+(?:packets?|materials|book)|staff\s+reports|item\s+documents", re.I)

# Item numbers carried by a document's own label or URL.
_LABEL_ITEM_RE = re.compile(
    r"^\s*(?:agenda\s+)?item\s*(?:no\.?\s*)?(\d{1,3}(?:\.\d{1,2})?[a-z]?)\b|^\s*(\d{1,2}(?:\.\d{1,2})?[a-z]?)[.)]?\s+(?=\S)", re.I)
_URL_ITEM_RE = re.compile(r"item[\s_+\-]*0*(\d{1,3}[a-z]?)(?![0-9])|/pdf/(\d{1,3}[a-z]?)/", re.I)
# Labels that name a document's kind rather than its subject.
_GENERIC_LABEL_RE = re.compile(
    r"^(?:(?:agenda\s+)?item\s*\S*|attachment\s*\S*|exhibit\s*\S*|appendix\s*\S*|presentation\s*\S*|supporting\s+document.*|"
    r"ssr|staff\s+(?:summary\s+)?report|executive\s+officer\s+summary\s+report|pdf|download|view|english(?:\s+version)?|"
    r"agenda|minutes|resolution|memo|report|slides|notice|revised\s+notice|day\s+\d|agenda-doc|view\s+agenda|read\s+more)\s*(?:\(pdf\))?$", re.I)

_TABLE_BLOCK_RE = re.compile(
    r'new TableBlock\(\s*"([0-9a-f-]{36})"\s*,\s*"[^"]*"\s*,\s*"(\{[0-9A-F-]{36}\})"\s*,\s*(-?\d+)')
_CHALLENGE_RE = re.compile(r"_Incapsula_Resource|cf-chl|challenge-platform|Verifying your browser|Request unsuccessful", re.I)
_COMMITTEE_RE = re.compile(r"\b(committee|subcommittee|commission|council|panel|task force)\b", re.I)
_TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\.?(?![a-z])", re.I)
_MEETING_WORD_RE = re.compile(r"\b(meeting|committee|board|session|hearing|workshop|retreat|commission|council)\b", re.I)
_ROW_STOP = ("body", "main", "article", "html")
_HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6", "strong", "b", "dt", "th", "caption")
_NOISE_TAGS = ("script", "style", "noscript", "header", "footer", "nav", "aside", "form", "button")
_ITEM_CONTEXT_TAGS = ("li", "tr", "p", "dd", "dt", "td", "div", "span") + _HEADING_TAGS


@dataclass
class Link:
    url: str
    text: str
    anchor: Optional[Tag] = None


@dataclass
class Listing:
    """A meeting as the index presents it."""
    date: Optional[datetime]
    day_precise: bool
    title: str
    links: List[Link] = field(default_factory=list)
    detail_url: Optional[str] = None
    follow_urls: List[str] = field(default_factory=list)
    root: Optional[Tag] = None
    time: Optional[Tuple[int, int]] = None

    def identity(self) -> Tuple:
        return (self.date, self.detail_url, tuple(link.url for link in self.links))


def load_sites() -> Dict[str, Dict[str, Any]]:
    with SITES_FILE.open() as f:
        return json.load(f)


def clean(text: str) -> str:
    # Non-breaking hyphens and spaces ("Oct\u201109\u00a0\u00a02026") read as plain ones.
    return re.sub(r"\s+", " ", (text or "").replace("\u2011", "-").replace("\u00a0", " ")).strip()


def _safe_date(year: int, month: int, day: int) -> Optional[datetime]:
    try:
        return datetime(year, month, day)
    except ValueError:
        return None


def day_dates(text: str) -> List[Tuple[int, datetime]]:
    """Every day-precise date in prose, with its position."""
    found = []
    for m in _TEXT_DAY_RE.finditer(text):
        found.append((m.start(), _safe_date(int(m.group(3)), _MONTHS[m.group(1)[:3].lower()], int(m.group(2)))))
    for m in _TEXT_DAY_FIRST_RE.finditer(text):
        found.append((m.start(), _safe_date(int(m.group(3)), _MONTHS[m.group(2)[:3].lower()], int(m.group(1)))))
    for m in _TEXT_NUMERIC_RE.finditer(text):
        year = int(m.group(4))
        found.append((m.start(), _safe_date(year + 2000 if year < 100 else year, int(m.group(1)), int(m.group(3)))))
    for m in _TEXT_ISO_RE.finditer(text):
        found.append((m.start(), _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))))
    return sorted(((pos, d) for pos, d in found if d and 1990 <= d.year <= 2100), key=lambda f: f[0])


def parse_text_date(text: str) -> Tuple[Optional[datetime], bool]:
    """First date in prose; day-precise when it names a day."""
    found = day_dates(text)
    if found:
        return found[0][1], True
    m = _TEXT_MONTH_RE.search(text)
    if m:
        return _safe_date(int(m.group(2)), _MONTHS[m.group(1)[:3].lower()], 1), False
    return None, False


def parse_filename_date(url: str) -> Tuple[Optional[datetime], bool]:
    """Date in the file's own name; directories are often posting dates."""
    return parse_url_date(url, filename_only=True)


def parse_url_date(url: str, filename_only: bool = False) -> Tuple[Optional[datetime], bool]:
    """Date carried in a URL path; filename first, then directories."""
    segments = [s for s in unquote(urlparse(url).path).split("/") if s]
    for scope in ((segments[-1:],) if filename_only else (segments[-1:], segments)):
        text = "/".join(scope)
        for pattern, (y, mo, d) in _URL_DATE_PATTERNS:
            for m in pattern.finditer(text):
                year = int(m.group(y))
                year = year + 2000 if year < 100 else year
                date = _safe_date(year, int(m.group(mo)), int(m.group(d)) if d else 1)
                if date and 1990 <= year <= 2100:
                    return date, d is not None
        for m in _URL_MONTH_DAY_RE.finditer(text):
            date = _safe_date(int(m.group(3)), _MONTHS[m.group(1)[:3].lower()], int(m.group(2)))
            if date:
                return date, True
        for m in _URL_MONTH_NAME_RE.finditer(text):
            year = m.group(1) or m.group(3) or m.group(4)
            if year:
                year = int(year)
                return _safe_date(year + 2000 if year < 100 else year, _MONTHS[m.group(2)[:3].lower()], 1), False
    return None, False


def is_document(url: str, text: str) -> bool:
    """A file, by extension, by a download route, or by a label like "[PDF/300KB]"."""
    parsed = urlparse(url)
    path = parsed.path.lower()
    # File servers that take the name as a parameter: GetFile.cfm?File=...\Agenda.pdf
    query_file = any(_DOC_EXT_RE.search(v) for v in re.split(r"[&=]", unquote(parsed.query)))
    return bool(_DOC_EXT_RE.search(path) or query_file or "/download" in path or "/media/file/" in path
                or re.search(r"[\[(]\s*pdf\b", text, re.I))


def is_translation(url: str, text: str) -> bool:
    name = unquote(urlparse(url).path.rsplit("/", 1)[-1])
    stem = name.rsplit(".", 1)[0]
    return bool(_TRANSLATION_RE.search(text) or _TRANSLATION_RE.search(name) or _TRANSLATION_TOKEN_RE.search(stem))


def is_agenda(link: Link) -> bool:
    name = unquote(urlparse(link.url).path.rsplit("/", 1)[-1])
    label = f"{link.text} {name}"
    return bool(_AGENDA_RE.search(label.replace("_", " ").replace("-", " ")) or _AGENDA_RE.search(name)) \
        and not _NOT_AGENDA_RE.search(label.replace("_", " ").replace("-", " ")) and not looks_like_minutes(link.text)


def is_minutes(link: Link) -> bool:
    return looks_like_minutes(link.text) or (not link.text and looks_like_minutes(link.url))


def doc_type(url: str) -> str:
    m = _DOC_EXT_RE.search(urlparse(url).path)
    return m.group(1).lower() if m else "pdf"


def content_root(soup: BeautifulSoup, scope: Optional[str]) -> Tag:
    """The page's content region, with site chrome removed."""
    if scope:
        found = soup.select_one(scope)
        if found:
            return found
    for tag in soup.find_all(("script", "style", "noscript", "svg")):
        tag.decompose()
    body = soup.body or soup
    total = _document_count(body)
    # Chrome goes, but only chrome: a stray unclosed <header> or <form> can wrap
    # the whole page once parsed, and removing it would remove the listing.
    for tag in soup.find_all(_NOISE_TAGS):
        if not tag.decomposed and _document_count(tag) * 2 <= total:
            tag.decompose()
    total = _document_count(body)
    # Templates wrap the listing in <main> on some pages and not others (the
    # Central Valley water board's sits beside it), so a region only wins when
    # it actually holds most of the page's documents.
    for selector in ("main", "[role=main]", "#main-content", "#content", "article"):
        found = soup.select_one(selector)
        if found and _document_count(found) * 2 > total:
            return found
    return body


def _document_count(node: Tag) -> int:
    return sum(1 for a in node.find_all("a", href=True) if is_document(str(a["href"]), a.get_text(" ")))


class RowFinder:
    """Smallest ancestor of a link whose text holds exactly one date."""

    def __init__(self, root: Tag):
        self.root = root
        self._dates: Dict[int, List[datetime]] = {}

    def dates(self, node: Tag) -> List[datetime]:
        key = id(node)
        if key not in self._dates:
            seen: List[datetime] = []
            for _, d in day_dates(clean(node.get_text(" "))):
                if d not in seen:
                    seen.append(d)
                if len(seen) > 1:
                    break
            self._dates[key] = seen
        return self._dates[key]

    def row(self, anchor: Tag) -> Tuple[Tag, Optional[datetime]]:
        # Inside a table the row is the <tr>: a cell's own "posted 1/26/2024"
        # stamp is not the meeting date.
        tr = anchor.find_parent("tr")
        node = tr if tr is not None and self.root in tr.parents else anchor.parent
        last = node
        while isinstance(node, Tag) and node is not self.root and node.name not in _ROW_STOP:
            found = self.dates(node)
            if len(found) == 1:
                return node, found[0]
            if len(found) > 1:
                if node.name == "tr":
                    # Calendar rows lead with the meeting date; later cells
                    # carry "posted 1/26/2024" stamps.
                    first = node.find(["td", "th"])
                    lead = self.dates(first) if first is not None else []
                    if len(lead) == 1:
                        return node, lead[0]
                break
            if node.name == "tr":
                # A table row is a row whatever its text says; climbing past it
                # lands on a month heading and merges the month's meetings.
                return node, self.attribute_date(node)
            last = node
            node = node.parent
        return (last if isinstance(last, Tag) else self.root), None

    @staticmethod
    def attribute_date(row: Tag) -> Optional[datetime]:
        """Calendar tables that print only the day keep the date in an anchor id."""
        for tag in row.find_all(id=True):
            m = re.search(r"(?<!\d)(20\d{2})(\d{2})(\d{2})", str(tag["id"]))
            if m:
                return _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return None


def parse_time(text: str) -> Optional[Tuple[int, int]]:
    """First clock time ("9:00 a.m.", "1 PM") in a row or page heading."""
    m = _TIME_RE.search(text)
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2) or 0)
    if not (1 <= hour <= 12 and minute < 60):
        return None
    return (hour % 12) + (12 if m.group(3).lower() == "p" else 0), minute


def heading_date(anchor: Tag) -> Tuple[Optional[datetime], bool]:
    """Date in the nearest heading above an undated row ("August 2026")."""
    for node in anchor.find_all_previous(_HEADING_TAGS, limit=12):
        date, precise = parse_text_date(clean(node.get_text(" ")))
        if date:
            return date, precise
    return None, False


def normalize_key(key: str) -> str:
    """ "03" and "3", "04a" and "4a" are one item."""
    return re.sub(r"^0+(?=\d)", "", key.lower())


def item_key(link: Link) -> Optional[str]:
    m = _LABEL_ITEM_RE.match(link.text.replace("_", " "))
    if m:
        return normalize_key(m.group(1) or m.group(2))
    m = _URL_ITEM_RE.search(unquote(urlparse(link.url).path))
    if m:
        return normalize_key(m.group(1) or m.group(2))
    return None


def item_context(anchor: Tag, root: Tag) -> str:
    """Text naming the item a document belongs to.

    The anchor's own block when it carries words besides its links ("Item 5:
    Waste Discharge Requirements ... [SSR] [Order]"), else the nearest earlier
    block that is not itself a run of document links.
    """
    # Climb a few levels: "<p>1. Consideration of ...<ul><li><a>SSR</a>" puts
    # the item's words two blocks above its documents.
    for depth, node in enumerate(anchor.parents):
        if node is root or not isinstance(node, Tag) or depth > 4:
            break
        if node.name in ("li", "tr", "p", "dd", "td", "div"):
            own = clean(" ".join(s for s in node.find_all(string=True) if not s.find_parent("a")))
            if len(own) > 600:
                break
            if len(own) > 12 and re.search(r"[A-Za-z]{4}", own):
                return own[:400]
    # Walk back to the previous item's documents; the nearest heading in that
    # span names the item (CalSTRS puts "Session: Open | Type: Action" between
    # "Item 3 - Chief Investment Officer's Report" and its files).
    first = ""
    for node in anchor.find_all_previous(_ITEM_CONTEXT_TAGS + ("a",), limit=60):
        if root not in node.parents:
            break
        if node.name == "a":
            if node.get("href") and is_document(str(node["href"]), node.get_text(" ")) and first:
                break
            continue
        if node.find("a", href=True) and node.name not in _HEADING_TAGS:
            continue
        text = clean(node.get_text(" "))
        if not (6 <= len(text) <= 400 and re.search(r"[A-Za-z]{4}", text)):
            continue
        if node.name in _HEADING_TAGS:
            return text
        first = first or text
    return first


def strip_pdf_suffix(text: str) -> str:
    """ "Report (PDF)", "Agenda [PDF/300KB]", "Item_03b_Name.pdf" -> the words."""
    text = re.sub(r"\s*[\[(]\s*(?:pdf|docx?)[^)\]]*[)\]]\s*$", "", text, flags=re.I)
    if _DOC_EXT_RE.search(text) and " " not in text:
        text = _DOC_EXT_RE.sub("", text).replace("_", " ")
    return text.strip()


class AsyncSelfHostedAdapter(AsyncBaseAdapter):
    """Registry-driven adapter for bodies on their own websites."""

    MINUTES_DISCOVERY_SUPPORTED = True
    ORIGINALS_ARCHIVE_SUPPORTED = True

    def __init__(self, city_slug: str, metrics: Optional[MetricsCollector] = None,
                 site: Optional[Dict[str, Any]] = None):
        super().__init__(city_slug, vendor="selfhosted", metrics=metrics)
        # An explicit site is a draft entry under validation.
        site = site or load_sites().get(city_slug)
        if not site:
            raise ValueError(f"No selfhosted site entry for {city_slug!r} in {SITES_FILE.name}")
        self.site = site
        self.index_urls: List[str] = site["index"]
        self.meeting_href = re.compile(site["meeting_href"]) if site.get("meeting_href") else None
        self.default_title: str = site.get("title", "Board Meeting")
        self.scope: Optional[str] = site.get("scope")
        self.detail_scope: Optional[str] = site.get("detail_scope")
        self.exclude = re.compile(site["exclude"], re.I) if site.get("exclude") else None
        # The archive reuses one adapter across a source's monthly windows;
        # refetching the same index page per window is what tripped the
        # waterboards.ca.gov WAF (2026-10-13).
        self._index_cache: Dict[str, str] = {}

    async def _fetch_meetings_impl(self, days_back: int, days_forward: int) -> List[Dict[str, Any]]:
        start, end = self._date_range(days_back, days_forward)
        listings = await self._discover(start, end)
        if self.meeting_href:
            listings = await self._resolve_details(listings, start, end)
        listings = [m for m in listings if m.date and start <= m.date <= end]

        built = await self._bounded_gather(
            [self._build_meeting(listing) for listing in listings], max_concurrent=3, return_exceptions=True)
        results = []
        for listing, meeting in zip(listings, built):
            if isinstance(meeting, BaseException):
                if self._originals_only:
                    self._archive_discovery_errors.append(f"{listing.date:%Y-%m-%d}: {meeting}")
                logger.warning("selfhosted meeting build failed", slug=self.slug,
                               date=str(listing.date), error=str(meeting))
            elif meeting:
                results.append(meeting)
        logger.info("selfhosted meetings fetched", slug=self.slug, count=len(results),
                    start=str(start.date()), end=str(end.date()))
        return results

    # ------------------------------------------------------------------
    # Index pages
    # ------------------------------------------------------------------

    def _index_pages(self, start: datetime, end: datetime) -> Iterable[Tuple[str, bool]]:
        """(url, optional): a templated page may not exist yet (next year's archive)."""
        for url in self.index_urls:
            if "{year}" in url:
                for year in range(end.year, start.year - 1, -1):
                    yield url.replace("{year}", str(year)), True
            else:
                yield url, "{page}" in url

    async def _fetch_html(self, url: str) -> str:
        response = await self._get(url)
        html = await response.text(errors="replace")
        # Bot walls answer 200 with a script shell. Parsed, that is "no
        # meetings" and the sync reports success; it must fail instead.
        if _CHALLENGE_RE.search(html[:4000]) and html.count("<a ") < 5:
            raise VendorHTTPError(f"Bot challenge page instead of content: {url}", vendor=self.vendor,
                                  url=url, city_slug=self.slug)
        return html

    async def _fetch_index(self, url: str) -> str:
        if url not in self._index_cache:
            self._index_cache[url] = await self._fetch_html(url)
        return self._index_cache[url]

    async def discover_listings(self, start: datetime, end: datetime) -> List[Listing]:
        """Index-page listings only: no detail pages, no documents fetched."""
        return await self._discover(start, end)

    async def _discover(self, start: datetime, end: datetime) -> List[Listing]:
        listings: List[Listing] = []
        for template, optional in dict.fromkeys(self._index_pages(start, end)):
            # "{page}" walks a paged listing until a page adds nothing new or
            # every listing on it predates the window.
            pages = (template.replace("{page}", str(n)) for n in range(1, MAX_PAGES + 1)) \
                if "{page}" in template else iter([template])
            seen: set = set()
            for page in pages:
                try:
                    html = await self._fetch_index(page)
                except VendorHTTPError as exc:
                    # A year page the site hasn't published yet is absence, not failure.
                    if (optional or page != template) and "404" in str(exc):
                        break
                    raise
                html = await self._expand_table_blocks(html, page)
                parsed = await asyncio.to_thread(self._parse_index, html, page)
                fresh = [entry for entry in parsed if entry.identity() not in seen]
                seen.update(entry.identity() for entry in parsed)
                listings.extend(fresh)
                if not fresh or all(entry.date and entry.date < start for entry in fresh):
                    break
        return self._merge(listings)

    async def _expand_table_blocks(self, html: str, page_url: str) -> str:
        """Sitecore TableBlock widgets load their rows by script; the widget's
        own CSV export returns the same rows, which become a plain table."""
        blocks = _TABLE_BLOCK_RE.findall(html)
        if not blocks:
            return html
        tables = []
        origin = "{0.scheme}://{0.netloc}".format(urlparse(page_url))
        for page_id, data_source, rendering_hash in blocks:
            source = base64.b64encode(data_source.encode()).decode()
            text = await self._fetch_index(
                f"{origin}/admin/tableutils/CsvExportUnfiltered?pageId={page_id}"
                f"&dataSourceId={source}&renderingParamsHash={rendering_hash}")
            rows = list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))
            # Cells hold the site's own escaped link markup; header row skipped.
            body = "".join("<tr>" + "".join(f"<td>{html_lib.unescape(c)}</td>" for c in row) + "</tr>"
                           for row in rows[1:])
            tables.append(f"<table>{body}</table>")
        return f"<html><body><main>{''.join(tables)}</main></body></html>"

    def _parse_index(self, html: str, page_url: str) -> List[Listing]:
        root = content_root(BeautifulSoup(html, "lxml"), self.scope)
        if self.meeting_href:
            return self._parse_detail_links(root, page_url)
        finder = RowFinder(root)
        rows: Dict[Tuple[int, datetime], Listing] = {}
        for anchor in root.find_all("a", href=True):
            link = self._link(anchor, page_url)
            if not link:
                continue
            document = is_document(link.url, link.text)
            materials = not document and _MATERIALS_RE.search(link.text)
            if not document and not materials:
                continue
            row, date = finder.row(anchor)
            precise = date is not None
            # A document named for its meeting's date is the strongest anchor
            # there is: accordion pages put item prose ("Adoption of the June
            # 25, 2026 Meeting Summary") closer to a link than the yearless
            # "July 23" heading of the meeting it belongs to.
            named, named_precise = parse_filename_date(link.url) if document else (None, False)
            if named and named_precise:
                date, precise = named, True
            if not date:
                date = self._yearless_row_date(row, link)
                precise = date is not None
            if not date:
                date, precise = parse_url_date(link.url) if document else (None, False)
            if not date:
                date, precise = heading_date(anchor)
            if not date:
                continue
            listing = rows.get((id(row), date))
            if listing is None:
                listing = rows[(id(row), date)] = Listing(
                    date=date, day_precise=precise, title=self._row_title(row), time=parse_time(clean(row.get_text(" "))))
            if materials:
                listing.follow_urls.append(link.url)
            else:
                listing.links.append(link)
        return [listing for listing in rows.values() if listing.links or listing.follow_urls]

    @staticmethod
    def _yearless_row_date(row: Tag, link: Link) -> Optional[datetime]:
        """ "February 11" in a calendar row; the year from the URL or the heading above."""
        m = _MONTH_DAY_RE.search(clean(row.get_text(" ")))
        if not m or not link.anchor:
            return None
        year_source = parse_url_date(link.url)[0] or heading_date(link.anchor)[0]
        if not year_source:
            year = re.search(r"\b(20\d{2})\b", " ".join(
                clean(h.get_text(" ")) for h in link.anchor.find_all_previous(_HEADING_TAGS, limit=6)))
            year_source = datetime(int(year.group(1)), 1, 1) if year else None
        if not year_source:
            return None
        return _safe_date(year_source.year, _MONTHS[m.group(1)[:3].lower()], int(m.group(2)))

    def _link(self, anchor: Tag, base: str) -> Optional[Link]:
        href = str(anchor.get("href", "")).strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            return None
        url = urljoin(base, href).split("#", 1)[0]
        if urlparse(url).scheme not in ("http", "https"):
            return None
        text = clean(anchor.get_text(" "))
        if text.startswith("?xml") or "svg PUBLIC" in text:
            # Inline icon markup that the parser surfaced as text.
            text = ""
        text = text or clean(str(anchor.get("title", "")) or str(anchor.get("aria-label", "")))
        if is_translation(url, text) or (self.exclude and (self.exclude.search(url) or self.exclude.search(text))):
            return None
        return Link(url=url, text=text, anchor=anchor)

    def _row_title(self, row: Tag) -> str:
        """Meeting kind the row names (workshop, retreat, special), else the body default.

        Calendars that list hearings and workshops beside board meetings
        (``row_title``) name each event in the row's longest text cell.
        """
        if self.site.get("row_title") and row.name == "tr":
            cells = [clean(c.get_text(" ")) for c in row.find_all(["td", "th"]) if not c.find("a", href=True)]
            # A row's own meeting-page link names that meeting ("Quarterly
            # Board Meeting"); it outranks the body column it repeats.
            linked = [clean(a.get_text(" ")) for a in row.find_all("a", href=True)
                      if not is_document(urljoin("http://x/", str(a["href"])), a.get_text(" "))]
            named = [c for c in linked if _MEETING_WORD_RE.search(c)] or [c for c in cells if _MEETING_WORD_RE.search(c)]
            topic = max(named or cells, key=len, default="")
            if len(topic) > 8 and not parse_text_date(topic)[0]:
                return topic[:200]
        text = clean(row.get_text(" "))
        m = re.search(r"\b(special|workshop|retreat|study session|public hearing|joint|closed session)\b", text, re.I)
        if m:
            return f"{self.default_title} - {m.group(1).title()}"
        return self.default_title

    def _parse_detail_links(self, root: Tag, page_url: str) -> List[Listing]:
        listings: Dict[str, Listing] = {}
        finder = RowFinder(root)
        for anchor in root.find_all("a", href=True):
            url = urljoin(page_url, str(anchor.get("href", ""))).split("#", 1)[0]
            if not self.meeting_href or not self.meeting_href.search(url):
                continue
            text = clean(anchor.get_text(" "))
            # Precedence: the link's own words, the URL, then the surrounding
            # row (which on a sparse page can be a whole column of prose).
            date, precise = parse_text_date(text)
            url_date, url_precise = parse_url_date(url)
            if url_date and (not date or (url_precise and not precise)):
                date, precise = url_date, url_precise
            if not precise:
                row_date = finder.row(anchor)[1]
                if row_date and (not date or (row_date.year, row_date.month) == (date.year, date.month)):
                    date, precise = row_date, True
            prior = listings.get(url)
            if prior and prior.date and (prior.day_precise or not precise):
                continue
            title = text if len(text) > 8 and not parse_text_date(text)[0] and not re.fullmatch(r"(?i)agenda|english|view|details?", text) else self.default_title
            listings[url] = Listing(date=date, day_precise=precise, title=title, detail_url=url)
        return list(listings.values())

    def _merge(self, listings: List[Listing]) -> List[Listing]:
        """One listing per (date, title, detail page); a row split across cells rejoins."""
        merged: Dict[Tuple, Listing] = {}
        for listing in listings:
            key = (listing.date, listing.title, listing.detail_url)
            if key not in merged:
                merged[key] = listing
                continue
            known = {link.url for link in merged[key].links}
            merged[key].links.extend(link for link in listing.links if link.url not in known)
            merged[key].follow_urls.extend(u for u in listing.follow_urls if u not in merged[key].follow_urls)
        return list(merged.values())

    # ------------------------------------------------------------------
    # Detail and materials pages
    # ------------------------------------------------------------------

    async def _resolve_details(self, listings: List[Listing], start: datetime, end: datetime) -> List[Listing]:
        """Fetch detail pages that could fall in range; refine month-only dates."""
        def maybe_in_range(listing: Listing) -> bool:
            if not listing.date:
                return True
            if listing.day_precise:
                return start <= listing.date <= end
            return (start.year, start.month) <= (listing.date.year, listing.date.month) <= (end.year, end.month)

        wanted = [listing for listing in listings if maybe_in_range(listing) and listing.detail_url]
        pages = await self._bounded_gather(
            [self._fetch_html(str(listing.detail_url)) for listing in wanted], max_concurrent=3, return_exceptions=True)
        resolved = []
        for listing, html in zip(wanted, pages):
            if isinstance(html, BaseException):
                if self._originals_only:
                    self._archive_discovery_errors.append(f"{listing.detail_url}: {html}")
                logger.warning("selfhosted detail fetch failed", slug=self.slug,
                               url=listing.detail_url, error=str(html))
                continue
            await asyncio.to_thread(self._apply_detail, listing, str(html))
            resolved.append(listing)
        return resolved

    def _apply_detail(self, listing: Listing, html: str) -> None:
        soup = BeautifulSoup(html, "lxml")
        heading = clean(" ".join(t.get_text(" ") for t in soup.find_all(["title", "h1"])[:3]))
        root = content_root(soup, self.detail_scope)
        if not listing.day_precise:
            date, precise = parse_text_date(heading)
            if not precise:
                date, precise = parse_text_date(clean(root.get_text(" "))[:4000])
            same_month = date and listing.date and (date.year, date.month) == (listing.date.year, listing.date.month)
            if date and precise and (not listing.date or same_month):
                listing.date, listing.day_precise = date, True
        listing.time = listing.time or parse_time(heading) or parse_time(clean(root.get_text(" "))[:1500])
        h1 = clean(soup.h1.get_text(" ")) if soup.h1 else ""
        if 5 <= len(h1) <= 160 and _MEETING_WORD_RE.search(h1):
            listing.title = h1
        listing.root = root
        listing.links = self._documents(root, str(listing.detail_url))
        listing.follow_urls = [
            link.url for a in root.find_all("a", href=True)
            if (link := self._link(a, str(listing.detail_url))) and not is_document(link.url, link.text)
            and _MATERIALS_RE.search(link.text)]

    def _documents(self, root: Tag, base: str) -> List[Link]:
        links: Dict[str, Link] = {}
        for anchor in root.find_all("a", href=True):
            link = self._link(anchor, base)
            if not link or not is_document(link.url, link.text):
                continue
            # An icon and a label often both link the file; keep the label.
            if link.url not in links or (not links[link.url].text and link.text):
                links[link.url] = link
        return list(links.values())

    async def _materials_items(self, listing: Listing) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for url in listing.follow_urls:
            html = await self._fetch_html(url)
            root = await asyncio.to_thread(lambda h=html: content_root(BeautifulSoup(h, "lxml"), self.detail_scope))
            links = await asyncio.to_thread(self._documents, root, url)
            items.extend(self._items(links, root, offset=len(items)))
        return items

    # ------------------------------------------------------------------
    # Meeting assembly
    # ------------------------------------------------------------------

    async def _build_meeting(self, listing: Listing) -> Optional[Dict[str, Any]]:
        agenda = next((link for link in listing.links if is_agenda(link)), None)
        minutes = next((link for link in listing.links if link is not agenda and is_minutes(link)), None)
        if not agenda and not listing.detail_url:
            # An index row whose documents don't say "agenda" (SF Bay labels the
            # agenda with its date) leads with the agenda.
            agenda = next((link for link in listing.links if link is not minutes), None)
        others = [link for link in listing.links if link is not agenda and link is not minutes]
        if not agenda and not minutes and not others and not listing.follow_urls:
            return None

        start = listing.date
        if start and listing.time:
            start = start.replace(hour=listing.time[0], minute=listing.time[1])
        meeting: Dict[str, Any] = {
            "vendor_id": self._vendor_id(listing),
            "title": listing.title,
            "start": start.isoformat() if start else None,
            # body_name is what meeting_sync turns into a committee (as for
            # CivicPlus section headers). A row or page that names its own
            # committee ("Committee on Finance, Audit & Budget") is that body;
            # otherwise it is the agency's board.
            "body_name": listing.title if listing.title != self.default_title and _COMMITTEE_RE.search(listing.title)
            else self.site.get("body", self.default_title),
            "metadata": {"source_page": listing.detail_url or self.index_urls[0]},
        }
        status = self._parse_meeting_status(f"{listing.title} {' '.join(link.text for link in listing.links)}")
        if status:
            meeting["meeting_status"] = status
        if agenda:
            meeting["agenda_url"] = agenda.url
        if minutes:
            meeting["minutes_url"] = minutes.url
        if self._minutes_discovery_only:
            return meeting

        if listing.detail_url:
            items = self._items(others, listing.root)
        else:
            # Index rows carry reports beside the agenda (EO reports, notices).
            items = [self._single_item(link, i + 1) for i, link in enumerate(others)]
        if listing.follow_urls:
            items += await self._materials_items(listing)

        # Item documents on the page are the agenda's substance; the agenda PDF
        # is chunked only when the page gave nothing finer.
        if agenda and not any(item.get("agenda_number") for item in items):
            linked = await self._agenda_items(agenda, meeting["vendor_id"])
            items = linked + [{**item, "sequence": len(linked) + i + 1} for i, item in enumerate(items)]
        if items:
            meeting["items"] = items
        return meeting

    async def _agenda_items(self, agenda: Link, vendor_id: str) -> List[Dict[str, Any]]:
        if not self._originals_only:
            return await self._chunk_agenda_then_packet(agenda_url=agenda.url, vendor_id=vendor_id)
        # Archive mode: only the first-level documents the agenda links to.
        if not urlparse(agenda.url).path.lower().endswith(".pdf"):
            return []
        result = await self._chunk_packet_pdf(agenda.url, vendor_id, ladder="archive_url")
        if result.failure_reason in {"timeout", "engine_error", "open_failed", "encrypted", "download_failed"}:
            self._archive_discovery_errors.append(f"agenda link discovery failed: {result.failure_reason} ({agenda.url})")
            return []
        return result.items or []

    def _single_item(self, link: Link, sequence: int) -> Dict[str, Any]:
        title = strip_pdf_suffix(link.text)
        if (not title or _GENERIC_LABEL_RE.match(title)) and link.anchor is not None:
            # "PDF", "Agenda", "View" name the file type; the row says what it is.
            body = link.anchor.find_parent("body")
            title = (item_context(link.anchor, body) if body is not None else "") or title
        title = clean(title)[:500] or "Document"
        return {
            "vendor_item_id": hashlib.sha256(link.url.encode()).hexdigest()[:12],
            "title": title,
            "sequence": sequence,
            "attachments": [{"name": title, "url": link.url, "type": doc_type(link.url)}],
        }

    def _items(self, links: List[Link], root: Optional[Tag], offset: int = 0) -> List[Dict[str, Any]]:
        """Group a page's documents into items, anchor-first."""
        groups: Dict[str, Dict[str, Any]] = {}
        # One page can hold several committees' agendas, each numbering from 1.
        # A key seen before, reached from a different key, starts a new agenda.
        namespace, previous, used = 0, None, set()
        for link in links:
            key = item_key(link)
            context = item_context(link.anchor, root) if link.anchor is not None and root is not None else ""
            if not key and context:
                m = _LABEL_ITEM_RE.match(context)
                key = normalize_key(m.group(1) or m.group(2)) if m else None
            if key:
                if key in used and key != previous:
                    namespace += 1
                    used = set()
                used.add(key)
                previous = key
                key = f"{namespace}.{key}" if namespace else key
            group_key = key or (f"h:{context[:160]}" if context else f"u:{link.url}")
            label = strip_pdf_suffix(link.text)
            informative = bool(label) and not _GENERIC_LABEL_RE.match(label)
            if group_key not in groups:
                title = label if informative and not _LABEL_ITEM_RE.match(label) else (context or label)
                if informative and _LABEL_ITEM_RE.match(label):
                    title = _LABEL_ITEM_RE.sub("", label, count=1) or label
                groups[group_key] = {
                    "vendor_item_id": key or hashlib.sha256(group_key.encode()).hexdigest()[:12],
                    "title": clean(title)[:500] or "Document",
                    "sequence": offset + len(groups) + 1,
                    "attachments": [],
                }
                if key:
                    groups[group_key]["agenda_number"] = key.split(".", 1)[1] if namespace and "." in key else key
            groups[group_key]["attachments"].append(
                {"name": label or "Document", "url": link.url, "type": doc_type(link.url)})
        return list(groups.values())

    def _vendor_id(self, listing: Listing) -> str:
        """Date plus meeting kind (or detail page): stable across revised agenda filenames."""
        basis = listing.detail_url or listing.title
        digest = hashlib.sha256(f"{self.slug}|{basis}".encode()).hexdigest()[:8]
        return f"{listing.date:%Y%m%d}-{digest}" if listing.date else digest
