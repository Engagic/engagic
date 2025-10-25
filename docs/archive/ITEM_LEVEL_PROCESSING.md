# Item-Level Attachment Processing

**Branch:** `dev-item-level-attachments`
**Status:** Phase 4 Complete (Full Pipeline Working) | Testing In Progress
**Date:** 2025-01-25

---

## Vision

### Problem Statement
Current architecture processes entire meetings as monolithic blobs:
- Board of Supervisors meeting: 30 agenda items × 20 attachments = 600+ PDFs
- Single bond financing item can have 21 attachments (indentures, memos, agreements)
- Processing 500+ page packets causes VPS crashes
- No granular topic tracking or item-level summaries

### Solution Architecture
**Item-granular processing pipeline:**

```
Meeting → Agenda Items → Filter Attachments → Process Per-Item → Combine
```

1. **Fetch item structure** from vendor API (Legistar: EventItems → Matters → Attachments)
2. **Filter attachments** by relevance (legislative summaries, staff memos vs. indenture drafts)
3. **Process each item** separately (10-50 pages vs. 500 pages)
4. **Extract topics** per item (e.g., "affordable housing bonds", "zoning reform")
5. **Combine summaries** into coherent meeting overview (avoid repetition)

### Benefits
- **Smaller processing units:** 10-50 pages per item (manageable for VPS)
- **Better failure isolation:** If bond item fails, others still process
- **Granular topic tracking:** Know which items discuss what
- **Selective processing:** Skip public comment packets, prioritize legislative summaries
- **Future UX:** Display item-level summaries, navigate by topic

---

## Implementation Progress

### ✅ Phase 1: Legistar API Integration

**File:** `backend/adapters/legistar_adapter.py`

**Added Methods:**
- `fetch_event_items(event_id: int) -> List[Dict]`
  - Calls `/events/{id}/eventitems` endpoint
  - For each item with MatterId, fetches `/matters/{id}/attachments`
  - Returns all items (even without attachments, for display)

- Modified `fetch_meetings()` to always include items
  - Legistar always has item structure, no boolean flag needed
  - Returns: `{meeting_id, title, start, packet_url, items: [...]}`

**Item Structure:**
```python
{
    'item_id': '118765',
    'title': 'AN ORDINANCE relating to City employment...',
    'sequence': 10,
    'matter_id': '16556',
    'attachments': [
        {'name': 'Central Staff Memo', 'url': '...', 'type': 'pdf'},
        {'name': 'Fiscal Note', 'url': '...', 'type': 'doc'}
    ]
}
```

**Validated:**
- Seattle City Council: 18 items, 2 with attachments (4 + 1 files)
- Attachments correctly typed (PDF vs DOC)

---

### ✅ Phase 2: Database Schema

**File:** `backend/database/unified_db.py`

**Added Dataclass:**
```python
@dataclass
class AgendaItem:
    id: str                     # Vendor item ID
    meeting_id: str             # FK to meetings.id
    title: str
    sequence: int               # Order in agenda
    attachments: List[Any]      # Attachment metadata as JSON (flexible: URLs, dicts with name/url/type, page ranges, etc.)
    summary: Optional[str]      # Item-level summary
    topics: Optional[List[str]] # Extracted topics
    created_at: Optional[datetime]
```

**Added Table:**
```sql
CREATE TABLE agenda_items (
    id TEXT PRIMARY KEY,
    meeting_id TEXT NOT NULL,
    title TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    attachments TEXT,           -- JSON array
    summary TEXT,
    topics TEXT,                -- JSON array
    created_at TIMESTAMP,
    FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE
);
```

**Added Methods:**
- `store_agenda_items(meeting_id, items: List[AgendaItem]) -> int`
- `get_agenda_items(meeting_id) -> List[AgendaItem]`
- `update_agenda_item(item_id, summary, topics) -> None`

**Validated:**
- Table exists in `data/engagic.db`
- Foreign key constraints working
- JSON serialization/deserialization working

---

### ✅ Phase 3: Item-Level Processing

**File:** `backend/core/processor.py`

**Added Methods:**
1. **`process_agenda_item(item_data: Dict, city_banana: str) -> Dict`**
   - Downloads item attachments (filters to PDFs only)
   - Extracts text using Tier 1 (PyPDF2 + Gemini fallback)
   - Generates summary with structured prompt asking for:
     - 2-3 sentence summary of the agenda item
     - 1-3 main topics (comma-separated)
   - Uses Flash-Lite for small items (<200K chars), Flash for larger
   - Returns: `{'success': bool, 'summary': str, 'topics': List[str], 'processing_time': float, 'attachments_processed': int}`

2. **`_summarize_agenda_item(item_title: str, text: str) -> tuple[str, List[str]]`**
   - Internal method for Gemini API call
   - Parses response to extract `SUMMARY:` and `TOPICS:` lines
   - Returns tuple of (summary, topics_list)

3. **`combine_item_summaries(item_summaries: List[Dict], meeting_title: str) -> str`**
   - Simple concatenation strategy (no additional LLM call for cost savings)
   - Formats as: Meeting title + per-item sections with title, summary, and topics
   - Returns concatenated string

**Processing Flow:**
- If item has no PDF attachments → skip processing, return success with empty result
- If all attachments fail to extract → return failure with error message
- If some attachments succeed → combine their text and process
- Topics extracted via structured prompt parsing

---

### ✅ Phase 4: Conductor Integration

**File:** `backend/services/conductor.py` (renamed from `background_processor.py`)

**Architectural Changes:**
- Renamed `BackgroundProcessor` → `Conductor` (orchestrates the entire pipeline)
- Updated all references in `daemon.py` and function names

**Sync-Time Integration:**
- Modified `_sync_city()` to detect `items` field in meetings
- When Legistar meetings include items:
  - Convert adapter items to `AgendaItem` objects
  - Store via `db.store_agenda_items()`
  - Composite ID format: `{meeting_id}_{item_id}`
  - Attachments stored as full JSON metadata (name/url/type dicts)

**Processing-Time Integration:**
- Added `_process_meeting_with_items(meeting, agenda_items)` method
- Modified `_process_meeting_summary()` to check for agenda items:
  - **If items exist:** Call `_process_meeting_with_items()` for item-level processing
  - **If no items:** Fall back to monolithic `process_agenda_with_cache()`

**Item Processing Pipeline:**
1. Load agenda items from DB
2. For each item with attachments:
   - Check if already processed (skip if summary exists)
   - Call `processor.process_agenda_item()`
   - Update item in DB with summary/topics
3. Combine all processed item summaries
4. Update meeting.summary with combined result
5. Set processing_method to `item_level_{N}_items`

---

## Future Enhancements (Phase 5+)

### Attachment Filtering Baskets
**High-value attachments** (prioritize):
- Legislative summaries/digests ("Leg Dig Ver1")
- Staff reports/memos ("HSS Memo", "OPF Memo")
- Fiscal impact statements ("Fiscal Note")
- Committee reports (WARNING: 100+ pages, needs size check)

**Low-value attachments** (skip):
- Internal bureaucracy ("Meet and Confer Det", "Presidential Transfer")
- Draft legal documents (15 indenture drafts for bond item)
- Public comments (can be 80% of packet, often available separately)

**Implementation:**
- `backend/adapters/attachment_filters.py`
- Pattern matching on attachment names
- Configurable max count (5 per item) + max size (50 pages)
- Ranking: legislative summaries > staff memos > fiscal notes > other

### Topic Aggregation
- `meeting_topics` table: track topics with relevance scores
- Enable search: "Show me all meetings discussing affordable housing"
- B2B tenant keyword tracking (Phase 5 multi-tenancy)

### Other Vendors
- Granicus: May have monolithic packets (use old deep_scrape)
- CivicPlus: HTML scraping, not API (hybrid approach)
- PrimeGov: Check if API supports item structure

---

## Technical Notes

### Legistar API Structure
```
Event (Meeting)
  └─ EventItems (Agenda Items)
       └─ Matter (Legislation)
            └─ MatterAttachments (PDFs/DOCs)
```

- Not all items have Matters (procedural items: "CALL TO ORDER")
- We store all items, only process those with attachments
- Attachment URLs: `https://legistar2.granicus.com/.../attachments/{guid}.pdf`

### Processing Strategy
**Before (monolithic):**
- 1 meeting → 500 pages → 1 summary → VPS crash

**After (item-granular):**
- 1 meeting → 23 items → 5-10 with attachments → 10-50 pages each → 23 item summaries → 1 combined summary

### Data Model
- **Meeting** stores main packet URL (full agenda PDF) + combined summary
- **AgendaItems** store per-item attachment metadata (full dicts with name/url/type)
  - Flexible format supports both:
    - **Legistar:** `[{'name': 'Fiscal Note', 'url': '...', 'type': 'pdf'}]`
    - **PrimeGov (future):** `[{'name': 'Main Packet', 'url': '...', 'page_range': '1-40'}]`
- Both have summaries (item-level stored in `agenda_items`, meeting-level in `meetings`)
- Topics stored as JSON arrays in `agenda_items.topics`

### Responsibilities By Layer
**Adapters (Sync Time):**
- Extract item structure in vendor-specific format
- Return flexible attachment metadata (adapters decide structure)

**Database:**
- Store raw metadata as JSON (no interpretation)
- Provide CRUD for AgendaItem objects

**Processor (Processing Time):**
- Parse attachment metadata (handle URLs, page ranges, etc.)
- Download/extract/summarize content
- Return updated AgendaItem objects

**Conductor (Orchestration):**
- Coordinate sync → storage → processing → DB updates
- Handle fallback to monolithic processing for non-item vendors

---

**Last Updated:** 2025-01-25
**Next Milestone:** End-to-end testing with production Legistar data
