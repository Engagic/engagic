"""
Dockets: a state regulatory commission's case-management system.

A docket system is a record system rather than a body's page: one commission,
tens of thousands of cases, each with filings (testimony, exhibits, rulings,
transcripts, reports) accumulating over years. Cases are listed by the
system's own case key, the only enumeration these systems expose without a
form postback, so a backfill walks the keys and a missing case is absence.

Each system kind is a class whose list_case(key) returns a RawDocket: the
caption the case page prints and its filings, each with its documents. The
adapter returns raw vendor identities; scripts/ingest_dockets.py mints ids and
writes dockets/docket_filings, and archives the documents as originals.

Which systems exist, their hosts, case ranges and owning bodies live in
data/docket_systems.json (git-ignored), keyed by system:

  kind      the class below that parses it
  base      the system's root URL
  body      the owning body's banana, or a jurisdiction block for
            scripts/ingest_publications.ensure_body to create
  range     [newest, oldest] case keys to walk
  per_year  for kinds whose keys restart yearly: the highest number to try

Public comments are separate endpoints on every system here and are not
collected: they are individuals' letters, not the record. ZIPs hold native
files and are skipped.
"""

import asyncio
import html
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from bs4 import BeautifulSoup, Tag

from config import config
from exceptions import VendorHTTPError
from vendors.adapters.base_adapter_async import AsyncBaseAdapter

SYSTEMS_FILE = Path(config.DB_DIR) / "docket_systems.json"
_ARCHIVES = {"zip", "7z", "rar"}
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


class BotWallError(VendorHTTPError):
    """A challenge page where a listing was expected: stop the system, record nothing."""


@dataclass
class RawDocument:
    url: str
    name: str


@dataclass
class RawFiling:
    vendor_filing_id: str
    filing_type: Optional[str]
    description: Optional[str]
    filer: Optional[str]
    filed_on: Optional[date]
    documents: List[RawDocument] = field(default_factory=list)

    @property
    def title(self) -> str:
        parts = [p for p in (self.filing_type, self.description) if p]
        if self.filer:
            parts.append(f"filed by {self.filer}")
        return " | ".join(parts)[:500] or "Filing"


@dataclass
class RawDocket:
    case_key: str
    url: str
    docket_number: Optional[str] = None
    title: Optional[str] = None
    filings: List[RawFiling] = field(default_factory=list)


def load_systems() -> Dict[str, Dict[str, Any]]:
    with SYSTEMS_FILE.open() as f:
        return json.load(f)


def _text(node: Optional[Tag]) -> str:
    return _SPACE_RE.sub(" ", node.get_text(" ", strip=True)).strip() if node is not None else ""


def _date(value: str, fmt: str = "%m/%d/%Y") -> Optional[date]:
    try:
        return datetime.strptime(value.strip().split()[0], fmt).date()
    except (ValueError, IndexError):
        return None


def _kept(url: str, name: str = "") -> bool:
    ext = url.split("?", 1)[0].rsplit(".", 1)[-1].lower()
    name_ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return ext not in _ARCHIVES and name_ext not in _ARCHIVES


def _labelled(page_text: str, label: str) -> Optional[str]:
    """The value printed after 'Label' in a page flattened with | between cells.
    Flattening drops empty cells, so a "value" that is itself a label (ends in
    a colon) means the field was blank."""
    i = page_text.find(label)
    if i < 0:
        return None
    rest = page_text[i + len(label):].lstrip(" :|")
    value = rest.split("|", 1)[0].strip()
    return value if value and not value.endswith(":") else None


class DocketSystem(AsyncBaseAdapter):
    """Shared transport: paced per host under the 'dockets' rate-limit class."""

    def __init__(self, system: str, conf: Dict[str, Any]):
        super().__init__(system, "dockets")
        self.system = system
        self.conf = conf
        self.base = conf["base"].rstrip("/")

    @property
    def body(self):
        return self.conf["body"]

    def case_numbers(self, start: int, end: int) -> Iterator[int]:
        step = -1 if start > end else 1
        return iter(range(start, end + step, step))

    async def _page(self, url: str) -> Tuple[BeautifulSoup, str]:
        response = await self._get(url)
        # Older ASP systems serve cp1252 without declaring it.
        text = (await response.read()).decode(response.charset or "utf-8", errors="replace")
        head = text[:5000].lower()
        if "incapsula" in head or "captcha" in head or "cf-chl" in head:
            raise BotWallError(f"challenge page at {url}", self.vendor, status_code=response.status,
                               url=url, city_slug=self.slug)
        soup = await asyncio.to_thread(BeautifulSoup, text, "lxml")
        # Unescaped after tags are cut, so an escaped "<" in a caption stays text.
        flat = _SPACE_RE.sub(" ", re.sub(r"(\|\s*)+", "|", html.unescape(_TAG_RE.sub("|", text))))
        return soup, flat

    async def list_case(self, key: int) -> Optional[RawDocket]:
        raise NotImplementedError


class NYDPS(DocketSystem):
    """documents.dps.ny.gov: CaseMaster/PublicDocuments/{MatterSeq} returns a
    case's filed documents as (double-encoded) JSON, one row per document with
    its filing's FilingSeq; documents download from Common/ViewDoc.aspx. The
    CaseMaster page prints the case number and title."""

    async def list_case(self, key: int) -> Optional[RawDocket]:
        url = f"{self.base}/CaseMaster/PublicDocuments/{key}"
        response = await self._get(url)
        text = await response.text()
        try:
            rows = json.loads(text) if text.strip() else []
            if isinstance(rows, str):
                rows = json.loads(rows) if rows.strip() else []
        except json.JSONDecodeError:
            if "<html" in text[:2000].lower():
                raise BotWallError(f"non-JSON HTML for case {key}", self.vendor, status_code=response.status,
                                   url=url, city_slug=self.slug)
            rows = []
        if not rows:
            return None
        filings: Dict[str, RawFiling] = {}
        for row in rows:
            ref = row.get("DocRefNo")
            if not ref:
                continue  # links out to the tariff system; no document here
            fid = str(row.get("FilingSeq") or row.get("FilingNo") or ref)
            name = _TAG_RE.sub("", row.get("DocTitle") or "").strip() or row.get("DocName") or "Document"
            filing = filings.setdefault(fid, RawFiling(
                vendor_filing_id=fid, filing_type=row.get("Doctype"), description=name,
                filer=row.get("FilingCompany"), filed_on=_date(row.get("DateFiled") or "")))
            filing.documents.append(RawDocument(url=f"{self.base}/Common/ViewDoc.aspx?DocRefId={ref}",
                                                name=row.get("DocName") or name))
        page_url = f"{self.base}/MatterManagement/CaseMaster.aspx?MatterSeq={key}"
        _, flat = await self._page(page_url)
        # Incidents and filed statements are matters without a case number;
        # their matter number is what the commission cites them by.
        number = _labelled(flat, "Case Number:") or _labelled(flat, "Matter Number:")
        return RawDocket(case_key=str(key), url=page_url, docket_number=number,
                         title=_labelled(flat, "Title of Matter/Case:"), filings=list(filings.values()))


class TXPUC(DocketSystem):
    """interchange.puc.texas.gov: a control number's filings are one table
    (item, file stamp, party, item type, description) under its 'Style'; each
    item's page lists its files at /Documents/{control}_{item}_{id}.{ext}."""

    async def list_case(self, key: int) -> Optional[RawDocket]:
        url = (f"{self.base}/search/filings/?UtilityType=A&ControlNumber={key}"
               f"&ItemMatch=Equal&DocumentType=ALL&SortBy=ItemNumber&SortOrder=Ascending")
        page, flat = await self._page(url)
        rows = []
        for row in page.find_all("tr"):
            anchor = row.find("a", href=lambda h: bool(h) and "itemNumber=" in h)
            cells = [_text(c) for c in row.find_all("td")]
            if anchor and len(cells) >= 5:
                rows.append((anchor["href"], cells))
        if not rows:
            return None
        listed = await self._bounded_gather([self._item(href, cells) for href, cells in rows],
                                            max_concurrent=2, return_exceptions=True)
        filings = []
        for result in listed:
            # A filing page that failed fails the case, so it is listed again
            # rather than checkpointed without that filing.
            if isinstance(result, BaseException):
                raise result
            filings.append(result)
        return RawDocket(case_key=str(key), url=url, docket_number=str(key), title=_labelled(flat, "Style"),
                         filings=filings)

    async def _item(self, href: str, cells: List[str]) -> RawFiling:
        item, stamp, party, item_type, description = cells[:5]
        filing = RawFiling(vendor_filing_id=item, filing_type=item_type or None, description=description or None,
                           filer=party or None, filed_on=_date(stamp))
        page, _ = await self._page(self.base + href.replace("&amp;", "&"))
        for anchor in page.find_all("a", href=lambda h: bool(h) and "/Documents/" in h):
            if _kept(anchor["href"]):
                filing.documents.append(RawDocument(url=anchor["href"], name=_text(anchor)))
        return filing


class ORPUC(DocketSystem):
    """apps.puc.state.or.us/edockets: docket.asp?DocketID={n} prints the docket
    number and name, then each filing as a Date/Action row holding one
    edocs.asp link, followed by a Description row."""

    async def list_case(self, key: int) -> Optional[RawDocket]:
        url = f"{self.base}/docket.asp?DocketID={key}"
        page, flat = await self._page(url)
        filings: Dict[str, RawFiling] = {}
        for anchor in page.find_all("a", href=lambda h: bool(h) and "edocs.asp" in h):
            row = anchor.find_parent("tr")
            cells = row.find_all("td", recursive=False) if row is not None else []
            if len(cells) < 3:
                continue
            following = row.find_next_sibling("tr")
            description = ""
            if following is not None and "Description" in following.get_text():
                description = re.sub(r"^\s*Description\s*", "", _text(following))
            seq = re.search(r"numSequence=(\d+)", anchor["href"])
            doc_url = f"{self.base}/{anchor['href']}"
            fid = seq.group(1) if seq else doc_url
            filing = filings.setdefault(fid, RawFiling(
                vendor_filing_id=fid, filing_type=re.sub(r"^\s*Action:\s*", "", _text(cells[2])) or None,
                description=description or None, filer=None, filed_on=_date(_text(cells[1]))))
            name = re.search(r"FileName=([^&]+)", anchor["href"])
            filing.documents.append(RawDocument(url=doc_url, name=name.group(1) if name else "document"))
        if not filings:
            return None
        return RawDocket(case_key=str(key), url=url, docket_number=_labelled(flat, "Docket No:"),
                         title=_labelled(flat, "Docket Name:"), filings=list(filings.values()))


class WAUTC(DocketSystem):
    """utc.wa.gov: /casedocket/{year}/{yynnnn}/docsets lists each filing as a
    row (type, date, description) holding its files, which download from
    apiproxy.utc.wa.gov/cases/GetDocument. Numbers restart each year."""

    def case_numbers(self, start: int, end: int) -> Iterator[int]:
        for yy in range(start // 10000, end // 10000 - 1, -1):
            for n in range(int(self.conf["per_year"]), 0, -1):
                key = yy * 10000 + n
                if end <= key <= start:
                    yield key

    async def list_case(self, key: int) -> Optional[RawDocket]:
        yy = key // 10000
        case_url = f"{self.base}/casedocket/{2000 + yy if yy < 70 else 1900 + yy}/{key:06d}"
        page, _ = await self._page(f"{case_url}/docsets")
        filings: Dict[str, RawFiling] = {}
        for anchor in page.find_all("a", href=lambda h: bool(h) and "GetDocument" in h):
            row = anchor.find_parent("tr")
            if row is None:
                continue
            cells = row.find_all("td", recursive=False)
            box = anchor.find_parent("div", id=True)
            fid = box["id"] if box is not None else _text(row)[:120]
            description = cells[2].find(string=True, recursive=False) if len(cells) > 2 else None
            filing = filings.setdefault(fid, RawFiling(
                vendor_filing_id=fid, filing_type=(_text(cells[0]) or None) if cells else None,
                description=(description or "").strip() or None, filer=None,
                filed_on=_date(_text(cells[1])) if len(cells) > 1 else None))
            name = _text(anchor)
            if _kept(anchor["href"], name):
                filing.documents.append(RawDocument(url=anchor["href"], name=name))
        if not filings:
            return None
        # The details page prints the prefixed number (UE-230172), the company and a summary.
        _, flat = await self._page(case_url)
        number = _labelled(flat, "Docket Number|") or f"{key:06d}"
        company = _labelled(flat, "Company|")
        summary = _labelled(flat, "Summary|")
        title = " | ".join(p for p in (company, summary) if p)[:1000] or None
        return RawDocket(case_key=f"{key:06d}", url=case_url, docket_number=number, title=title,
                         filings=list(filings.values()))


class KYPSC(DocketSystem):
    """psc.ky.gov: /Case/ViewCaseFilings/{yyyy}-{nnnnn} prints the case number
    and caption, then each filing as a row (received time, description, filer)
    holding files under /pscecf/ (e-filed) or /pscscf/ (Commission-issued).
    Numbers restart each year. The /Public variant is public comments."""

    def case_numbers(self, start: int, end: int) -> Iterator[int]:
        for year in range(start // 100000, end // 100000 - 1, -1):
            for n in range(int(self.conf["per_year"]), 0, -1):
                key = year * 100000 + n
                if end <= key <= start:
                    yield key

    async def list_case(self, key: int) -> Optional[RawDocket]:
        number = f"{key // 100000}-{key % 100000:05d}"
        url = f"{self.base}/Case/ViewCaseFilings/{number}"
        page, flat = await self._page(url)
        filings: Dict[str, RawFiling] = {}
        for anchor in page.find_all("a", href=lambda h: bool(h) and ("/pscecf/" in h or "/pscscf/" in h)):
            row = anchor.find_parent("tr")
            if row is None:
                continue
            received = _text(row.find(id="spnRcvdDt"))
            description = _text(row.find(id="pFileDesc"))
            fid = f"{received}|{description[:200]}"
            filing = filings.setdefault(fid, RawFiling(
                vendor_filing_id=fid, filing_type=None, description=description or None,
                filer=_text(row.find(id="pFiler")) or None, filed_on=_date(received)))
            if _kept(anchor["href"]):
                filing.documents.append(RawDocument(url=anchor["href"], name=_text(anchor)))
        if not filings:
            return None
        # The caption is the cell before "Docket for Case"; only e-filed cases
        # put an "Electronic Case" label in front of it.
        head = flat.split("|Docket for Case", 1)
        caption = head[0].rsplit("|", 1)[-1].strip() if len(head) == 2 else ""
        return RawDocket(case_key=number, url=url, docket_number=number, title=caption or None,
                         filings=list(filings.values()))


class FLPSC(DocketSystem):
    """pscweb.floridapsc.com (the API behind floridapsc.com's Angular app):
    ClerkOffice/PSCDocketFilingsDetails pages a docket's filings as JSON
    (document number, filed date, description, files with direct links);
    DocketDetailsByDocketsNo carries the docket title. Docket numbers are
    yyyynnnn and restart each year. Letters from consumers are filed as
    'CORRESPONDENCE-Consumers & Representatives' and are not collected, for
    the same reason public comments are not."""

    API = "https://pscweb.floridapsc.com/api/ClerkOffice"
    PAGE = 500

    def case_numbers(self, start: int, end: int) -> Iterator[int]:
        for year in range(start // 10000, end // 10000 - 1, -1):
            for n in range(int(self.conf["per_year"]), 0, -1):
                key = year * 10000 + n
                if end <= key <= start:
                    yield key

    async def _api(self, route: str, **params: Any) -> Dict[str, Any]:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        data = await self._get_json(f"{self.API}/{route}?{query}")
        if not isinstance(data, dict):
            raise BotWallError(f"non-JSON answer from {route}", self.vendor, url=self.API, city_slug=self.slug)
        return data.get("result") or {}

    async def list_case(self, key: int) -> Optional[RawDocket]:
        filings: List[RawFiling] = []
        page = 1
        while True:
            result = await self._api("PSCDocketFilingsDetails", pageNumber=page, pageSize=self.PAGE,
                                     sortFieldName="", sortingOrder="", docketNumber=key, documentType="")
            for row in result.get("result") or []:
                description = (row.get("description") or "").strip()
                if description.lower().startswith("correspondence-consumers"):
                    continue
                filing = RawFiling(vendor_filing_id=row.get("documentNumber") or description[:120],
                                   filing_type=None, description=description or None, filer=None,
                                   filed_on=_date((row.get("documentFiledDate") or "")[:10], "%Y-%m-%d"))
                for f in row.get("files") or []:
                    if f.get("link") and _kept(f["link"], f.get("fullName") or ""):
                        filing.documents.append(RawDocument(url=f["link"], name=f.get("fullName") or f["link"]))
                filings.append(filing)
            if not result.get("hasNextPage"):
                break
            page += 1
        if not filings:
            return None
        details = await self._api("DocketDetailsByDocketsNo", pageNumber=1, pageSize=1, sortFieldName="",
                                  sortingOrder="", docketNo=key, searchKey="")
        events = (details.get("result") or {}).get("docketEventDetails") or []
        title = events[0].get("docketTitle") if events else None
        return RawDocket(case_key=str(key), url=f"https://www.floridapsc.com/clerks-office-dockets-level2?DocketNo={key}",
                         docket_number=str(key), title=title, filings=filings)


class GAPSC(DocketSystem):
    """psc.ga.gov FACTS: /search/service-facts-docket/?docketId={n} pages a
    docket's filings as JSON (documentId, company, filed date, description);
    each filing's page /search/facts-document/?documentId= links its files at
    services.psc.ga.gov/.../DownloadFile/{documentId}/{fileId}. The docket
    page prints the title."""

    PAGE = 1000

    async def list_case(self, key: int) -> Optional[RawDocket]:
        rows: List[Dict[str, Any]] = []
        page = 1
        while True:
            data = await self._get_json(f"{self.base}/search/service-facts-docket/?docketId={key}&sortDirection=asc"
                                        f"&sortColumn=&searchText=&pageSize={self.PAGE}&pageNumber={page}")
            if not isinstance(data, dict):
                raise BotWallError(f"non-JSON answer for docket {key}", self.vendor, url=self.base,
                                   city_slug=self.slug)
            batch = data.get("resultsItems") or []
            rows.extend(batch)
            if len(rows) >= int(data.get("resultsCount") or 0) or not batch:
                break
            page += 1
        if not rows:
            return None
        listed = await self._bounded_gather([self._filing(row) for row in rows], max_concurrent=2,
                                            return_exceptions=True)
        filings = []
        for result in listed:
            # A filing page that failed fails the case, so it is listed again
            # rather than checkpointed without that filing.
            if isinstance(result, BaseException):
                raise result
            filings.append(result)
        url = f"{self.base}/search/facts-docket/?docketId={key}"
        _, flat = await self._page(url)
        return RawDocket(case_key=str(key), url=url, docket_number=str(key), title=_labelled(flat, "Title:"),
                         filings=filings)

    async def _filing(self, row: Dict[str, Any]) -> RawFiling:
        companies = ", ".join(c.get("companyName", "").strip() for c in row.get("companyDetailsVm") or []
                              if c.get("companyName"))
        filing = RawFiling(vendor_filing_id=str(row["documentId"]), filing_type=None,
                           description=(row.get("description") or "").strip() or None, filer=companies or None,
                           filed_on=_date((row.get("filedDate") or "")[:10], "%Y-%m-%d"))
        if row.get("hasAttachment") is False:
            return filing
        page, _ = await self._page(f"{self.base}/search/facts-document/?documentId={row['documentId']}")
        for anchor in page.find_all("a", href=lambda h: bool(h) and "/DownloadFile/" in h):
            name = _text(anchor)
            if _kept(anchor["href"], name):
                filing.documents.append(RawDocument(url=anchor["href"], name=name))
        return filing


KINDS = {"gapsc": GAPSC, "flpsc": FLPSC, "nydps": NYDPS, "txpuc": TXPUC, "orpuc": ORPUC, "wautc": WAUTC, "kypsc": KYPSC}


def system_adapter(system: str) -> DocketSystem:
    conf = load_systems()[system]
    return KINDS[conf["kind"]](system, conf)
