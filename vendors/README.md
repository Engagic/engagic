# Vendors Module - Civic Tech Platform Adapters

**Fetch meeting data from 11 civic tech platforms.** Unified adapter architecture with vendor-specific parsers and shared utilities.

**Last Updated:** November 24, 2025

---

## Overview

The vendors module provides adapters for fetching meeting data from civic technology platforms used by local governments. Each adapter implements the `AsyncBaseAdapter` interface while handling vendor-specific quirks in HTML parsing, API integration, and data extraction.

**Architecture Pattern:** AsyncBaseAdapter + Vendor-Specific Parsers + Shared Utilities

**Migration Status:** All 11 adapters async (migration complete Nov 2025)

```
vendors/
├── adapters/           # 11 async adapters
│   ├── base_adapter_async.py       # Async base (639 lines)
│   ├── legistar_adapter_async.py   # Legistar async (1170 lines)
│   ├── primegov_adapter_async.py   # PrimeGov async (353 lines)
│   ├── granicus_adapter_async.py   # Granicus async (148 lines)
│   ├── iqm2_adapter_async.py       # IQM2 async (693 lines)
│   ├── novusagenda_adapter_async.py # NovusAgenda async (254 lines)
│   ├── escribe_adapter_async.py    # eScribe async (522 lines) - ITEM-LEVEL
│   ├── civicclerk_adapter_async.py # CivicClerk async (134 lines)
│   ├── civicplus_adapter_async.py  # CivicPlus async (436 lines)
│   ├── custom/
│   │   ├── berkeley_adapter_async.py  # Berkeley async (328 lines)
│   │   ├── chicago_adapter_async.py   # Chicago async (805 lines)
│   │   └── menlopark_adapter_async.py # Menlo Park async (206 lines)
│   └── parsers/        # 4 vendor-specific HTML parsers
│       ├── legistar_parser.py      # Legistar HTML tables - 373 lines
│       ├── primegov_parser.py      # PrimeGov HTML tables - 287 lines
│       ├── granicus_parser.py      # Granicus HTML tables - 141 lines
│       └── novusagenda_parser.py   # NovusAgenda HTML - 116 lines
├── extractors/         # Data extraction utilities
│   └── council_member_extractor.py # Extract council members from Legistar (281 lines)
├── utils/              # Shared utilities
│   ├── item_filters.py    # Procedural item detection (277 lines)
│   └── attachments.py     # Attachment deduplication (162 lines)
├── factory.py          # Adapter dispatcher (82 lines)
├── rate_limiter_async.py  # Async vendor rate limiting (53 lines)
├── session_manager_async.py  # Async HTTP pooling (143 lines)
├── validator.py        # Meeting validation (270 lines)
└── schemas.py          # Pydantic validation schemas (145 lines)

**Total:** ~7,758 lines (all async, sync code removed Nov 2025)
```

---

## Architecture

### AsyncBaseAdapter Pattern

All vendor adapters inherit from `AsyncBaseAdapter`, which provides:
- **Async HTTP client** (aiohttp) with retry logic and timeout handling
- **Date parsing** utilities (handles various formats)
- **Rate limiting** integration (async-aware)
- **Error handling** with context (vendor, city, URL)
- **Common interface** (`fetch_meetings()` async method)

```python
# vendors/adapters/base_adapter_async.py
class AsyncBaseAdapter:
    def __init__(self, city_slug: str, vendor: str):
        self.slug = city_slug
        self.vendor = vendor
        self.session: Optional[aiohttp.ClientSession] = None

    async def fetch_meetings(self, days_back: int = 7, days_forward: int = 14) -> List[Dict]:
        """Fetch meetings for date range. MUST be implemented by subclass."""
        raise NotImplementedError

    async def _get(self, url: str, params: Optional[Dict] = None) -> aiohttp.ClientResponse:
        """Async HTTP GET with retry and rate limiting."""
        # Shared async retry logic

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date from various vendor formats."""
        # Handles: "11/20/2025", "2025-11-20", "Nov 20, 2025", etc.
```

### Adapter ID Contract

Adapters return `vendor_id` (the native vendor identifier), NOT canonical `meeting_id`. The database layer generates canonical meeting IDs.

```python
# Adapter returns meeting dict with vendor_id
{
    "vendor_id": "12345",           # Native ID from vendor (required)
    "title": "City Council",
    "start": "2025-11-10T18:00:00",
    "agenda_url": "https://...",    # HTML agenda (item-level)
    "packet_url": "https://...",    # PDF packet (monolithic)
    "items": [...],                 # Optional: extracted agenda items
}
```

**vendor_id by Vendor:**

| Vendor | vendor_id Source | Example |
|--------|-----------------|---------|
| Legistar | `EventId` from API | `"98765"` |
| PrimeGov | `id` from API | `"12345"` |
| Chicago | `meetingId` from API | `"abc-uuid-123"` |
| NovusAgenda | `MeetingID` from HTML | `"4567"` |
| CivicClerk | `id` from API | `"789"` |
| IQM2 | ID extracted from URL | `"meeting_123"` |
| CivicPlus | ID extracted from URL | `"civic_456"` |
| Escribe | ID from URL or generated | `"esc_789"` |
| Granicus | `meeting_id` from API | `"gran_123"` |
| Berkeley | Date string (no native ID) | `"20251110"` |
| Menlo Park | Date string (no native ID) | `"20251110"` |

**Database generates canonical ID:** `{banana}_{8-char-md5-hash}`

See `database/README.md` for ID generation details.

---

## Vendor Adapters

### Item-Level Adapters (7 adapters - 88% of cities)

These adapters extract **structured agenda items** from HTML agendas or APIs. Items are stored separately with `matter_id`, `matter_file`, titles, and PDF links.

**1. Legistar (1170 lines) - 110 cities**
- **Dual mode:** API-first, fallback to HTML scraping
- **API:** `/events.json` endpoint with structured JSON
- **HTML:** Calendar view → meeting detail pages → item tables
- **Item extraction:**
  - API: Direct JSON parsing of `EventItems` array
  - HTML: `legistar_parser.py` parses `<tr>` tables with `data-id` attributes
- **Matter tracking:** `File #` column → `matter_file`, `EventItemMatterId` → `matter_id`
- **PDF links:** Attachment URLs from `EventItemAgendaFile` or HTML hrefs
- **City examples:** NYC, Los Angeles, San Francisco, Seattle, Boston

**2. PrimeGov (353 lines) - 64 cities**
- **HTML scraping only:** Agenda list → detail pages → item tables
- **Parser:** `primegov_parser.py` handles `<table class="agenda">` structure
- **Item extraction:**
  - Title from `<td class="title">` or first `<td>`
  - Matter from `<td class="file">` or pattern matching in title
  - PDF links from `<a href="/agendas/...">` in row
- **Quirks:** Some cities use non-standard table classes (handled via selectors)
- **City examples:** Austin TX, Portland OR, San Diego CA

**3. Granicus (148 lines) - 467 cities (200+ with item extraction)**
- **Hybrid:** API for meeting list, HTML scraping for items
- **API:** `/meetings` JSON endpoint for meeting metadata
- **HTML:** Meeting detail pages → `granicus_parser.py` parses agenda tables
- **Item extraction:**
  - Title from `<div class="item-title">` or `<h3>` tags
  - Matter from `<span class="item-number">` or title prefixes
  - PDF links from `<a class="attachment">` or inline PDFs
- **Coverage:** Not all Granicus cities have structured agendas (fallback to monolithic)
- **City examples:** Sacramento CA, Denver CO, Phoenix AZ

**4. IQM2 (693 lines) - 45 cities**
- **HTML scraping:** Agenda calendar → detail pages → item tables
- **No dedicated parser:** Inline parsing in adapter (could extract to parser)
- **Item extraction:**
  - Title from `<div class="agenda-item-title">`
  - Matter from `<span class="item-number">` or title prefix
  - PDF links from `<a class="pdf-link">`
- **City examples:** Fremont CA, Alameda CA

**5. NovusAgenda (254 lines) - 38 cities**
- **HTML scraping:** Meeting list → detail → `novusagenda_parser.py`
- **Parser:** Handles `<table id="agenda">` with rowspan/colspan complexity
- **Item extraction:**
  - Title from `<td class="title">` (may span multiple rows)
  - Matter from `<td class="number">` or pattern in title
  - PDF attachments from nested `<ul class="attachments">`
- **Quirks:** Heavy use of rowspan/colspan requires careful DOM traversal
- **City examples:** Santa Clara CA, Sunnyvale CA

**6. Chicago (805 lines) - 1 city (custom)**
- **Custom scraper** for Chicago's unique Legistar instance
- **API-based:** Uses Legistar API with Chicago-specific pagination
- **Item extraction:** Similar to standard Legistar but with custom filters
- **Matter tracking:** Chicago uses numeric IDs + file numbers
- **Procedural filtering:** Filters "Call to Order", "Adjournment", etc.
- **Special case:** High volume (1000+ items/meeting) requires batching

**7. eScribe (522 lines) - ~20 cities**
- **HTML scraping:** Meeting list -> Agenda=Merged view for items
- **Item extraction:** Via `.AgendaItemContainer` elements with unique IDs
- **Matter tracking:** Extracts case numbers from title prefixes (BOA-0039-2025, etc.)
- **Per-item attachments:** `FileStream.ashx?DocumentId=` links per item
- **Section hierarchy:** Nested containers with indentation
- **City examples:** Raleigh NC, Canadian cities (supports French language)

---

### Monolithic Adapters (4 adapters - 12% of cities)

These adapters fetch **PDF packet URLs only** (no structured items). Meetings are processed with comprehensive LLM summarization.

**8. CivicClerk (134 lines) - ~30 cities**
- **HTML scraping:** Agenda calendar -> packet PDF links
- **No item extraction:** Only stores `packet_url`
- **PDF structure:** Single PDF with all agenda items (no separation)
- **City examples:** Multiple small CA cities

**9. CivicPlus (436 lines) - ~25 cities**
- **HTML scraping:** Meeting list -> packet PDF links
- **No item extraction:** Monolithic PDFs
- **Quirks:** Some cities hide PDFs behind JavaScript modals
- **City examples:** Various mid-size cities

**10. Berkeley (328 lines) - 1 city (custom)**
- **Custom scraper** for Berkeley CA's unique system
- **Monolithic:** Fetches packet PDFs only
- **Special handling:** Berkeley uses custom CMS with non-standard structure

**11. Menlo Park (206 lines) - 1 city (custom)**
- **Custom scraper** for Menlo Park CA
- **Monolithic:** Packet URLs only
- **Historical:** One of the first adapters (predates item-level pattern)

---

## HTML Parsing Architecture

**Separation of Concerns:** Adapters fetch data, Parsers extract structure.

### Parser Pattern

```python
# vendors/adapters/parsers/legistar_parser.py
class LegistarParser:
    """Parse Legistar HTML agenda tables into structured items."""

    @staticmethod
    def parse_agenda_items(html: str, meeting_id: str) -> List[Dict]:
        """
        Extract items from Legistar HTML table.

        Returns:
            [
                {
                    "title": "Ordinance 2025-001",
                    "matter_file": "BL2025-1005",
                    "matter_id": "251041",
                    "matter_type": "Bill",
                    "sequence": 1,
                    "agenda_url": "https://...",
                    "attachments": [{"url": "...", "name": "...", "type": "pdf"}]
                },
                ...
            ]
        """
        soup = BeautifulSoup(html, "html.parser")
        items = []

        # Find agenda table
        table = soup.find("table", {"id": "ctl00_ContentPlaceHolder1_gridMain_ctl00"})
        if not table:
            return []

        for row in table.find_all("tr", class_="rgRow"):
            # Extract title
            title_cell = row.find("td", class_="rgSorted")
            title = title_cell.get_text(strip=True) if title_cell else ""

            # Extract matter file
            file_cell = row.find("td", {"data-title": "File #"})
            matter_file = file_cell.get_text(strip=True) if file_cell else None

            # Extract attachments
            attachment_links = row.find_all("a", href=re.compile(r"Attachments/.*\.pdf"))
            attachments = [...]

            items.append({...})

        return items
```

**Why separate parsers?**
- **Vendor updates:** HTML changes → update parser only, adapter unchanged
- **Testing:** Can test parsing logic independently
- **Reusability:** Same parser works across multiple cities using same vendor
- **Clarity:** Adapter focuses on HTTP/retry, parser focuses on DOM traversal

---

## Shared Utilities

### Item Filtering (vendors/utils/item_filters.py)

**Procedural item detection:** Identifies agenda items that don't need LLM summarization.

```python
def is_procedural_item(title: str) -> bool:
    """
    Detect procedural items (Call to Order, Adjournment, etc.).

    These items don't need summarization:
    - "Call to Order"
    - "Roll Call"
    - "Approval of Minutes"
    - "Public Comment"
    - "Adjournment"
    """
    title_lower = title.lower().strip()

    procedural_patterns = [
        r"^call to order$",
        r"^roll call$",
        r"^approval of (?:the )?minutes?$",
        r"^(?:public|oral) comments?$",
        r"^adjournment$",
        r"^recess$",
    ]

    return any(re.search(pattern, title_lower) for pattern in procedural_patterns)
```

**Deployed across:** All 7 item-level adapters (Legistar, PrimeGov, Granicus, IQM2, NovusAgenda, Chicago, eScribe)

**Impact:** Saves ~5-10% of LLM costs by skipping procedural items

### Attachment Deduplication (vendors/utils/attachments.py)

**Hash-based deduplication:** Prevents processing same PDF multiple times.

```python
def compute_attachment_hash(attachments: List[Dict]) -> str:
    """
    Compute stable hash of attachment URLs.

    Used for matters-first deduplication:
    - Matter appears in 3 meetings
    - If attachment URLs unchanged → reuse canonical summary
    - If attachment URLs changed → re-process matter
    """
    # Sort URLs for stable hash
    urls = sorted([att["url"] for att in attachments])
    combined = "|".join(urls)
    return hashlib.sha256(combined.encode()).hexdigest()[:16]
```

**Deployed in:** `database/services/meeting_ingestion.py` for matters-first processing

**Impact:** Prevents redundant LLM calls when matter appears in multiple meetings

---

## Rate Limiting Strategy

**Vendor-aware rate limiting** prevents overwhelming civic tech platforms.

```python
# vendors/rate_limiter.py
class VendorRateLimiter:
    """
    Per-vendor rate limiting with polite defaults.

    Different vendors have different tolerance:
    - Legistar API: 60 req/min (official rate limit)
    - PrimeGov HTML: 10 req/min (polite scraping)
    - Granicus API: 30 req/min (undocumented, conservative)
    """

    VENDOR_LIMITS = {
        "legistar": 60,    # Official API rate limit
        "primegov": 10,    # Polite HTML scraping
        "granicus": 30,    # Conservative (API undocumented)
        "iqm2": 15,        # Polite HTML scraping
        "novusagenda": 10, # Polite HTML scraping
        "default": 10,     # Default for custom adapters
    }
```

**Backoff strategy:** Exponential backoff on 429/503 responses (1s → 2s → 4s → 8s)

**Polite crawling:** Respects robots.txt when scraping HTML (though civic data is public)

---

## Vendor Factory (factory.py)

**Adapter dispatcher:** Maps vendor name → async adapter class.

```python
# vendors/factory.py
from vendors.adapters.legistar_adapter_async import AsyncLegistarAdapter
from vendors.adapters.primegov_adapter_async import AsyncPrimeGovAdapter
# ... all 11 async adapters

VENDOR_ADAPTERS = {
    "legistar": AsyncLegistarAdapter,
    "primegov": AsyncPrimeGovAdapter,
    "granicus": AsyncGranicusAdapter,
    "iqm2": AsyncIQM2Adapter,
    "novusagenda": AsyncNovusAgendaAdapter,
    "escribe": AsyncEscribeAdapter,
    "civicclerk": AsyncCivicClerkAdapter,
    "civicplus": AsyncCivicPlusAdapter,
    "berkeley": AsyncBerkeleyAdapter,
    "chicago": AsyncChicagoAdapter,
    "menlopark": AsyncMenloParkAdapter,
}

def get_async_adapter(vendor: str, city_slug: str, **kwargs) -> AsyncBaseAdapter:
    """
    Get async adapter instance for vendor.

    Args:
        vendor: Vendor identifier (e.g., "legistar", "primegov")
        city_slug: City identifier (e.g., "nyc", "losangeles")
        **kwargs: Additional arguments (api_token, etc.)

    Returns:
        Async adapter instance

    Raises:
        VendorError: If vendor not supported
    """
    adapter_class = VENDOR_ADAPTERS.get(vendor)
    if not adapter_class:
        raise VendorError(f"Unsupported vendor: {vendor}")

    return adapter_class(city_slug=city_slug, **kwargs)
```

**Usage:**
```python
# In pipeline/fetcher.py
from vendors.factory import get_async_adapter

adapter = get_async_adapter(vendor="legistar", city_slug="nyc")
meetings = await adapter.fetch_meetings(days_back=7, days_forward=14)
```

---

## Meeting Validation (validator.py)

**Pydantic validation** ensures vendor data meets schema requirements.

```python
# vendors/validator.py
from pydantic import BaseModel, validator

class MeetingSchema(BaseModel):
    """Schema for meeting data from vendors."""
    id: str
    title: str
    date: datetime
    agenda_url: Optional[str] = None
    packet_url: Optional[str] = None

    @validator('agenda_url', 'packet_url')
    def validate_at_least_one_url(cls, v, values):
        """Meeting must have either agenda_url or packet_url."""
        if not v and not values.get('packet_url') and not values.get('agenda_url'):
            raise ValueError("Meeting must have at least one URL")
        return v

def validate_meeting(meeting_data: Dict) -> Meeting:
    """
    Validate meeting data from vendor.

    Raises:
        ValidationError: If data doesn't match schema
    """
    schema = MeetingSchema(**meeting_data)
    return Meeting.from_dict(schema.dict())
```

**Validation points:**
1. **After fetch:** Adapter validates data before returning
2. **Before storage:** `meeting_ingestion.py` validates before DB insert
3. **API response:** Server validates before sending to frontend

---

## Adding a New Vendor Adapter

**Step-by-step guide for adding support for a new civic tech platform.**

### 1. Create Async Adapter Class

```python
# vendors/adapters/newvendor_adapter_async.py
from vendors.adapters.base_adapter_async import AsyncBaseAdapter, logger
from typing import List, Dict, Any
import asyncio

class AsyncNewVendorAdapter(AsyncBaseAdapter):
    """Async adapter for NewVendor civic tech platform."""

    def __init__(self, city_slug: str):
        super().__init__(city_slug, vendor="newvendor")
        self.base_url = f"https://{city_slug}.newvendor.com"

    async def fetch_meetings(self, days_back: int = 7, days_forward: int = 14) -> List[Dict[str, Any]]:
        """
        Fetch meetings from NewVendor platform (async).

        Returns:
            [
                {
                    "meeting_id": "meeting_12345",
                    "title": "City Council Meeting",
                    "start": "2025-11-20T19:00:00",
                    "agenda_url": "https://...",  # If available
                    "packet_url": "https://...",  # Fallback
                    "items": [...]  # If item-level
                },
                ...
            ]
        """
        # 1. Construct URL for meeting list
        url = f"{self.base_url}/meetings"

        # 2. Fetch with async retry
        response = await self._get(url)
        html = await response.text()

        # 3. Parse response (CPU-bound, run in thread pool)
        meetings = await asyncio.to_thread(self._parse_meetings, html)

        # 4. Fetch details concurrently
        detail_tasks = [self._fetch_meeting_details(m["meeting_id"]) for m in meetings]
        details = await asyncio.gather(*detail_tasks, return_exceptions=True)

        for meeting, detail in zip(meetings, details):
            if not isinstance(detail, Exception):
                meeting.update(detail)

        return meetings

    async def _fetch_meeting_details(self, meeting_id: str) -> Dict[str, Any]:
        """Fetch agenda items for a meeting (async)."""
        url = f"{self.base_url}/meetings/{meeting_id}/items"
        response = await self._get(url)
        html = await response.text()
        items = await asyncio.to_thread(self._parse_items, html)
        return {"items": items, "agenda_url": url}

    def _parse_meetings(self, html: str) -> List[Dict]:
        """Parse meeting list (sync, run in thread pool)."""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        # Extract meetings...
        ...

    def _parse_items(self, html: str) -> List[Dict]:
        """Parse agenda items (sync, run in thread pool)."""
        # If complex, extract to vendors/adapters/parsers/newvendor_parser.py
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

### 3. Add Cities to Database

```python
# In pipeline/conductor.py or admin script
db.add_city(
    banana="examplecityCA",
    name="Example City",
    state="CA",
    vendor="newvendor",
    city_slug="examplecity",  # Used in adapter URL construction
    timezone="America/Los_Angeles",
)
```

### 4. Test Adapter

```bash
# Sync one city to verify
python -m pipeline.conductor sync-city examplecityCA --force
```

### 5. Monitor & Iterate

- Check logs for errors: `tail -f logs/engagic.log | grep newvendor`
- Verify data in database: `sqlite3 data/engagic.db "SELECT * FROM meetings WHERE banana = 'examplecityCA'"`
- Adjust parser if HTML structure varies across cities

---

## Debugging Adapters

### Common Issues

**1. No meetings returned**
- Check date range (some vendors only show future meetings)
- Verify URL construction (city_slug might be case-sensitive)
- Check HTTP response (might be 404, 403, or 500)

```python
# Add debug logging
self.logger.debug("fetching meetings", url=url, date_range=f"{start_date} to {end_date}")
response = self._get_with_retry(url)
self.logger.debug("response received", status_code=response.status_code, content_length=len(response.text))
```

**2. Parsing failures**
- HTML structure changed (vendor updated their site)
- BeautifulSoup selectors too specific
- Missing null checks on DOM elements

```python
# Defensive parsing
title_elem = row.find("td", class_="title")
title = title_elem.get_text(strip=True) if title_elem else "Untitled"
```

**3. Rate limiting (429 errors)**
- Reduce requests per minute in `rate_limiter.py`
- Add delays between requests: `time.sleep(0.5)`
- Check if vendor has official rate limit documentation

**4. Authentication required**
- Some vendors require API tokens
- Pass via `api_token` kwarg in adapter constructor
- Store in environment variable (`LEGISTAR_API_TOKEN`, etc.)

---

## Performance Metrics

**Adapter efficiency** (average across all vendors):

| Metric | Value | Notes |
|--------|-------|-------|
| Success rate | 94% | Failures mostly due to vendor downtime |
| Avg response time | 2.3s | Includes retry attempts |
| Meetings/city/sync | 8.2 | Depends on city size and meeting frequency |
| Items/meeting (item-level) | 12.4 | Avg for structured adapters |

**Bottlenecks:**
- HTML parsing (BeautifulSoup): ~200ms/page (negligible)
- HTTP requests: ~1-3s/request (vendor response time)
- Rate limiting: Adds 0-60s/city (depending on vendor limits)

**Optimization opportunities:**
- Parallel fetching (currently sequential per city)
- Cache meeting lists (reduce re-fetching unchanged data)
- Batch API requests (some vendors support this)

---

## Testing

**Unit tests:** `tests/test_vendors.py`

```python
# Test adapter parsing with fixture HTML
def test_legistar_parse_items():
    html = load_fixture("legistar_agenda.html")
    parser = LegistarParser()
    items = parser.parse_agenda_items(html, meeting_id="test_123")

    assert len(items) == 15
    assert items[0]["title"] == "Ordinance 2025-001"
    assert items[0]["matter_file"] == "BL2025-1005"
```

**Integration tests:** `tests/integration/test_vendor_adapters.py`

```python
# Test live adapter (uses VCR.py to record HTTP)
@vcr.use_cassette("legistar_nyc_meetings.yaml")
def test_legistar_fetch_meetings():
    adapter = LegistarAdapter(city_slug="nyc")
    meetings = adapter.fetch_meetings(start_date, end_date)

    assert len(meetings) > 0
    assert all(m["agenda_url"] or m["packet_url"] for m in meetings)
```

**Manual testing:**
```bash
# Sync single city
python -m pipeline.conductor sync-city paloaltoCA --force

# Check results
sqlite3 data/engagic.db "SELECT COUNT(*) FROM meetings WHERE banana = 'paloaltoCA'"
```

---

## Future Work

**Expansion:**
- [ ] Add support for Municode (50+ potential cities)
- [ ] Add support for Novus (different from NovusAgenda)
- [ ] Improve Granicus item extraction (currently only 200/467 cities)

**Optimization:**
- [ ] Parallel city syncing (process multiple cities concurrently)
- [ ] Incremental updates (only fetch new meetings since last sync)
- [ ] API v2: Vendors provide structured JSON (reduce HTML parsing)

**Reliability:**
- [ ] Health checks for each vendor (detect when vendor site is down)
- [ ] Adapter versioning (track when HTML structure changes)
- [ ] Fallback strategies (try HTML if API fails, vice versa)

---

**See Also:**
- [pipeline/README.md](../pipeline/README.md) - How adapters integrate with processing pipeline
- [database/README.md](../database/README.md) - How meeting data is stored
- [VISION.md](../docs/VISION.md) - Product roadmap and vendor expansion plans

**Last Updated:** 2025-12-03 (Line counts updated, added extractors/council_member_extractor.py)
