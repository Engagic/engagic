"""
Publications: what a public body issues outside of meetings.

Executive agencies, courts and grand juries publish reports, regulations,
orders and findings with no agenda around them. Their listing pages reduce to
one model, simpler than a meeting: a document link, the title the listing
gives it, and the date it prints, if any. This reuses the self-hosted
adapter's page machinery (lxml parsing, chrome stripping, bot-wall detection,
per-host rate limits) and differs only in what it collects.

Each source is an entry in data/publication_sources.json keyed by slug (the
site's domain prefix, plus a path segment when one domain hosts several):

  index         listing pages; a "{year}" template expands as in selfhosted
  listing_href  regex for links on an index page that lead to more listings
                (one term's reports, one volume of regulations); followed once
  scope, exclude  as in selfhosted
  banana        the body's row, when it already exists (it publishes meetings)
  jurisdiction  {name, state, type, vernacular, parent} for a body that has no
                row yet; scripts/ingest_publications.py onboard creates it

Dates are stored only when the listing states a day: in the link's own words,
in the file's name, or in a row that holds this document alone. A month, a
term ("2024-2025") or a page-level "updated" stamp is not a publication date.
"""

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup, Tag

from config import config
from exceptions import VendorHTTPError
from vendors.adapters.custom.selfhosted_adapter_async import (
    _GENERIC_LABEL_RE,
    AsyncSelfHostedAdapter,
    Link,
    RowFinder,
    clean,
    content_root,
    is_document,
    item_context,
    parse_filename_date,
    parse_text_date,
    strip_pdf_suffix,
)
from vendors.adapters.base_adapter_async import logger


SOURCES_FILE = Path(config.DB_DIR) / "publication_sources.json"

# Translations duplicate the English record. A document's language is the
# marker at the end of its label ("-- Arabic", "Chinese Traditional Document")
# or of its file name (d-170-final-posted-arabic.pdf), never a language word
# inside the title: D-170 is about "English Language Learners" in every
# translation. Two signals, both from the page: a page that marks any document
# English marks its translations too, so a document marked with another
# language is one; and documents sharing a title differ only by language, so
# those marked with another language translate the one that is unmarked.
_LANGUAGES = (
    r"english|spanish|espa[nñ]ol|chinese|arabic|bangla|bengali|french|haitian|creole|korean|russian|urdu|polish|"
    r"vietnamese|tagalog|japanese|italian|portuguese|hindi|punjabi|farsi|persian|yiddish|hebrew|greek|"
    r"german|somali|hmong|khmer|armenian|ukrainian|nepali|burmese|thai|lao|amharic|albanian|uzbek|tajik|pashto|"
    r"dari|swahili|wolof|fulani|mandarin|cantonese|turkish|malayalam|tamil|telugu|gujarati|marathi|romanian|"
    r"serbian|bosnian|croatian|czech|slovak|hungarian|dutch|indonesian|malay|ilocano|samoan|tongan|marshallese|"
    r"chuukese|navajo|kurdish|tigrinya|oromo|kinyarwanda|mixtec|mixteco|k'iche'?|quiche")
_LANGUAGE_RE = re.compile(rf"\b({_LANGUAGES})\b", re.I)
# How much of a label's end counts as its marker: "-- French (Haiti) Haitian Creole".
_MARKER_CHARS = 40
_TRAILING_LANGUAGE_RE = re.compile(
    rf"(?:\s*(?:--|[-–|])?\s*\(?(?:{_LANGUAGES})(?:\s*\([^)]*\))?\)?)+\s*$", re.I)
# A row holding more documents than this is a section, not one document's row;
# its single date is a heading or an "updated" stamp.
_MAX_ROW_DOCUMENTS = 2


@dataclass
class Publication:
    url: str
    title: str
    published_on: Optional[date]


def load_sources() -> Dict[str, Dict[str, Any]]:
    with SOURCES_FILE.open() as f:
        return json.load(f)


class AsyncPublicationsAdapter(AsyncSelfHostedAdapter):
    """Registry-driven lister for a body's publications."""

    # "Language Access: Spanish" is a report, not a translation; _collect
    # decides from the page instead.
    DROP_LABELED_TRANSLATIONS = False

    def __init__(self, slug: str, site: Optional[Dict[str, Any]] = None):
        site = site or load_sources().get(slug)
        if not site:
            raise ValueError(f"No publications entry for {slug!r} in {SOURCES_FILE.name}")
        super().__init__(slug, site=site)
        self.listing_href = re.compile(site["listing_href"]) if site.get("listing_href") else None

    async def fetch_publications(self, since: datetime) -> List[Publication]:
        """Every document the listings show. `since` bounds "{year}" templates
        only: a listing's undated documents are kept whatever their age."""
        pages: List[str] = []
        found: Dict[str, Publication] = {}
        for template, optional in dict.fromkeys(self._index_pages(since, datetime.now())):
            try:
                html = await self._fetch_index(template)
            except VendorHTTPError as exc:
                # A year page the site hasn't published yet is absence, not failure.
                if optional and "404" in str(exc):
                    continue
                raise
            root = await asyncio.to_thread(self._root, html)
            self._collect(root, template, found)
            if self.listing_href:
                pages.extend(self._follow_links(root, template))
        pages = list(dict.fromkeys(p for p in pages if p not in self._index_cache))
        fetched = await self._bounded_gather([self._fetch_index(p) for p in pages], max_concurrent=3,
                                             return_exceptions=True)
        for page, html in zip(pages, fetched):
            if isinstance(html, BaseException):
                logger.warning("publications listing fetch failed", slug=self.slug, url=page, error=str(html))
                continue
            root = await asyncio.to_thread(self._root, str(html))
            self._collect(root, page, found)
        logger.info("publications listed", slug=self.slug, pages=len(pages) + len(self.index_urls),
                    documents=len(found), dated=sum(1 for p in found.values() if p.published_on))
        return list(found.values())

    def _root(self, html: str) -> Tag:
        return content_root(BeautifulSoup(html, "lxml"), self.scope)

    def _follow_links(self, root: Tag, base: str) -> List[str]:
        urls = []
        for anchor in root.find_all("a", href=True):
            link = self._link(anchor, base)
            if link and self.listing_href and self.listing_href.search(link.url) and not is_document(link.url, link.text):
                urls.append(link.url)
        return urls

    def _collect(self, root: Tag, page_url: str, found: Dict[str, Publication]) -> None:
        links = self._documents(root, page_url)
        marked = [(link, self._title(link, root), self._language(link)) for link in links]
        english_page = any(language == "english" for _, _, language in marked)
        unmarked_titles = {_TRAILING_LANGUAGE_RE.sub("", title) for _, title, language in marked if language is None}
        finder = RowFinder(root)
        for link, title, language in marked:
            if link.url in found:
                continue
            if language not in (None, "english") and (
                    english_page or _TRAILING_LANGUAGE_RE.sub("", title) in unmarked_titles):
                continue
            found[link.url] = Publication(url=link.url, title=_TRAILING_LANGUAGE_RE.sub("", title) or title,
                                          published_on=self._published_on(link, finder))

    @staticmethod
    def _language(link: Link) -> Optional[str]:
        """The language a document is marked with, if any."""
        name = unquote(urlparse(link.url).path.rsplit("/", 1)[-1]).rsplit(".", 1)[0]
        row = link.anchor.find_parent(("tr", "li")) if link.anchor is not None else None
        for text in (link.text, name.replace("-", " ").replace("_", " "), clean(row.get_text(" ")) if row is not None else ""):
            found = _LANGUAGE_RE.findall(text[-_MARKER_CHARS:])
            if found:
                return found[-1].lower()
        return None

    @staticmethod
    def _title(link: Link, root: Tag) -> str:
        title = strip_pdf_suffix(link.text).strip()
        if (not title or _GENERIC_LABEL_RE.match(title)) and link.anchor is not None:
            title = item_context(link.anchor, root) or title
        return clean(title)[:500] or "Document"

    @staticmethod
    def _published_on(link: Link, finder: RowFinder) -> Optional[date]:
        stated, precise = parse_text_date(link.text)
        if stated and precise:
            return stated.date()
        named, precise = parse_filename_date(link.url)
        if named and precise:
            return named.date()
        if link.anchor is None:
            return None
        row, row_date = finder.row(link.anchor)
        if row_date and row is not finder.root:
            documents = sum(1 for a in row.find_all("a", href=True) if is_document(str(a["href"]), a.get_text(" ")))
            if documents <= _MAX_ROW_DOCUMENTS:
                return row_date.date()
        return None
