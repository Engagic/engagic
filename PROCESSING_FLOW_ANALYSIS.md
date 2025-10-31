# Processing Flow Analysis - Item Summaries to Meeting Summary

**Date**: 2025-10-30
**Question**: How do item summaries get concatenated? Can we point to which item contains which topic?

---

## TL;DR

**YES**, items are processed individually with their own summaries and topics.
**YES**, we CAN point to which item contains which topic (it's in the DB).
**BUT**, the frontend only gets the concatenated summary and loses all granularity.

---

## The Processing Flow (Item-Based Meetings)

### Step 1: Items Extracted by Adapter

```python
# adapters/legistar_adapter.py (or primegov, granicus)
items = [
    {
        "id": "item_001",
        "title": "Approval of Oak Street Development",
        "sequence": 1,
        "attachments": [{"url": "https://...", "pages": "1-15"}]
    },
    {
        "id": "item_002",
        "title": "FY2025 Budget Amendment",
        "sequence": 2,
        "attachments": [{"url": "https://...", "pages": "16-20"}]
    },
    # ... 8 more items
]
# Stored in database: items table
```

### Step 2: Each Item Processed Individually

**File**: `pipeline/conductor.py:696-873`

```python
def _process_meeting_with_items(meeting, agenda_items):
    # For EACH item separately:
    for item in need_processing:
        # 1. Extract PDF text from attachments
        text = extract_text_from_pdfs(item.attachments)

        # 2. Call LLM for THIS item only
        summary, topics = llm.summarize_item(
            item_title=item.title,
            text=text
        )

        # 3. Store in database - ITEM TABLE
        db.update_agenda_item(
            item_id=item.id,
            summary=summary,        # "Approves 240-unit development at..."
            topics=topics           # ["housing", "zoning", "transportation"]
        )

        # 4. Add to processed list
        processed_items.append({
            "sequence": item.sequence,
            "title": item.title,
            "summary": summary,
            "topics": topics
        })
```

**At this point**:
- ✅ Each item has its own summary in the database
- ✅ Each item has its own topics in the database
- ✅ We can query: "Which items have topic 'housing'?" → Item 1
- ✅ We can query: "What's the summary for Item 2?" → "Transfers $125,000..."

### Step 3: Items CONCATENATED into Meeting Summary

**File**: `pipeline/conductor.py:874-913`

```python
# Build combined summary directly
summary_parts = [f"Meeting: {meeting.title}\n"]

for item in processed_items:
    title = item.get("title", "Untitled Item")
    summary = item.get("summary", "No summary available")
    summary_parts.append(f"\n{title}\n{summary}")

summary_parts.append(f"\n\n[Processed {len(processed_items)} items]")
combined_summary = "\n".join(summary_parts)
```

**Output** (what gets stored in `meetings.summary`):
```
Meeting: City Council Meeting - Oct 30, 2025

Approval of Oak Street Development
Approves 240-unit mixed-use development at 1500 Oak Street including...

FY2025 Budget Amendment
Transfers $125,000 from Parks Department general fund to emergency repairs...

Traffic Signal Installation at Main & Oak
Installs new traffic signal at intersection with $85,000 budget...

[Processed 10 items]
```

### Step 4: Topics AGGREGATED from Items

**File**: `pipeline/conductor.py:885-898`

```python
# Collect ALL topics from ALL items
all_topics = []
for item in processed_items:
    all_topics.extend(item.get("topics", []))

# Count frequency
# Item 1: ["housing", "zoning", "transportation"]
# Item 2: ["budget", "parks"]
# Item 3: ["transportation"]
# Item 4: ["housing", "zoning"]
# → all_topics = ["housing", "zoning", "transportation", "budget", "parks", "transportation", "housing", "zoning"]

topic_counts = {}
for topic in all_topics:
    topic_counts[topic] = topic_counts.get(topic, 0) + 1

# topic_counts = {"housing": 2, "zoning": 2, "transportation": 2, "budget": 1, "parks": 1}

# Sort by frequency (most common first)
meeting_topics = sorted(
    topic_counts.keys(),
    key=lambda t: topic_counts[t],
    reverse=True
)
# → ["housing", "zoning", "transportation", "budget", "parks"]
```

### Step 5: Meeting Updated with Aggregated Data

**File**: `pipeline/conductor.py:907-913`

```python
self.db.update_meeting_summary(
    meeting_id=meeting.id,
    summary=combined_summary,              # Concatenated text
    processing_method=f"item_level_10_items",
    processing_time=processing_time,
    topics=meeting_topics                  # Aggregated, sorted by frequency
)
```

**Database State After Processing**:

**`meetings` table**:
```
id: "meeting_123"
summary: "Meeting: City Council...\n\nApproval of Oak Street...\n\n[Processed 10 items]"
topics: ["housing", "zoning", "transportation", "budget", "parks"]
```

**`items` table**:
```
Row 1:
  id: "item_001"
  meeting_id: "meeting_123"
  title: "Approval of Oak Street Development"
  summary: "Approves 240-unit mixed-use development..."
  topics: ["housing", "zoning", "transportation"]

Row 2:
  id: "item_002"
  meeting_id: "meeting_123"
  title: "FY2025 Budget Amendment"
  summary: "Transfers $125,000 from Parks..."
  topics: ["budget", "parks"]

Row 3-10: ...
```

---

## Can We Point to Which Item Contains Which Topic?

**Answer: YES, ABSOLUTELY** ✅

The database has everything needed:

```sql
-- Which items have topic "housing"?
SELECT id, title, summary
FROM items
WHERE meeting_id = 'meeting_123'
  AND EXISTS (
    SELECT 1 FROM json_each(items.topics)
    WHERE value = 'housing'
  );

-- Result:
-- item_001 | Approval of Oak Street Development | Approves 240-unit...
-- item_004 | Zoning Change for Downtown District | Changes zoning...
```

**The backend endpoint `/api/search/by-topic` ALREADY DOES THIS!**

**File**: `server/main.py:987-1015`

```python
@app.post("/api/search/by-topic")
async def search_by_topic(request: TopicSearchRequest):
    # Find meetings with topic
    meetings = db.search_meetings_by_topic(normalized_topic)

    # For each meeting, get ITEMS that match this topic
    for meeting in meetings:
        items_query = """
            SELECT * FROM items
            WHERE meeting_id = ?
            AND EXISTS (SELECT 1 FROM json_each(items.topics) WHERE value = ?)
        """
        matching_items = [AgendaItem.from_db_row(row) for row in item_rows]

        results.append({
            "meeting": meeting.to_dict(),
            "matching_items": [
                {
                    "id": item.id,
                    "title": item.title,
                    "sequence": item.sequence,
                    "summary": item.summary,
                    "topics": item.topics
                }
                for item in matching_items
            ]
        })
```

**This endpoint EXISTS but frontend doesn't use it!**

---

## The Problem

### What We Store:
```
Meeting 123
  ├─ Item 1: "Oak Street" → ["housing", "zoning", "transportation"]
  ├─ Item 2: "Budget" → ["budget", "parks"]
  ├─ Item 3: "Traffic Signal" → ["transportation"]
  └─ [... 7 more items]

Meeting summary: [CONCATENATED TEXT OF ALL 10 ITEMS]
Meeting topics: ["housing", "zoning", "transportation", "budget", "parks"]
```

### What Frontend Gets (via `/api/search`):
```json
{
  "meetings": [
    {
      "id": "meeting_123",
      "summary": "Meeting: City Council...\n\nApproval of Oak Street...\n\n[10 items]",
      "topics": ["housing", "zoning", "transportation", "budget", "parks"]
    }
  ]
}
```

### What Frontend Shows:
```
City Council Meeting - Oct 30, 2025

[WALL OF TEXT - 10 items concatenated]
```

### What Frontend SHOULD Get:
```json
{
  "meetings": [
    {
      "id": "meeting_123",
      "topics": ["housing", "zoning", "transportation", "budget", "parks"],
      "items": [
        {
          "id": "item_001",
          "title": "Approval of Oak Street Development",
          "sequence": 1,
          "summary": "Approves 240-unit mixed-use development...",
          "topics": ["housing", "zoning", "transportation"]
        },
        {
          "id": "item_002",
          "title": "FY2025 Budget Amendment",
          "sequence": 2,
          "summary": "Transfers $125,000...",
          "topics": ["budget", "parks"]
        }
      ]
    }
  ]
}
```

### What Frontend SHOULD Show:
```
City Council Meeting - Oct 30, 2025

Topics: Housing • Zoning • Transportation • Budget • Parks

📋 Agenda Items (10 total)

1. Approval of Oak Street Development
   Topics: Housing, Zoning, Transportation
   Approves 240-unit mixed-use development at 1500 Oak Street...
   [View 15-page packet]

2. FY2025 Budget Amendment
   Topics: Budget, Parks
   Transfers $125,000 from Parks Department...
   [View 5-page packet]

[... more items]
```

---

## Answers to Your Questions

### Q: Are we concatenating summaries of items into 1 meeting summary?

**A: YES**, line 874-883 in `conductor.py`:

```python
summary_parts = [f"Meeting: {meeting.title}\n"]
for item in processed_items:
    title = item.get("title", "Untitled Item")
    summary = item.get("summary", "No summary available")
    summary_parts.append(f"\n{title}\n{summary}")
combined_summary = "\n".join(summary_parts)
```

**But the original item summaries are still in the database!**

### Q: Can we point to which item contains which topic if we were asked?

**A: YES**, the data exists in the `items` table:

```sql
SELECT title, summary, topics
FROM items
WHERE meeting_id = ?
  AND EXISTS (SELECT 1 FROM json_each(topics) WHERE value = 'housing');
```

**And we already have an endpoint for this**: `/api/search/by-topic`

**But we DON'T expose it in the main meeting detail view!**

---

## The Core Issue

You're doing **TWICE the work**:

1. ✅ Process each item individually (expensive LLM calls)
2. ✅ Store each item with summary + topics
3. ❌ Concatenate into monolithic summary
4. ❌ Serve only the concatenation to frontend
5. ❌ Throw away the granularity

**It's like:**
- Taking a high-res photo (item-level processing)
- Downsampling to 480p (concatenation)
- Storing both versions
- Only showing users the 480p version

---

## What Should Change

### Backend (Minimal Change):

**Option 1: Add items to existing endpoints**
```python
# In handle_city_search(), handle_zipcode_search()
meetings = db.get_meetings(bananas=[city.banana], limit=50)

# For each meeting, optionally include items
for meeting in meetings:
    items = db.get_agenda_items(meeting.id)
    meeting_dict = meeting.to_dict()
    if items:
        meeting_dict["items"] = [item.to_dict() for item in items]
```

**Option 2: New endpoint for meeting detail**
```python
@app.get("/api/meeting/{meeting_id}")
async def get_meeting_detail(meeting_id: str):
    meeting = db.get_meeting(meeting_id)
    items = db.get_agenda_items(meeting_id)

    return {
        "meeting": meeting.to_dict(),
        "items": [item.to_dict() for item in items]
    }
```

### Frontend (Moderate Change):

1. **Update types** (already done!)
2. **Create `AgendaItemCard` component**
3. **Refactor meeting detail** to show items list instead of monolithic summary
4. **Add topic filtering** to items

---

## Recommendation

**Stop concatenating summaries for frontend consumption.**

Keep the concatenated summary for:
- Full-text search indexing
- LLM context in future features
- Legacy compatibility

But expose the items array in API responses so users get:
- Individual item navigation
- Topic-level filtering
- Direct attachment links
- Better UX

**You already have all the infrastructure. Just expose the data you're collecting.**

---

**Confidence**: 10/10 - Direct code inspection confirms concatenation happens and item data exists in DB.
