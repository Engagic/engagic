# Vendors Module - Civic Tech Platform Adapters

**Fetch meeting data from 13 civic tech platforms.** Unified adapter architecture with vendor-specific parsers and shared utilities.

**Last Updated:** February 2026

---

## Overview

The vendors module provides adapters for fetching meeting data from civic technology platforms used by local governments. Each adapter implements the `AsyncBaseAdapter` interface while handling vendor-specific quirks in HTML parsing, API integration, and data extraction.

**Architecture Pattern:** AsyncBaseAdapter + Vendor-Specific Parsers + Shared Utilities

```
vendors/
├── adapters/           # 13 async adapters
│   ├── base_adapter_async.py          # Async base (262 lines)
│   ├── legistar_adapter_async.py      # Legistar async (1212 lines)
│   ├── primegov_adapter_async.py      # PrimeGov async (320 lines)
│   ├── granicus_adapter_async.py      # Granicus async (347 lines)
│   ├── iqm2_adapter_async.py          # IQM2 async (576 lines)
│   ├── novusagenda_adapter_async.py   # NovusAgenda async (199 lines)
│   ├── escribe_adapter_async.py       # eScribe async (420 lines)
│   ├── civicclerk_adapter_async.py    # CivicClerk async (362 lines)
│   ├── civicplus_adapter_async.py     # CivicPlus async (369 lines)
│   ├── municode_adapter_async.py      # Municode async (503 lines)
│   ├── onbase_adapter_async.py        # OnBase async (464 lines)
│   ├── custom/
│   │   ├── berkeley_adapter_async.py  # Berkeley async (295 lines)
│   │   ├── chicago_adapter_async.py   # Chicago async (796 lines)
│   │   └── menlopark_adapter_async.py # Menlo Park async (182 lines)
│   └── parsers/        # 5 vendor-specific HTML parsers
│       ├── legistar_parser.py         # Legistar HTML tables (373 lines)
│       ├── primegov_parser.py         # PrimeGov HTML items (315 lines)
│       ├── granicus_parser.py         # Granicus HTML formats (414 lines)
│       ├── municode_parser.py         # Municode HTML sections (213 lines)
│       └── novusagenda_parser.py      # NovusAgenda HTML items (116 lines)
├── extractors/         # Data extraction utilities
│   └── council_member_extractor.py    # Sponsor extraction (281 lines)
├── utils/              # Shared utilities
│   └── attachments.py                 # Attachment version filtering (162 lines)
├── factory.py          # Adapter dispatcher (62 lines)
├── rate_limiter_async.py              # Async vendor rate limiting (53 lines)
├── session_manager_async.py           # Async HTTP pooling (143 lines)
├── validator.py        # Domain validation (270 lines)
└── schemas.py          # Pydantic validation schemas (155 lines)

Total: ~8,905 lines
```

---

## Architecture

### AsyncBaseAdapter Pattern

All vendor adapters inherit from `AsyncBaseAdapter`, which provides:
- **Async HTTP client** (aiohttp via `AsyncSessionManager`) with timeout and error handling
- **Date parsing** utilities (handles various vendor formats)
- **Metrics collection** via `MetricsCollector` protocol
- **Error handling** with `VendorHTTPError` (vendor, URL, city context)
- **Fallback vendor ID generation** (SHA256 hash for vendors without native IDs)
- **Meeting status detection** (cancelled, postponed, deferred, revised)
- **Meeting validation** (requires vendor_id, title, start)
- **FetchResult contract** - distinguishes "0 meetings" from "adapter failed"

```python
# vendors/adapters/base_adapter_async.py

@dataclass
class FetchResult:
    """Distinguishes success from failure."""
    meetings: List[Dict[str, Any]] = field(default_factory=list)
    success: bool = True
    error: Optional[str] = None
    error_type: Optional[str] = None

class AsyncBaseAdapter:
    def __init__(self, city_slug: str, vendor: str, metrics: Optional[MetricsCollector] = None):
        self.slug = city_slug
        self.vendor = vendor
        self.metrics = metrics or NullMetrics()

    async def fetch_meetings(self, days_back: int = 7, days_forward: int = 14) -> FetchResult:
        """Validates results, catches exceptions, returns FetchResult."""
        # Calls _fetch_meetings_impl(), validates each meeting, wraps result

    async def _fetch_meetings_impl(self, days_back: int, days_forward: int) -> List[Dict[str, Any]]:
        """Subclass must implement. Return raw meeting dicts."""
        raise NotImplementedError

    async def _get(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        """GET request via shared session. Raises VendorHTTPError on failure."""

    async def _post(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        """POST request. Raises VendorHTTPError on failure."""

    async def _get_json(self, url: str, **kwargs) -> Any:
        """GET + JSON parse. Handles content-type mismatches."""

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse vendor date formats (ISO, US, human-readable)."""

    def _generate_fallback_vendor_id(self, title: str, date: Optional[datetime], ...) -> str:
        """SHA256 hash (12 hex chars) for vendors without native IDs."""

    def _parse_meeting_status(self, title: str, date_str: Optional[str] = None) -> Optional[str]:
        """Detect cancelled/postponed/deferred/revised/rescheduled from text."""
```

### Adapter ID Contract

Adapters return `vendor_id` (the native vendor identifier), NOT canonical `meeting_id`. The database layer generates canonical meeting IDs.

```python
# Adapter returns meeting dict with vendor_id
{
    "vendor_id": "12345",           # Native ID from vendor (required)
    "title": "City Council",
    "start": "2025-11-10T18:00:00",
    "agenda_url": "https://...",    # HTML agenda (when items extracted)
    "packet_url": "https://...",    # PDF packet (monolithic fallback)
    "items": [...],                 # Optional: extracted agenda items
    "participation": {...},         # Optional: public comment info
    "meeting_status": "cancelled",  # Optional: cancelled/postponed/etc.
    "metadata": {...},              # Optional: vendor-specific extras
}
```

**vendor_id by Vendor:**

| Vendor | vendor_id Source | Example |
|--------|-----------------|---------|
| Legistar | `EventId` from API | `"98765"` |
| PrimeGov | `id` from API | `"12345"` |
| Chicago | `meetingId` from API | `"abc-uuid-123"` |
| NovusAgenda | `MeetingID` from HTML or fallback hash | `"4567"` |
| CivicClerk | `id` from OData API | `"789"` |
| IQM2 | ID from Detail_Meeting URL | `"1234"` |
| CivicPlus | `civic_` + ID from URL or MD5 hash | `"civic_456"` |
| eScribe | `escribe_` + UUID from meeting URL | `"escribe_7b0..."` |
| Granicus | `event_id` from ViewPublisher listing | `"5678"` |
| OnBase | Meeting ID from page JSON/HTML | `"9012"` |
| Municode | `MeetingID` from API or date+type composite | `"3456"` |
| Berkeley | SHA256 hash of URL path + date | `"a1b2c3d4e5f6"` |
| Menlo Park | SHA256 hash of PDF URL + date | `"f6e5d4c3b2a1"` |

**Database generates canonical ID:** `{banana}_{8-char-md5-hash}`

See `database/README.md` for ID generation details.

---

## Vendor Adapters

### Item-Level Adapters (11 adapters)

These adapters extract **structured agenda items** from HTML agendas, APIs, or PDFs. Items are stored separately with `matter_id`, `matter_file`, titles, and PDF links.

**1. Legistar (1212 lines)**
- **Dual mode:** API-first (`/Events` endpoint), HTML fallback (`Calendar.aspx` scraping)
- **API:** OData-style filtering, handles both JSON and XML responses (NYC returns XML)
- **HTML:** Calendar RadGrid → meeting detail pages → item tables via `legistar_parser.py`
- **Item extraction:**
  - API: `EventItems` endpoint per event, concurrent fetches
  - HTML: `parse_html_agenda()` parses `rgMasterTable` with column mapping
- **Matter tracking:** `EventItemMatterId`, `EventItemMatterFile`, sponsors from `/matters/{id}/sponsors`
- **Votes:** Fetched from `/EventItems/{id}/Votes` with normalization (yea→yes, nay→no, etc.)
- **Attachments:** From `/matters/{id}/attachments`, filters Leg Ver versions (keeps highest)
- **Roster:** `fetch_roster_data()` fetches Bodies and OfficeRecords for committee membership
- **City examples:** Seattle WA, NYC, Cambridge MA

**2. PrimeGov (320 lines)**
- **API + HTML scraping:** REST API for meeting lists, HTML scraping for item extraction
- **API endpoints:** `/api/v2/PublicPortal/ListUpcomingMeetings` and `/ListArchivedMeetings?year=`
- **Multiple agenda types:** Regular, Continuation, Special agendas fetched in parallel, merged with deduplication
- **Parser:** `primegov_parser.py` handles three HTML patterns (LA/newer, Palo Alto/older, Boulder/table)
- **Matter tracking:** `data-mig` GUID, `data-itemid`, `forcepopulate` table metadata
- **Attachments:** Via `historyattachment` API endpoint with `history_id`
- **Participation:** Extracted from agenda HTML (contact info, zoom links)
- **City examples:** Palo Alto CA, Mountain View CA, Sunnyvale CA

**3. Granicus (347 lines)**
- **HTML scraping:** Two-step process - ViewPublisher.php listing → AgendaViewer/AgendaOnline detail
- **Config dependency:** Requires `data/granicus_view_ids.json` mapping base URLs to view IDs
- **Parser:** `granicus_parser.py` handles three HTML formats:
  - AgendaOnline accessible view (`ViewMeetingAgenda`)
  - AgendaOnline table-based (older format)
  - Original AgendaViewer with File IDs and MetaViewer attachments
- **Attachments:** Fetched from AgendaOnline item detail pages, DownloadFile→ViewDocument URL translation
- **Encoding:** UTF-8 with latin-1 fallback (Granicus often misreports encoding)
- **SSL:** Disabled for Granicus domains (cert issues on S3 redirects)
- **Participation:** Council member extraction from blue-styled header spans
- **City examples:** Cambridge MA, Santa Monica CA, Redwood City CA

**4. IQM2 (576 lines)**
- **HTML scraping:** Calendar page → Detail_Meeting.aspx → MeetingDetail table
- **Multiple URL patterns:** Tries `/Citizens`, `/Citizens/Calendar.aspx`, `/Citizens/Default.aspx`
- **Inline parsing:** No dedicated parser; parses MeetingDetail table directly in adapter
- **Matter tracking:** LegiFile IDs from `Detail_LegiFile.aspx` links, case numbers extracted via regex
- **Metadata:** Fetches matter_type, sponsors, department, attachments from Detail_LegiFile pages
- **Attachment dedup:** By file ID parameter in URL (same files appear in multiple views)
- **City examples:** Boise ID, Santa Monica CA, Cambridge MA, Buffalo NY

**5. NovusAgenda (199 lines)**
- **HTML scraping:** `/agendapublic` page → RadGrid table rows → MeetingView.aspx for items
- **Parser:** `novusagenda_parser.py` extracts items via CoverSheet.aspx links
- **Agenda selection:** Prioritizes "HTML Agenda" over "View Agenda" over generic links
- **Date format:** `%m/%d/%y` (2-digit year)
- **City examples:** Hagerstown MD, Houston TX

**6. Chicago (796 lines) - Custom**
- **REST API** at `api.chicityclerkelms.chicago.gov`
- **OData-style filtering** with pagination (500 per page, 2000 cap)
- **Item extraction hierarchy:** API `agenda.groups[].items[]` → PDF extraction → packet fallback
- **PDF fallback:** Extracts record numbers (O2025-0019668) from agenda PDF, fetches matter data via `/matter/recordNumber/`
- **Matter data:** Attachments, sponsors, status, votes all from `/matter/{id}` (votes embedded in actions)
- **Vote normalization:** Yea→yes, Nay→no, etc.
- **Stats tracking:** Per-sync metrics (meetings, items, votes, attachments, API requests)
- **Participation:** Public comment deadline and instructions
- **Metadata:** Video links, transcript links, body info, related meetings

**7. eScribe (420 lines)**
- **Calendar API + HTML scraping:** POST to `/MeetingsCalendarView.aspx/GetCalendarMeetings`, then `/Meeting.aspx?Agenda=Merged` for items
- **Date handling:** Parses `/Date(timestamp)/` format (millisecond timestamps)
- **Item extraction:** `.AgendaItemContainer` elements with numeric IDs from CSS classes
- **Matter tracking:** Extracts case numbers via regex patterns (BOA-0039-2025, RES-2025-123, etc.)
- **Matter type inference:** Derives type from prefix (BOA→Board of Adjustment, ORD→Ordinance, etc.)
- **Per-item attachments:** `FileStream.ashx?DocumentId=` links
- **City examples:** Raleigh NC

**8. CivicClerk (362 lines)**
- **OData REST API** at `{slug}.api.civicclerk.com`
- **OData pagination:** Follows `@odata.nextLink` for multi-page results
- **Item extraction:** Fetches structured items from `/v1/Meetings/{agendaId}`, flattens section hierarchy (recursive `isSection` traversal)
- **Bill parsing:** Extracts Board Bill, Resolution, Ordinance numbers from HTML titles
- **Attachments:** Per-item `attachmentsList` with `pdfVersionFullPath`/`mediaFullPath` URLs
- **CORS headers:** Requires Origin/Referer headers matching portal domain
- **City examples:** St. Louis MO, Montpelier VT, Burlington VT

**9. Municode (503 lines)**
- **Dual mode:** Subdomain API (`{slug}.municodemeetings.com/api/v1/`) or PublishPage HTML (`meetings.municode.com/PublishPage/`)
- **Mode detection:** Hyphens in slug = subdomain API; short alphanumeric = PublishPage city code
- **Config dependency:** `data/municode_sites.json` for ppid overrides
- **Parser:** `municode_parser.py` extracts items from `<section class="agenda-section">` structure
- **HTML agenda:** Fetches from `/adaHtmlDocument/index?cc={code}&me={guid}&ip=True`
- **City code discovery:** Auto-discovers from API response URLs (`cc=` param, blob paths)
- **Participation:** Extracted from HTML (contact info, zoom links)
- **City examples:** Columbus GA, Tomball TX, Los Gatos CA, Cedar Park TX

**10. OnBase (464 lines)**
- **Config-based:** Sites configured in `data/onbase_sites.json`, keyed by banana
- **Platform:** Hyland OnBase Agenda Online (direct instances, not via Granicus)
- **Deployments:** Hyland Cloud (`{city}.hylandcloud.com`), self-hosted, multiple sites per city
- **Meeting listing:** JSON extraction from inline page data or static HTML links
- **Item extraction:** Reuses `granicus_parser.parse_agendaonline_html()` (shared format)
- **Attachments:** Fetched from item detail pages, DownloadFile→ViewDocument URL translation
- **Multi-URL strategy:** Tries `Documents/ViewAgenda` and `Meetings/ViewMeetingAgenda`, keeps best result
- **City examples:** San Diego CA, Tucson AZ, Tampa FL, Durham NC

**11. Berkeley (295 lines) - Custom**
- **Custom Drupal CMS** at `berkeleyca.gov`
- **HTML scraping:** Table rows with `<time>` tags for dates
- **Item extraction:** `<strong>1.</strong><a href="...pdf">Title</a>` pattern
- **Sponsors:** From `From:` lines following items
- **Recommendations:** Extracted from `Recommendation:` lines
- **Participation:** Zoom URL, phone number, email from intro paragraphs
- **Attachments:** PDF links from item anchors

---

### Monolithic Adapters (2 adapters)

These adapters fetch **PDF packet URLs only** (no structured items). Meetings are processed with comprehensive LLM summarization.

**12. CivicPlus (369 lines)**
- **Domain discovery:** Tries `{slug}.civicplus.com`, `{slug}.gov`, `{slug}.org` variants
- **HTML scraping:** AgendaCenter pages → ViewFile/Agenda links or meeting detail pages
- **No item extraction:** Fetches packet PDFs only
- **Meeting ID:** Extracts from URL `id=` param or generates MD5 hash of normalized URL
- **Date extraction:** From URL pattern (`_MMDDYYYY-ID`) or page text
- **Deduplication:** By date (keeps last uploaded, typically packet over agenda)
- **City examples:** Various mid-size cities

**13. Menlo Park (182 lines) - Custom**
- **Custom scraper** for Menlo Park CA's table-based website
- **PDF item extraction:** Downloads agenda PDF, extracts text via `PdfExtractor`, parses items via `parse_menlopark_pdf_agenda()`
- **Item format:** Letter-based sections (H., I., J., K.) with numbered items (H1., J1.)
- **Attachments:** Hyperlinked PDFs within agenda PDF (Staff Reports, Presentations)
- **Note:** While items are extracted from PDFs, the source document is a PDF rather than structured HTML/API data

---

## HTML Parsing Architecture

**Separation of Concerns:** Adapters fetch data, Parsers extract structure.

### Parser Inventory

| Parser | Adapter | Patterns Handled |
|--------|---------|-----------------|
| `legistar_parser.py` | Legistar | `rgMasterTable` RadGrid with column mapping; `LegislationDetail.aspx` attachments |
| `primegov_parser.py` | PrimeGov | LA pattern (meeting-item + forcepopulate), Palo Alto (agenda-item), Boulder (table data-itemid) |
| `granicus_parser.py` | Granicus, OnBase | ViewPublisher listing, AgendaOnline accessible/table views, AgendaViewer with MetaViewer |
| `municode_parser.py` | Municode | `agenda-section` → `agenda-items` → `agenda_item_attachments` |
| `novusagenda_parser.py` | NovusAgenda | CoverSheet.aspx links, exploratory multi-pattern detection |

**Adapters without dedicated parsers** (inline parsing): IQM2, eScribe, CivicClerk, CivicPlus, Berkeley, Chicago, Menlo Park.

**Why separate parsers?**
- **Vendor updates:** HTML changes → update parser only, adapter unchanged
- **Testing:** Can test parsing logic independently
- **Reusability:** Granicus parser is reused by OnBase adapter
- **Clarity:** Adapter focuses on HTTP/retry, parser focuses on DOM traversal

---

## Shared Utilities

### Attachment Version Filtering (vendors/utils/attachments.py)

**Version-based deduplication:** Filters to include at most one version of versioned documents.

```python
def filter_version_attachments(attachments, version_patterns=None, name_key='name'):
    """
    Filter attachments to include at most one version of versioned documents.
    Prefers higher version numbers (Ver2 > Ver1).
    Default patterns: ['leg ver', 'legislative version'] (Legistar)
    """

def normalize_attachment_metadata(attachment, vendor):
    """Normalize attachment fields across vendors to consistent {name, url, metadata} format."""
```

### Council Member Extractor (vendors/extractors/council_member_extractor.py)

**Sponsor extraction** from adapter output with normalization and deduplication.

```python
class CouncilMemberExtractor:
    """Extract council member/sponsor data from vendor output."""

    @staticmethod
    def extract_sponsors_from_item(item) -> List[str]:
        """Handles: item["sponsors"] (list), item["sponsor"] (str), item["metadata"]["sponsors"]."""

    @staticmethod
    def extract_all_sponsors_from_meeting(meeting) -> Dict[str, List[str]]:
        """Returns mapping of matter_id -> sponsor names for linking."""

    @staticmethod
    def normalize_sponsors(sponsors) -> List[str]:
        """Normalize via database.id_generation.normalize_sponsor_name()."""

async def process_meeting_sponsors(meeting, banana, council_member_repo, meeting_date=None) -> int:
    """Convenience: extract sponsors, create/update council members, create sponsorship links."""
```

---

## Pydantic Validation (schemas.py)

**Runtime validation** at adapter boundaries before database storage.

```python
class MeetingSchema(BaseModel):
    vendor_id: str          # Required, non-empty
    title: str              # Required, non-empty
    start: str              # ISO format string (NOT datetime object)
    location: Optional[str]
    agenda_url: Optional[str]
    packet_url: Optional[str]
    items: Optional[List[AgendaItemSchema]]
    participation: Optional[Dict]
    meeting_status: Optional[str]
    vendor_body_id: Optional[str]   # Legistar committee/body ID
    metadata: Optional[Dict]

class AgendaItemSchema(BaseModel):
    vendor_item_id: Optional[str]   # Falls back to sequence
    title: str                      # Required, non-empty
    sequence: int                   # Coerced from string if needed
    attachments: List[AttachmentSchema] = []
    matter_id: Optional[str]
    matter_file: Optional[str]
    matter_type: Optional[str]
    agenda_number: Optional[str]
    sponsors: Optional[List[str]]
    votes: Optional[List[Dict]]
    metadata: Optional[Dict]

class AttachmentSchema(BaseModel):
    name: str
    url: str                        # Required, non-empty
    type: str                       # pdf, doc, spreadsheet, unknown
    history_id: Optional[str]       # PrimeGov-specific
```

---

## Rate Limiting Strategy

**Delay-based rate limiting** prevents overwhelming civic tech platforms with vendor-specific delays between requests.

```python
# vendors/rate_limiter_async.py
class AsyncRateLimiter:
    delays = {
        "primegov": 3.0,
        "granicus": 4.0,
        "civicclerk": 3.0,
        "legistar": 3.0,
        "civicplus": 8.0,    # Aggressive blocking, needs longer delays
        "novusagenda": 4.0,
        "iqm2": 3.0,
        "escribe": 3.0,
        "unknown": 5.0,      # Fallback (municode, berkeley, chicago, menlopark, onbase)
    }
```

**Features:**
- Async-safe with `asyncio.Lock()`
- Per-vendor delay tracking
- CivicPlus gets extra random jitter (0-2s) to avoid pattern detection
- All other vendors get 0-1s random jitter
- Non-blocking delays via `asyncio.sleep()`

---

## Session Management (session_manager_async.py)

**Centralized HTTP pooling** using aiohttp for all vendor adapters.

- **One session per vendor** (not per city) with connection reuse
- **Connection limits:** 20 total, 5 per host, DNS cache 5 min
- **Browser-like headers** to avoid bot detection
- **Configurable timeout:** 30s default (total), 10s connect
- **Lazy creation:** Sessions created on first use
- **Stats:** `get_stats()` returns active sessions and connection counts

---

## Vendor Factory (factory.py)

**Adapter dispatcher:** Maps vendor name → async adapter class.

```python
VENDOR_ADAPTERS = {
    "granicus": AsyncGranicusAdapter,
    "iqm2": AsyncIQM2Adapter,
    "legistar": AsyncLegistarAdapter,
    "novusagenda": AsyncNovusAgendaAdapter,
    "onbase": AsyncOnBaseAdapter,
    "primegov": AsyncPrimeGovAdapter,
    "civicclerk": AsyncCivicClerkAdapter,
    "civicplus": AsyncCivicPlusAdapter,
    "escribe": AsyncEscribeAdapter,
    "municode": AsyncMunicodeAdapter,
    "berkeley": AsyncBerkeleyAdapter,
    "chicago": AsyncChicagoAdapter,
    "menlopark": AsyncMenloParkAdapter,
}

def get_async_adapter(vendor: str, city_slug: str, metrics: Optional[MetricsCollector] = None, **kwargs):
    """Get async adapter instance. Raises VendorError if unsupported.
    Passes api_token for Legistar if provided in kwargs."""
```

---

## URL Domain Validation (validator.py)

**Domain validation** prevents data corruption by verifying URLs match vendor configuration.

- Validates `packet_url`, `agenda_url`, and attachment URLs against expected vendor domains
- Supports domain patterns per vendor (including CDN domains like S3, CloudFront)
- **Return actions:** `store` (valid), `warn` (suspicious but allowed), `reject` (domain mismatch)
- **Note:** Currently used in tests only; not integrated into production pipeline

Vendors with configured domains: primegov, granicus, legistar, civicclerk, novusagenda, civicplus, civicweb, iqm2, municode, escribe, menlopark, berkeley, chicago.

---

## Configuration Dependencies

Several adapters require static configuration files:

| Adapter | Config File | Contents |
|---------|------------|----------|
| Granicus | `data/granicus_view_ids.json` | Maps base URLs to `view_id` integers |
| OnBase | `data/onbase_sites.json` | Maps banana to list of site URL paths |
| Municode | `data/municode_sites.json` | Per-city overrides (ppid, etc.) |

Adapters fail fast in `__init__` if their config is missing or the city is not configured.

---

## Adding a New Vendor Adapter

### 1. Create Async Adapter Class

```python
# vendors/adapters/newvendor_adapter_async.py
from vendors.adapters.base_adapter_async import AsyncBaseAdapter, logger
from pipeline.protocols import MetricsCollector

class AsyncNewVendorAdapter(AsyncBaseAdapter):
    def __init__(self, city_slug: str, metrics: Optional[MetricsCollector] = None):
        super().__init__(city_slug, vendor="newvendor", metrics=metrics)
        self.base_url = f"https://{self.slug}.newvendor.com"

    async def _fetch_meetings_impl(self, days_back: int = 7, days_forward: int = 14) -> List[Dict[str, Any]]:
        # 1. Fetch meeting list (API or HTML)
        # 2. Filter by date range
        # 3. Fetch details concurrently
        # 4. Return list of meeting dicts with vendor_id, title, start, items/packet_url
        ...
```

### 2. Register in Factory

```python
# vendors/factory.py
from vendors.adapters.newvendor_adapter_async import AsyncNewVendorAdapter

VENDOR_ADAPTERS = {
    ...
    "newvendor": AsyncNewVendorAdapter,
}
```

### 3. Add Rate Limiting (Optional)

Add vendor-specific delay to `rate_limiter_async.py` if needed (otherwise defaults to 5.0s "unknown").

### 4. Test

```bash
python -m pipeline.conductor sync-city examplecityCA --force
```

---

## Debugging Adapters

### Common Issues

**1. No meetings returned**
- Check date range (some vendors only show future meetings)
- Verify URL construction (city_slug might be case-sensitive)
- Check HTTP response via debug logging

**2. Parsing failures**
- HTML structure changed (vendor updated their site)
- BeautifulSoup selectors too specific
- Missing null checks on DOM elements

**3. Rate limiting (429 errors)**
- Increase delay in `rate_limiter_async.py`
- CivicPlus is most aggressive; uses 8s + 0-2s jitter

**4. SSL errors**
- Granicus has known SSL cert issues on S3 redirects (SSL disabled in base adapter for granicus domains)

---

**See Also:**
- [pipeline/README.md](../pipeline/README.md) - How adapters integrate with processing pipeline
- [database/README.md](../database/README.md) - How meeting data is stored

**Last Updated:** 2026-02-10 (Full code audit: line counts, adapter capabilities, patterns, config deps)
