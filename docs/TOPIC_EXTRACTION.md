# Topic Extraction - Implementation Complete

**Status:** Ready for deployment
**Date:** 2025-10-30
**Phase:** Phase 1 (Foundation)

---

## Overview

Topic extraction automatically tags meetings and agenda items with standardized topics like "housing", "transportation", "zoning", etc. This unlocks:
- **Search by topic** - "Show me all meetings about affordable housing"
- **User subscriptions** - "Alert me when my city discusses zoning"
- **Smart filtering** - "Housing meetings in the last month"
- **Analytics** - "What topics are trending across cities?"

---

## Architecture

### 1. AI Extraction (Already Working!)
**Location:** `analysis/llm/summarizer.py`

Topics are extracted during normal item processing via JSON structured output:
```python
{
  "topics": ["housing", "zoning"],  # Array of canonical topics
  "summary_markdown": "...",
  "confidence": "high"
}
```

The LLM prompt (analysis/llm/prompts_v2.json) uses JSON schema with enum validation:
```json
{
  "topics": {
    "type": "array",
    "items": {
      "type": "string",
      "enum": ["housing", "zoning", "transportation", ...]
    }
  }
}
```

### 2. Normalization
**Location:** `analysis/topics/normalizer.py`

Maps AI variations to canonical forms:
- "affordable housing" → `housing`
- "traffic safety" → `transportation`
- "rezoning" → `zoning`

**Taxonomy:** `analysis/topics/taxonomy.json` (16 canonical topics)

**Usage:**
```python
from analysis.topics.normalizer import get_normalizer

normalizer = get_normalizer()
normalized = normalizer.normalize(["affordable housing", "zoning changes"])
# Returns: ["housing", "zoning"]
```

### 3. Aggregation
**Location:** `pipeline/conductor.py`

After processing all items, topics are aggregated to meeting level:
```python
# Collect all item topics
all_topics = []
for item in processed_items:
    all_topics.extend(item.get("topics", []))

# Count frequency and sort by frequency
topic_counts = {topic: count for topic, count in ...}
meeting_topics = sorted(topic_counts.keys(), key=lambda t: topic_counts[t], reverse=True)
```

**Result:** Meeting has `["housing", "zoning", "transportation"]` (most common first)

### 4. Storage
**Database:** SQLite with JSON columns

```sql
-- Items table (already has topics column)
CREATE TABLE items (
    ...
    topics TEXT,  -- JSON array: ["housing", "zoning"]
    ...
);

-- Meetings table (NEW column)
CREATE TABLE meetings (
    ...
    topics TEXT,  -- JSON array: ["housing", "transportation", "zoning"]
    ...
);
```

**Data classes:**
```python
@dataclass
class AgendaItem:
    topics: Optional[List[str]] = None  # Per-item topics

@dataclass
class Meeting:
    topics: Optional[List[str]] = None  # Aggregated from items
```

---

## API Endpoints (NEW)

### 1. List All Topics
```http
GET /api/topics
```

**Response:**
```json
{
  "success": true,
  "topics": [
    {
      "canonical": "housing",
      "display_name": "Housing & Development"
    },
    {
      "canonical": "transportation",
      "display_name": "Transportation & Traffic"
    }
  ],
  "count": 16
}
```

### 2. Search by Topic
```http
POST /api/search/by-topic
Content-Type: application/json

{
  "topic": "affordable housing",
  "banana": "paloaltoCA",  // optional
  "limit": 50
}
```

**Response:**
```json
{
  "success": true,
  "query": "affordable housing",
  "normalized_topic": "housing",
  "display_name": "Housing & Development",
  "results": [
    {
      "meeting": { ... },
      "matching_items": [
        {
          "id": "item_123",
          "title": "Affordable Housing Development at 123 Main St",
          "summary": "...",
          "topics": ["housing", "zoning"]
        }
      ]
    }
  ],
  "count": 15
}
```

### 3. Popular Topics
```http
GET /api/topics/popular
```

**Response:**
```json
{
  "success": true,
  "topics": [
    {
      "topic": "housing",
      "display_name": "Housing & Development",
      "count": 342
    },
    {
      "topic": "zoning",
      "display_name": "Zoning & Land Use",
      "count": 278
    }
  ],
  "count": 20
}
```

---

## Deployment Steps

### 1. Local Testing (Already Done!)
```bash
# Test normalization
python scripts/test_topic_extraction.py
# ✓ ALL TESTS PASSED
```

### 2. Push to GitHub
```bash
git add .
git commit -m "Add topic extraction with normalization and aggregation

- Created topic taxonomy with 16 canonical topics
- Built topic normalizer for consistent tagging
- Added meeting-level topic aggregation
- Created API endpoints for topic search
- Updated database schema with topics column"
git push origin main
```

### 3. Deploy to VPS
```bash
# SSH to VPS
ssh root@engagic

# Pull changes
cd /root/engagic
git pull origin main

# Run migration
python scripts/migrate_add_topics.py

# Restart services
systemctl restart engagic-api
systemctl restart engagic-daemon
```

### 4. Backfill Existing Meetings (Optional)
```bash
# On VPS: Run full sync to process all meetings
engagic-conductor --full-sync
```

This will:
- Sync all cities and process their meetings
- Extract topics from meeting items
- Normalize and aggregate to meeting level

**Note:** New meetings will automatically get topics during normal processing via the daemon.

---

## Testing the API

### Get all topics
```bash
curl http://localhost:8000/api/topics
```

### Search for housing meetings
```bash
curl -X POST http://localhost:8000/api/search/by-topic \
  -H "Content-Type: application/json" \
  -d '{"topic": "affordable housing", "banana": "paloaltoCA"}'
```

### Get popular topics
```bash
curl http://localhost:8000/api/topics/popular
```

---

## Topic Taxonomy

**16 Canonical Topics:**
1. `housing` - Housing & Development
2. `zoning` - Zoning & Land Use
3. `transportation` - Transportation & Traffic
4. `budget` - Budget & Finance
5. `public_safety` - Public Safety
6. `environment` - Environment & Sustainability
7. `parks` - Parks & Recreation
8. `utilities` - Utilities & Infrastructure
9. `economic_development` - Economic Development
10. `education` - Education & Schools
11. `health` - Public Health
12. `planning` - City Planning
13. `permits` - Permits & Licensing
14. `contracts` - Contracts & Procurement
15. `appointments` - Appointments & Personnel
16. `other` - Other

**Synonym Mapping:** See `analysis/topics/taxonomy.json`

---

## Future Enhancements

### Phase 2: User Subscriptions
- User profiles with topic preferences
- Email alerts when topics match
- Weekly digest by topic

### Phase 3: Analytics
- Trending topics across cities
- Topic frequency over time
- Geographic topic distribution

### Phase 4: Advanced Search
- Multi-topic queries ("housing AND zoning")
- Topic exclusions ("transportation NOT parking")
- Date range filtering by topic

### Phase 5: Taxonomy Evolution
- Track unknown topics for expansion
- City-specific topic variations
- User-suggested topics

---

## Files Changed

**New Files:**
- `analysis/topics/taxonomy.json` - Canonical topic definitions
- `analysis/topics/normalizer.py` - Topic normalization logic
- `scripts/test_topic_extraction.py` - Test suite
- `scripts/migrate_add_topics.py` - Database migration
- `docs/TOPIC_EXTRACTION.md` - This document

**Modified Files:**
- `database/db.py` - Added topics to Meeting dataclass and schema
- `analysis/llm/prompts_v2.json` - JSON schema with topic enum validation
- `pipeline/conductor.py` - Added normalization and aggregation
- `server/main.py` - Added 3 new topic endpoints

**Lines Changed:** ~350 additions

---

## Key Design Decisions

### Why Normalization?
**Problem:** AI generates variations - "affordable housing", "housing affordability", "low-income housing"
**Solution:** Map all variations to canonical "housing"
**Benefit:** Consistent search, clean UI, accurate analytics

### Why 16 Topics?
**Balance:** Broad enough to cover 90% of meetings, specific enough to be useful
**Expandable:** Easy to add new canonical topics as patterns emerge
**User-friendly:** Not overwhelming for subscriptions

### Why Meeting-Level Aggregation?
**Use case:** "Show me meetings about housing" (not just individual items)
**Sorting:** Most common topics first = meeting's primary focus
**API simplicity:** One query returns meeting + matching items

### Why JSON in SQLite?
**Flexibility:** Topics are dynamic, don't need normalized table
**Performance:** SQLite json_each() is fast enough for our scale
**Simplicity:** No schema migrations when adding topics
**Future-proof:** Easy to migrate to PostgreSQL jsonb later

---

## Success Metrics

**Immediate:**
- Topic extraction working in production
- Normalization reduces variations by ~70%
- API endpoints functional

**Short-term (1 month):**
- 50% of meetings have topics
- Popular topics endpoint shows real patterns
- Frontend uses topic filtering

**Long-term (3 months):**
- User subscriptions by topic
- Email alerts based on topics
- Topic-based search is primary discovery method

---

**Status:** Ready for production deployment
