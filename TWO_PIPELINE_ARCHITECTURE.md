# Two-Pipeline Architecture - Item-Based First

**Date**: 2025-10-30
**Philosophy**: Backend extracts and stores structured data. Frontend handles presentation.

---

## Core Principle

**Backend should NOT do frontend work.**

- ❌ Concatenating items into text blob (presentation logic)
- ❌ Deciding how to display data (UI logic)
- ✅ Extracting structured data (data logic)
- ✅ Processing with LLM (enrichment logic)
- ✅ Storing granular data (persistence logic)
- ✅ Serving structured responses (API logic)

**Frontend should handle all presentation.**

- ✅ Receiving items array
- ✅ Deciding layout (list, accordion, tabs, etc.)
- ✅ Handling user interaction (expand/collapse)
- ✅ Client-side filtering/search
- ✅ Responsive design

---

## The Two Pipelines

### Pipeline 1: Item-Based (PRIMARY - 58% of cities)

**Vendors**: Legistar, PrimeGov, Granicus with HTML agendas

**Flow**:
```
1. Adapter extracts items from HTML agenda
   ├─ Item 1: "Oak Street Development"
   ├─ Item 2: "Budget Amendment"
   └─ Item 3-10: ...

2. Each item processed individually
   ├─ PDF text extraction from attachments
   ├─ LLM summarization (1-5 sentences)
   └─ Topic extraction (["housing", "zoning"])

3. Items stored in database
   └─ items table: id, meeting_id, title, sequence, summary, topics, attachments

4. Topics aggregated to meeting level
   └─ meeting.topics = ["housing", "zoning", "budget"] (for filtering)

5. API serves meeting + items array
   {
     "meeting": {..., "has_items": true, "topics": ["housing"]},
     "items": [
       {"title": "Oak Street", "summary": "...", "topics": ["housing"]},
       {"title": "Budget", "summary": "...", "topics": ["budget"]}
     ]
   }

6. Frontend renders structured view
   ├─ Agenda item list
   ├─ Topic badges per item
   ├─ Expandable summaries
   └─ Direct PDF links
```

**Key Point**: NO concatenation. Items stay granular from extraction to display.

---

### Pipeline 2: Monolithic (EDGE CASE - 42% of cities)

**Vendors**: CivicClerk, NovusAgenda, CivicPlus (no item extraction capability)

**Flow**:
```
1. Adapter fetches packet URL
   └─ Single PDF, no item breakdown available

2. Process entire packet as one unit
   ├─ Extract full PDF text
   └─ LLM summarization (comprehensive)

3. Store in meeting table
   └─ meeting.summary = "Large text blob..."
   └─ meeting.has_items = false

4. API serves meeting with summary
   {
     "meeting": {
       "summary": "...",
       "has_items": false
     }
   }

5. Frontend renders markdown blob
   └─ Single text view (like current implementation)
```

**Key Point**: This is the fallback for vendors that don't support item extraction.

---

## Database Schema

### `meetings` table
```sql
id                   TEXT PRIMARY KEY
banana               TEXT (FK to cities)
title                TEXT
date                 DATETIME
packet_url           TEXT (or JSON for multiple URLs)
summary              TEXT (NULL for item-based, populated for monolithic)
topics               JSON array (aggregated from items for item-based)
participation        JSON object
status               TEXT (cancelled/postponed/etc)
processing_status    TEXT (pending/processing/completed/failed)
processing_method    TEXT (item_level_N_items or monolithic)
processing_time      FLOAT
created_at           DATETIME
updated_at           DATETIME
```

### `items` table
```sql
id                   TEXT PRIMARY KEY
meeting_id           TEXT (FK to meetings)
title                TEXT
sequence             INT (order in agenda: 1, 2, 3...)
attachments          JSON array (URLs, page ranges, metadata)
summary              TEXT (individual item summary)
topics               JSON array (item-level topics)
created_at           DATETIME
```

---

## Backend Code Changes

### 1. Removed Concatenation (conductor.py)

**Before**:
```python
# Build combined summary
summary_parts = [f"\n{title}\n{summary}" for item in items]
combined_summary = "\n".join(summary_parts)

db.update_meeting_summary(
    meeting_id=meeting.id,
    summary=combined_summary,  # Concatenated blob
    topics=meeting_topics
)
```

**After**:
```python
# Aggregate topics only (no concatenation)
meeting_topics = aggregate_topics_from_items(items)

db.update_meeting_summary(
    meeting_id=meeting.id,
    summary=None,  # Frontend composes from items
    topics=meeting_topics  # For meeting-level filtering
)
```

### 2. Added Items to API Responses (server/main.py)

**All search endpoints now include items**:
```python
# Get meetings
meetings = db.get_meetings(bananas=[city.banana], limit=50)

# Enrich with items
meetings_with_items = []
for meeting in meetings:
    meeting_dict = meeting.to_dict()
    items = db.get_agenda_items(meeting.id)
    if items:
        meeting_dict["items"] = [item.to_dict() for item in items]
        meeting_dict["has_items"] = True
    else:
        meeting_dict["has_items"] = False
    meetings_with_items.append(meeting_dict)

return {"meetings": meetings_with_items}
```

---

## Frontend Usage

### Check meeting type:
```typescript
if (meeting.has_items && meeting.items) {
    // Item-based meeting - render structured view
    renderItemList(meeting.items);
} else if (meeting.summary) {
    // Monolithic meeting - render markdown
    renderSummary(meeting.summary);
} else {
    // Processing...
    renderProcessingState();
}
```

### Example Item-Based Rendering:
```svelte
{#if meeting.has_items && meeting.items}
    <div class="agenda-items">
        {#each meeting.items as item}
            <div class="item-card">
                <h3>{item.sequence}. {item.title}</h3>

                {#if item.topics}
                    <div class="topics">
                        {#each item.topics as topic}
                            <span class="topic-badge">{topic}</span>
                        {/each}
                    </div>
                {/if}

                {#if item.summary}
                    <p class="summary">{item.summary}</p>
                {/if}

                {#if item.attachments}
                    {#each item.attachments as attachment}
                        <a href={attachment.url}>
                            View Packet {attachment.pages ? `(${attachment.pages})` : ''}
                        </a>
                    {/each}
                {/if}
            </div>
        {/each}
    </div>
{:else if meeting.summary}
    <div class="markdown-content">
        {@html marked(meeting.summary)}
    </div>
{:else}
    <div class="processing">Processing...</div>
{/if}
```

---

## Benefits of This Architecture

### For Users:
1. **Better navigation** - Jump to specific agenda items
2. **Topic filtering** - See only housing-related items
3. **Direct access** - Click through to specific PDF pages
4. **Clearer structure** - Not a wall of text
5. **Faster scanning** - Read only what matters

### For Developers:
1. **Separation of concerns** - Backend handles data, frontend handles UI
2. **Flexibility** - Frontend can experiment with different layouts
3. **Reusability** - Items can be displayed in multiple views
4. **Type safety** - Structured data = fewer bugs
5. **Maintainability** - Logic is where it belongs

### For the System:
1. **Data utilization** - Actually using the granular data we extract
2. **Search quality** - Can search by item, not just meeting
3. **Scalability** - Structured data enables future features
4. **Cost efficiency** - Not wasting LLM calls on concatenation

---

## Migration Path (Already Complete!)

### ✅ Phase 1: Backend Changes
- [x] Remove concatenation from conductor.py
- [x] Update API to include items array
- [x] Add `has_items` flag to responses

### ⏳ Phase 2: Frontend Updates (Next)
- [ ] Add AgendaItem component
- [ ] Update meeting detail page to check `has_items`
- [ ] Render item list for item-based meetings
- [ ] Keep markdown rendering for monolithic meetings
- [ ] Add topic filtering UI

### ⏳ Phase 3: Enhancements
- [ ] Item-level deep links
- [ ] Topic-based navigation
- [ ] Collapsible items
- [ ] Search within meeting items
- [ ] Participation info display

---

## Examples

### Item-Based Meeting Response:
```json
{
  "meeting": {
    "id": "meeting_123",
    "title": "City Council Meeting - Oct 30, 2025",
    "topics": ["housing", "zoning", "budget"],
    "has_items": true
  },
  "items": [
    {
      "id": "item_001",
      "sequence": 1,
      "title": "Approval of Oak Street Development",
      "summary": "Approves 240-unit mixed-use development at 1500 Oak Street...",
      "topics": ["housing", "zoning", "transportation"],
      "attachments": [
        {"url": "https://...", "pages": "1-15"}
      ]
    },
    {
      "id": "item_002",
      "sequence": 2,
      "title": "FY2025 Budget Amendment",
      "summary": "Transfers $125,000 from Parks Department...",
      "topics": ["budget", "parks"],
      "attachments": [
        {"url": "https://...", "pages": "16-20"}
      ]
    }
  ]
}
```

### Monolithic Meeting Response:
```json
{
  "meeting": {
    "id": "meeting_456",
    "title": "City Council Meeting - Oct 30, 2025",
    "summary": "Large comprehensive text covering all agenda items...",
    "has_items": false
  }
}
```

---

## Performance Considerations

**API Response Size**: Item-based responses are larger (10 items × ~500 bytes = ~5KB extra)
- **Acceptable**: Modern networks handle this easily
- **Cacheable**: Browsers cache responses
- **Worth it**: Better UX >> marginal bandwidth

**Database Queries**: One extra query per meeting (get_agenda_items)
- **Mitigated**: Could batch-fetch all items in one query
- **Fast**: Items table has index on meeting_id
- **Acceptable**: ~1ms overhead per meeting

---

## Confidence

**10/10** - This is the correct architecture.

**Why**:
1. Follows separation of concerns
2. Utilizes data we're already extracting
3. Enables better UX
4. More maintainable
5. Industry standard (backend=data, frontend=presentation)

---

**Status**: Backend refactored ✅ | Frontend updates needed ⏳
