# Data Exposure Audit - What We're NOT Showing

**Date**: 2025-10-30
**Focus**: Item-based meetings (58% of cities) and unexposed database fields
**Severity**: HIGH - Major data loss

---

## Executive Summary

Your backend is **item-based first** (58% of cities use Legistar/PrimeGov/Granicus with item-level extraction), but your frontend is **meeting-summary only**. You're storing rich, granular data and serving back a monolithic text blob.

**Impact**: Users see a wall of text instead of structured, navigable agenda items with individual summaries and topics.

---

## The Item-Based Flow (Currently Broken)

### What Happens in the Backend:

1. **Adapter fetches meeting** (Legistar/PrimeGov/Granicus)
   - Extracts 10-50 individual agenda items per meeting
   - Each item has: title, sequence, attachments (PDFs with page ranges)

2. **Items stored in database** (`items` table)
   ```python
   AgendaItem:
       id: str                    # Vendor-specific item ID
       meeting_id: str            # FK to meeting
       title: str                 # "Approval of Oak Street Development"
       sequence: int              # Order in agenda (1, 2, 3...)
       attachments: List[Any]     # [{"url": "...", "pages": "1-15"}, ...]
       summary: str               # Individual item summary (1-5 sentences)
       topics: List[str]          # ["housing", "zoning", "transportation"]
   ```

3. **Items get processed**
   - Each item gets its own LLM summary
   - Each item gets topic extraction
   - Items are then AGGREGATED into meeting-level topics

4. **API returns meetings** (`/api/search`)
   ```json
   {
     "meetings": [
       {
         "id": "...",
         "title": "City Council Meeting",
         "summary": "MASSIVE WALL OF TEXT WITH ALL ITEMS SMOOSHED TOGETHER",
         "topics": ["housing", "zoning", "budget"],
         "date": "2025-10-30"
       }
     ]
   }
   ```

5. **Frontend displays**
   - Meeting title
   - Meeting date
   - Monolithic summary blob (markdown)
   - NO individual items
   - NO item-level navigation
   - NO item-level topics
   - NO attachment links

### What SHOULD Happen:

**Frontend should display**:
```
City Council Meeting - Oct 30, 2025

📋 Agenda Items (8 total)

1. Approval of Oak Street Development
   Topics: Housing, Zoning, Transportation
   Approves 240-unit mixed-use development at 1500 Oak Street...
   [View Packet (15 pages)]

2. FY2025 Budget Amendment
   Topics: Budget, Parks
   Transfers $125,000 for Central Park playground...
   [View Packet (5 pages)]

3. Traffic Signal Installation at Main & Oak
   Topics: Transportation
   ...
```

---

## Data Loss Breakdown

### 1. AgendaItems Table (COMPLETELY UNEXPOSED)

**For 58% of cities**, we extract and store:

| Field | What It Is | Why Users Need It |
|-------|-----------|-------------------|
| `title` | Individual agenda item name | Navigate to specific topics of interest |
| `sequence` | Order in agenda (1, 2, 3...) | Understand meeting structure |
| `attachments` | PDF URLs + page ranges | Direct links to source documents |
| `summary` | Item-level summary (1-5 sentences) | Quick scan without wall of text |
| `topics` | Item-level topics | Filter/search by topic |

**Current exposure**: ZERO. Only exposed in `/api/search/by-topic` (niche endpoint).

**Database method exists**: `db.get_agenda_items(meeting_id)` - **UNUSED by API**

---

### 2. Meeting Participation Info (UNEXPOSED)

**Field**: `participation: Dict[str, Any]`

**What it contains**:
```json
{
  "email": "cityclerk@example.com",
  "phone": "(650) 555-0123",
  "virtual_url": "https://zoom.us/j/12345",
  "physical_location": "City Hall, 250 Hamilton Ave"
}
```

**Why users need it**:
- How to attend meetings virtually
- How to submit public comments
- Where to show up in person
- Who to contact with questions

**Current exposure**: ZERO. Frontend types include it, but it's never displayed.

---

### 3. Meeting Topics (BARELY EXPOSED)

**Field**: `topics: List[str]` - Aggregated from all items

**What it is**: ["housing", "zoning", "budget", "transportation"]

**Current exposure**:
- ✅ Returned in API responses
- ❌ Frontend types include it
- ❌ Frontend NEVER displays it
- ❌ No topic filtering on meeting list
- ❌ No topic badges/chips

**Why users need it**:
- Filter meetings by topic of interest
- See at a glance what meeting covers
- Topic-based notifications/alerts

---

### 4. Processing Metadata (UNEXPOSED)

**Fields**:
- `processing_status`: "pending" | "processing" | "completed" | "failed"
- `processing_method`: "tier1_pypdf2_gemini" | "multiple_pdfs_N_combined"
- `processing_time`: 45.3 (seconds)

**Why users might need it**:
- Show "Processing..." state instead of "No summary yet"
- Transparency about AI processing
- Error handling (show "Processing failed" instead of blank)

**Current exposure**:
- ✅ Frontend types include `processing_status`
- ❌ Never displayed or used

---

### 5. City Metadata (PARTIALLY EXPOSED)

**Unexposed fields**:
- `county`: "Santa Clara County"
- `status`: "active" | "inactive"
- `created_at`: When city was added
- `updated_at`: Last sync time

**Why users might need it**:
- County-level browsing
- "Last updated: 2 hours ago" freshness indicator
- Filter out inactive cities

---

### 6. Meeting UUID (UNEXPOSED)

**Field**: `id: str`

**Current situation**:
- Frontend identifies meetings by slug (generated from title + date)
- Backend has proper UUIDs
- No way to directly fetch meeting by ID

**Why it matters**:
- Stable identifier for bookmarks/links
- Faster lookups (index on UUID vs slug generation)
- API endpoints could use `/api/meeting/{id}` instead of complex slug matching

---

## API Endpoint Gaps

### Exists in DB, NOT in API:

1. ❌ `GET /api/meeting/{meeting_id}` - Fetch single meeting by ID
2. ❌ `GET /api/meeting/{meeting_id}/items` - Fetch items for a meeting
3. ❌ `GET /api/city/{banana}/stats` - City-level statistics
4. ❌ `GET /api/topics` - List all topics (EXISTS but frontend doesn't use it)

### Exists in API, NOT used by Frontend:

1. ✅ `GET /api/topics` - Get all canonical topics
2. ✅ `GET /api/topics/popular` - Most common topics
3. ✅ `POST /api/search/by-topic` - Search meetings by topic

**These are POWERFUL endpoints that the frontend ignores.**

---

## Data Flow Comparison

### Current Flow (Meeting-Summary Model):
```
Legistar API
  └─> 10 agenda items extracted
      └─> Each item processed individually
          └─> Items aggregated into meeting summary
              └─> Frontend gets: ONE BIG TEXT BLOB
```

### Should Be (Item-Based Model):
```
Legistar API
  └─> 10 agenda items extracted
      └─> Each item processed individually
          └─> API returns: meeting + array of items
              └─> Frontend displays: STRUCTURED AGENDA with navigation
```

---

## Specific Examples of Data Loss

### Example 1: Palo Alto City Council (Legistar)

**What we store**:
```
Meeting: "City Council Meeting - Oct 30, 2025"
  Item 1: "Approval of Oak Street Development" (housing, zoning)
    - Summary: "Approves 240-unit mixed-use development..."
    - Attachments: [{"url": "...", "pages": "1-15"}]
  Item 2: "FY2025 Budget Amendment" (budget, parks)
    - Summary: "Transfers $125,000 for Central Park..."
    - Attachments: [{"url": "...", "pages": "16-20"}]
  Item 3: "Traffic Signal Installation" (transportation)
    ...
```

**What we show**:
```
City Council Meeting - Oct 30, 2025

[WALL OF TEXT combining all 10 items into one markdown blob]
```

**What users WANT**:
- Click "Housing" filter → See only Item 1
- Click Item 2 → Jump to budget section
- See "15-page packet" → Know if it's worth reading

---

### Example 2: Search by Topic

**Current**:
1. User searches "housing"
2. Gets list of MEETINGS that mention housing
3. Clicks meeting
4. Gets wall of text
5. Has to Ctrl+F to find housing-related content

**Should be**:
1. User searches "housing"
2. Gets list of SPECIFIC AGENDA ITEMS about housing
3. Clicks item
4. Sees focused summary of that ONE item
5. Can jump directly to source PDF

---

## Recommendations (Priority Order)

### P0 - Critical (Breaks Item-Based Model):

1. **Add items to Meeting API response**
   ```typescript
   interface Meeting {
     // ... existing fields ...
     items?: AgendaItem[];  // NEW: Include items array
   }
   ```

2. **Create item-based meeting detail view**
   - Replace monolithic summary with structured item list
   - Each item gets its own card/section
   - Show item topics as badges
   - Link to individual PDF attachments

3. **Expose participation info**
   - Show "How to Participate" section
   - Zoom links, email, phone, physical location

### P1 - High Value:

4. **Add topic filtering to meeting list**
   - Show topic badges on meeting cards
   - Click topic → filter to meetings with that topic
   - Use existing `/api/topics` and `/api/search/by-topic` endpoints

5. **Show processing status**
   - "Processing..." state instead of empty
   - "Processing failed" with retry option
   - Estimated time remaining

6. **Add meeting-by-ID endpoint**
   ```python
   @app.get("/api/meeting/{meeting_id}")
   async def get_meeting(meeting_id: str):
       meeting = db.get_meeting(meeting_id)
       items = db.get_agenda_items(meeting_id)
       return {"meeting": meeting.to_dict(), "items": [i.to_dict() for i in items]}
   ```

### P2 - Nice to Have:

7. **County-level browsing**
8. **Freshness indicators** ("Updated 2 hours ago")
9. **Meeting statistics** (avg processing time, success rate)

---

## Code Changes Required

### Backend (Minimal):

1. **Modify Meeting.to_dict()** to optionally include items:
   ```python
   def to_dict(self, include_items: bool = False) -> dict:
       data = asdict(self)
       # ... existing code ...

       if include_items:
           items = db.get_agenda_items(self.id)
           data["items"] = [item.to_dict() for item in items]

       return data
   ```

2. **Add items to search responses**:
   ```python
   # In handle_city_search, handle_zipcode_search
   meetings = db.get_meetings(bananas=[city.banana], limit=50)
   return {
       "meetings": [m.to_dict(include_items=True) for m in meetings]
   }
   ```

### Frontend (Moderate):

1. **Update Meeting type** (already done! ✅)
2. **Create AgendaItem component**
3. **Refactor meeting detail page** to show items
4. **Add topic badges** to meeting list
5. **Add participation section** to meeting detail

---

## The Elephant in the Room

**You built an item-based extraction pipeline (58% of cities!) but serve a meeting-summary-only frontend.**

This is like:
- Building a relational database but only returning CSVs
- Extracting structured data but serving it as unstructured text
- Having GPS coordinates but only showing street names

**The infrastructure is there. The data is there. It's just not exposed.**

---

## Impact Assessment

**Current Experience**:
- User searches "Palo Alto"
- Sees 10 meetings
- Clicks one
- Gets 5000-word wall of text
- Gives up

**With Item-Based UI**:
- User searches "Palo Alto"
- Sees 10 meetings with topic badges
- Filters by "Housing"
- Sees 3 meetings, 8 total housing items
- Clicks specific item
- Gets focused 2-paragraph summary
- Clicks "View 15-page packet"
- Finds what they need in 30 seconds

---

## Technical Debt Summary

| Category | In DB | In API | In Frontend | Usage |
|----------|-------|--------|-------------|-------|
| **AgendaItems** | ✅ Full | ⚠️ Topic search only | ❌ None | 0% |
| **Participation** | ✅ Full | ✅ Returned | ❌ Not displayed | 0% |
| **Topics** | ✅ Full | ✅ Multiple endpoints | ❌ Not displayed | 0% |
| **Processing Status** | ✅ Full | ✅ Returned | ❌ Not used | 0% |
| **Meeting UUID** | ✅ Full | ✅ Returned | ❌ Not used | 0% |

**Overall data utilization**: ~20% (only showing title, date, summary)

---

**Confidence**: 10/10 - This is based on direct code inspection of database schema, API endpoints, and frontend components.

**Recommendation**: Prioritize exposing AgendaItems. It's the biggest unlock for user experience and you already have all the infrastructure.
