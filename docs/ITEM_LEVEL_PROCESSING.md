# Item-Level Attachment Processing

**Branch:** `dev-item-level-attachments`
**Status:** Phase 2 Complete (Database Schema) | Phase 3 In Progress
**Date:** 2025-01-23

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
    attachments: List[str]      # PDF URLs as JSON
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

**Validated:**
- Table exists in `data/engagic.db`
- Foreign key constraints working
- JSON serialization/deserialization working

---

## Next Steps

### 🔄 Phase 3: Item-Level Processing

**File:** `backend/core/processor.py`

**Add Methods:**
1. `process_agenda_item(item_data: Dict, city_banana: str) -> Dict`
   - Downloads item attachments (configurable limit, PDFs only)
   - Extracts text (Tier 1: PyPDF2 + Gemini fallback)
   - Prompt: "Summarize this agenda item titled '{title}' based on attachments. Extract 1-3 main topics."
   - Returns: `{'summary': str, 'topics': List[str]}`

2. `combine_item_summaries(item_summaries: List[str]) -> str`
   - Synthesizes item summaries into meeting overview
   - Prompt: "Combine these item summaries into a coherent meeting narrative. Avoid repetition."

3. Modify `process_meeting()` to handle items:
   - If meeting has `items` field → process per-item
   - Otherwise → fallback to current monolithic processing
   - Store item summaries in `agenda_items` table
   - Store combined summary in `meetings.summary`

### 🔄 Phase 4: Background Daemon Hook

**File:** `backend/services/background_processor.py`

- When storing Legistar meetings, check for `items` field
- Store agenda items via `db.store_agenda_items()`
- Process queue: handle items individually or inline
- Track item-level processing status

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
- Meeting stores main packet URL (full agenda PDF)
- AgendaItems store per-item attachment URLs
- Both can have summaries (item-level + meeting-level)
- Topics stored as JSON arrays (future: normalize to separate table)

---

**Last Updated:** 2025-01-23
**Next Milestone:** Phase 3 complete (item-level processor functional)
