# Vendors Module - Civic Tech Platform Adapters

**Fetch meeting data from 11 civic tech platforms.** Unified adapter architecture with vendor-specific parsers and shared utilities.

**Last Updated:** November 20, 2025

---

## Overview

The vendors module provides adapters for fetching meeting data from civic technology platforms used by local governments. Each adapter implements a common interface (`BaseAdapter`) while handling vendor-specific quirks in HTML parsing, API integration, and data extraction.

**Architecture Pattern:** BaseAdapter + Vendor-Specific Parsers + Shared Utilities

```
vendors/
├── adapters/           # 11 vendor-specific adapters
│   ├── base_adapter.py         # Shared HTTP/date/retry logic (398 lines)
│   ├── legistar_adapter.py     # Legistar (API + HTML) - 980 lines
│   ├── primegov_adapter.py     # PrimeGov (HTML) - 326 lines
│   ├── granicus_adapter.py     # Granicus (API + HTML) - 584 lines
│   ├── iqm2_adapter.py         # IQM2 (HTML) - 343 lines
│   ├── novusagenda_adapter.py  # NovusAgenda (HTML) - 410 lines
│   ├── escribe_adapter.py      # eScribe (HTML) - 261 lines
│   ├── civicclerk_adapter.py   # CivicClerk (monolithic) - 192 lines
│   ├── civicplus_adapter.py    # CivicPlus (monolithic) - 168 lines
│   ├── custom/
│   │   ├── berkeley_adapter.py     # Berkeley custom (monolithic) - 156 lines
│   │   ├── chicago_adapter.py      # Chicago custom (item-level) - 447 lines
│   │   └── menlopark_adapter.py    # Menlo Park custom (monolithic) - 134 lines
│   └── parsers/        # Vendor-specific HTML parsing (4 parsers)
│       ├── legistar_parser.py      # Legistar HTML tables - 246 lines
│       ├── primegov_parser.py      # PrimeGov HTML tables - 187 lines
│       ├── granicus_parser.py      # Granicus HTML tables - 215 lines
│       └── novusagenda_parser.py   # NovusAgenda HTML - 212 lines
├── utils/              # Shared utilities
│   ├── filtering.py    # Item filtering (procedural detection)
│   └── deduplication.py # Attachment deduplication
├── factory.py          # get_adapter() dispatcher - 65 lines
├── rate_limiter.py     # Vendor-aware rate limiting - 49 lines
├── validator.py        # Meeting validation - 265 lines
└── schemas.py          # Pydantic schemas for vendor data

**Total:** ~6,556 lines
```

---

## Architecture

### BaseAdapter Pattern

All vendor adapters inherit from `BaseAdapter`, which provides:
- **HTTP client** with retry logic and timeout handling
- **Date parsing** utilities (handles various formats)
- **Rate limiting** integration
- **Error handling** with context (vendor, city, URL)
- **Common interface** (`fetch_meetings()`, `fetch_meeting_details()`)

```python
# vendors/adapters/base_adapter.py
class BaseAdapter:
    def __init__(self, city_slug: str, http_client: Optional[httpx.Client] = None):
        self.city_slug = city_slug
        self.http_client = http_client or httpx.Client(timeout=30.0)
        self.logger = get_logger(__name__).bind(vendor=self.__class__.__name__)

    def fetch_meetings(self, start_date: datetime, end_date: datetime) -> List[Meeting]:
        """Fetch meetings for date range. MUST be implemented by subclass."""
        raise NotImplementedError

    def _get_with_retry(self, url: str, retries: int = 3) -> httpx.Response:
        """HTTP GET with exponential backoff retry."""
        # Shared retry logic

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date from various vendor formats."""
        # Handles: "11/20/2025", "2025-11-20", "Nov 20, 2025", etc.
```

---

## Vendor Adapters

### Item-Level Adapters (6 adapters - 86% of cities)

These adapters extract **structured agenda items** from HTML agendas or APIs. Items are stored separately with `matter_id`, `matter_file`, titles, and PDF links.

**1. Legistar (980 lines) - 110 cities**
- **Dual mode:** API-first, fallback to HTML scraping
- **API:** `/events.json` endpoint with structured JSON
- **HTML:** Calendar view → meeting detail pages → item tables
- **Item extraction:**
  - API: Direct JSON parsing of `EventItems` array
  - HTML: `legistar_parser.py` parses `<tr>` tables with `data-id` attributes
- **Matter tracking:** `File #` column → `matter_file`, `EventItemMatterId` → `matter_id`
- **PDF links:** Attachment URLs from `EventItemAgendaFile` or HTML hrefs
- **City examples:** NYC, Los Angeles, San Francisco, Seattle, Boston

**2. PrimeGov (326 lines) - 64 cities**
- **HTML scraping only:** Agenda list → detail pages → item tables
- **Parser:** `primegov_parser.py` handles `<table class="agenda">` structure
- **Item extraction:**
  - Title from `<td class="title">` or first `<td>`
  - Matter from `<td class="file">` or pattern matching in title
  - PDF links from `<a href="/agendas/...">` in row
- **Quirks:** Some cities use non-standard table classes (handled via selectors)
- **City examples:** Austin TX, Portland OR, San Diego CA

**3. Granicus (584 lines) - 467 cities (200+ with item extraction)**
- **Hybrid:** API for meeting list, HTML scraping for items
- **API:** `/meetings` JSON endpoint for meeting metadata
- **HTML:** Meeting detail pages → `granicus_parser.py` parses agenda tables
- **Item extraction:**
  - Title from `<div class="item-title">` or `<h3>` tags
  - Matter from `<span class="item-number">` or title prefixes
  - PDF links from `<a class="attachment">` or inline PDFs
- **Coverage:** Not all Granicus cities have structured agendas (fallback to monolithic)
- **City examples:** Sacramento CA, Denver CO, Phoenix AZ

**4. IQM2 (343 lines) - 45 cities**
- **HTML scraping:** Agenda calendar → detail pages → item tables
- **No dedicated parser:** Inline parsing in adapter (could extract to parser)
- **Item extraction:**
  - Title from `<div class="agenda-item-title">`
  - Matter from `<span class="item-number">` or title prefix
  - PDF links from `<a class="pdf-link">`
- **City examples:** Fremont CA, Alameda CA

**5. NovusAgenda (410 lines) - 38 cities**
- **HTML scraping:** Meeting list → detail → `novusagenda_parser.py`
- **Parser:** Handles `<table id="agenda">` with rowspan/colspan complexity
- **Item extraction:**
  - Title from `<td class="title">` (may span multiple rows)
  - Matter from `<td class="number">` or pattern in title
  - PDF attachments from nested `<ul class="attachments">`
- **Quirks:** Heavy use of rowspan/colspan requires careful DOM traversal
- **City examples:** Santa Clara CA, Sunnyvale CA

**6. Chicago (447 lines) - 1 city (custom)**
- **Custom scraper** for Chicago's unique Legistar instance
- **API-based:** Uses Legistar API with Chicago-specific pagination
- **Item extraction:** Similar to standard Legistar but with custom filters
- **Matter tracking:** Chicago uses numeric IDs + file numbers
- **Procedural filtering:** Filters "Call to Order", "Adjournment", etc.
- **Special case:** High volume (1000+ items/meeting) requires batching

---

### Monolithic Adapters (5 adapters - 14% of cities)

These adapters fetch **PDF packet URLs only** (no structured items). Meetings are processed with comprehensive LLM summarization.

**7. CivicClerk (192 lines) - ~30 cities**
- **HTML scraping:** Agenda calendar → packet PDF links
- **No item extraction:** Only stores `packet_url`
- **PDF structure:** Single PDF with all agenda items (no separation)
- **City examples:** Multiple small CA cities

**8. CivicPlus (168 lines) - ~25 cities**
- **HTML scraping:** Meeting list → packet PDF links
- **No item extraction:** Monolithic PDFs
- **Quirks:** Some cities hide PDFs behind JavaScript modals
- **City examples:** Various mid-size cities

**9. eScribe (261 lines) - ~20 cities**
- **HTML/API hybrid:** Meeting list API → HTML packet links
- **No item extraction:** Single PDF per meeting
- **City examples:** Canadian cities (supports French language)

**10. Berkeley (156 lines) - 1 city (custom)**
- **Custom scraper** for Berkeley CA's unique system
- **Monolithic:** Fetches packet PDFs only
- **Special handling:** Berkeley uses custom CMS with non-standard structure

**11. Menlo Park (134 lines) - 1 city (custom)**
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

### Item Filtering (vendors/utils/filtering.py)

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

**Deployed across:** All 6 item-level adapters (Legistar, PrimeGov, Granicus, IQM2, NovusAgenda, Chicago)

**Impact:** Saves ~5-10% of LLM costs by skipping procedural items

### Attachment Deduplication (vendors/utils/deduplication.py)

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

**Adapter dispatcher:** Maps vendor name → adapter class.

```python
# vendors/factory.py
from vendors.adapters import (
    LegistarAdapter,
    PrimeGovAdapter,
    GranicusAdapter,
    IQM2Adapter,
    NovusAgendaAdapter,
    EScribeAdapter,
    CivicClerkAdapter,
    CivicPlusAdapter,
)
from vendors.adapters.custom import BerkeleyAdapter, ChicagoAdapter, MenloParkAdapter

VENDOR_ADAPTERS = {
    "legistar": LegistarAdapter,
    "primegov": PrimeGovAdapter,
    "granicus": GranicusAdapter,
    "iqm2": IQM2Adapter,
    "novusagenda": NovusAgendaAdapter,
    "escribe": EScribeAdapter,
    "civicclerk": CivicClerkAdapter,
    "civicplus": CivicPlusAdapter,
    "berkeley": BerkeleyAdapter,
    "chicago": ChicagoAdapter,
    "menlopark": MenloParkAdapter,
}

def get_adapter(vendor: str, city_slug: str, **kwargs) -> BaseAdapter:
    """
    Get adapter instance for vendor.

    Args:
        vendor: Vendor identifier (e.g., "legistar", "primegov")
        city_slug: City identifier (e.g., "nyc", "losangeles")
        **kwargs: Additional arguments (api_token, etc.)

    Returns:
        Adapter instance

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
from vendors.factory import get_adapter

adapter = get_adapter(vendor="legistar", city_slug="nyc")
meetings = adapter.fetch_meetings(start_date, end_date)
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

### 1. Create Adapter Class

```python
# vendors/adapters/newvendor_adapter.py
from vendors.adapters.base_adapter import BaseAdapter
from typing import List
from datetime import datetime

class NewVendorAdapter(BaseAdapter):
    """Adapter for NewVendor civic tech platform."""

    def __init__(self, city_slug: str, **kwargs):
        super().__init__(city_slug, **kwargs)
        self.base_url = f"https://{city_slug}.newvendor.com"

    def fetch_meetings(self, start_date: datetime, end_date: datetime) -> List[Dict]:
        """
        Fetch meetings from NewVendor platform.

        Returns:
            [
                {
                    "id": "meeting_12345",
                    "title": "City Council Meeting",
                    "date": datetime(2025, 11, 20, 19, 0),
                    "agenda_url": "https://...",  # If available
                    "packet_url": "https://...",  # Fallback
                },
                ...
            ]
        """
        # Implementation:
        # 1. Construct URL for meeting list
        url = f"{self.base_url}/meetings?start={start_date}&end={end_date}"

        # 2. Fetch with retry
        response = self._get_with_retry(url)

        # 3. Parse response (JSON or HTML)
        meetings = self._parse_meetings(response.text)

        # 4. Fetch details if needed
        for meeting in meetings:
            details = self._fetch_meeting_details(meeting["id"])
            meeting.update(details)

        return meetings

    def _fetch_meeting_details(self, meeting_id: str) -> Dict:
        """Fetch agenda items for a meeting (if item-level)."""
        # If NewVendor provides structured items:
        url = f"{self.base_url}/meetings/{meeting_id}/items"
        response = self._get_with_retry(url)
        items = self._parse_items(response.text)

        return {
            "items": items,  # List of agenda items
            "agenda_url": url,
        }

        # If NewVendor only provides PDF packets:
        # return {"packet_url": "https://..."}

    def _parse_meetings(self, html: str) -> List[Dict]:
        """Parse meeting list from HTML/JSON."""
        # Use BeautifulSoup for HTML or json.loads() for JSON
        ...

    def _parse_items(self, html: str) -> List[Dict]:
        """Parse agenda items from detail page."""
        # If complex, extract to vendors/adapters/parsers/newvendor_parser.py
        ...
```

### 2. Register in Factory

```python
# vendors/factory.py
from vendors.adapters.newvendor_adapter import NewVendorAdapter

VENDOR_ADAPTERS = {
    ...
    "newvendor": NewVendorAdapter,
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
# Sync one meeting to verify
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

**Last Updated:** 2025-11-20 (Initial documentation)
