# Engagic API Reference

Complete reference for the Engagic public API endpoints.

**For server code architecture and implementation details, see:** [../server/README.md](../server/README.md)

**Base URL (Production):** `https://api.engagic.org`
**Base URL (Local):** `http://localhost:8000`

**Version:** v1
**Last Updated:** December 3, 2025

---

**This document provides:**
- Public API endpoint specifications
- Request/response examples
- Authentication and rate limiting
- Error codes and troubleshooting

**For server implementation, see:** [../server/README.md](../server/README.md)

---

## Table of Contents

- [Authentication](#authentication)
- [Rate Limiting](#rate-limiting)
- [Response Format](#response-format)
- [Search Endpoints](#search-endpoints)
- [Topic Endpoints](#topic-endpoints)
- [Meeting Endpoints](#meeting-endpoints)
- [Vote Endpoints](#vote-endpoints)
- [Committee Endpoints](#committee-endpoints)
- [Engagement Endpoints](#engagement-endpoints)
- [Feedback Endpoints](#feedback-endpoints)
- [System Endpoints](#system-endpoints)
- [Admin Endpoints](#admin-endpoints)
- [Error Codes](#error-codes)

---

## Authentication

### Public Endpoints
Most endpoints are **public and require no authentication**.

### Admin Endpoints
Admin endpoints require the `X-Admin-Token` header:

```http
X-Admin-Token: your-admin-token-here
```

Set via `ENGAGIC_ADMIN_TOKEN` environment variable.

---

## Rate Limiting

**Tiered rate limiting** balances open data access with infrastructure sustainability.

### Tiers

| Tier | Minute Limit | Daily Limit | Auth Required | Use Case |
|------|--------------|-------------|---------------|----------|
| **Free** | 30 req/min | 300 req/day | No | Personal use, exploration |
| **Hacktivist** | 100 req/min | 5,000 req/day | Yes (attribution) | Nonprofits, journalists, researchers |
| **Enterprise** | 1,000+ req/min | 100,000+ req/day | Yes (paid) | Commercial applications |

**Self-host option:** AGPL-3.0 license - unlimited if you run your own instance

### Headers

```http
X-RateLimit-Limit: 30
X-RateLimit-Remaining: 25
X-RateLimit-Reset: 1698765432
X-RateLimit-Limit-Day: 300
X-RateLimit-Remaining-Day: 275
```

### Rate Limit Exceeded (429)

```json
{
  "detail": "Rate limit exceeded",
  "retry_after": 45,
  "current_tier": "free",
  "limits": {
    "minute": {"limit": 30, "remaining": 0, "reset": 1698765432},
    "day": {"limit": 300, "remaining": 150, "reset": 1698851832}
  },
  "upgrade_options": {
    "hacktivist": "Email admin@motioncount.com with your use case for nonprofit/journalist tier",
    "enterprise": "Visit https://motioncount.com for commercial pricing",
    "self_host": "Clone https://github.com/yourusername/engagic and run unlimited"
  }
}
```

**HTTP Status:** `429 Too Many Requests`

---

## Response Format

All responses return JSON with a consistent structure:

### Success Response
```json
{
  "success": true,
  "data": { ... },
  "message": "Optional success message"
}
```

### Error Response
```json
{
  "detail": "Error message describing what went wrong"
}
```

---

## Search Endpoints

### Search Meetings

Universal search endpoint that handles zipcodes, city names, and state queries.

**Endpoint:** `POST /api/search`

**Request Body:**
```json
{
  "query": "94301"  // Zipcode, city name, or state
}
```

**Examples:**
```bash
# Search by zipcode
curl -X POST https://api.engagic.org/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "94301"}'

# Search by city name
curl -X POST https://api.engagic.org/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "Palo Alto, CA"}'

# Search by state
curl -X POST https://api.engagic.org/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "California"}'
```

**Response (Zipcode/City):**
```json
{
  "success": true,
  "city_name": "Palo Alto",
  "state": "CA",
  "banana": "paloaltoCA",
  "vendor": "granicus",
  "meetings": [
    {
      "id": "meeting_123",
      "title": "City Council Meeting",
      "start": "2025-11-01T19:00:00",
      "topics": ["housing", "zoning", "transportation"],
      "participation": {
        "email": "council@cityofpaloalto.org",
        "phone": "+1-650-329-2477",
        "virtual_url": "https://zoom.us/j/123456789",
        "is_hybrid": true
      },
      "has_items": true,
      "items": [
        {
          "id": "item_456",
          "title": "Affordable Housing Development at 123 Main St",
          "summary_markdown": "Council to consider...",
          "topics": ["housing", "zoning"],
          "attachments": [
            {
              "name": "Staff Report",
              "url": "https://...",
              "type": "pdf"
            }
          ]
        }
      ]
    }
  ],
  "cached": true,
  "query": "94301",
  "type": "zipcode"
}
```

**Response (State):**
```json
{
  "success": true,
  "state": "CA",
  "cities": [
    {
      "name": "Palo Alto",
      "state": "CA",
      "banana": "paloaltoCA",
      "vendor": "granicus",
      "meeting_count": 42
    }
  ],
  "count": 150,
  "query": "California",
  "type": "state"
}
```

**Response (Not Found):**
```json
{
  "success": false,
  "message": "We're not covering that area yet, but we're always expanding!",
  "query": "12345",
  "type": "zipcode",
  "meetings": []
}
```

---

## Topic Endpoints

### Get All Topics

List all canonical topics available for search/filtering.

**Endpoint:** `GET /api/topics`

**Example:**
```bash
curl https://api.engagic.org/api/topics
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
      "canonical": "zoning",
      "display_name": "Zoning & Land Use"
    },
    {
      "canonical": "transportation",
      "display_name": "Transportation & Traffic"
    }
  ],
  "count": 16
}
```

**All Topics:**
- `housing` - Housing & Development
- `zoning` - Zoning & Land Use
- `transportation` - Transportation & Traffic
- `budget` - Budget & Finance
- `public_safety` - Public Safety
- `environment` - Environment & Sustainability
- `parks` - Parks & Recreation
- `utilities` - Utilities & Infrastructure
- `economic_development` - Economic Development
- `education` - Education & Schools
- `health` - Public Health
- `planning` - City Planning
- `permits` - Permits & Licensing
- `contracts` - Contracts & Procurement
- `appointments` - Appointments & Personnel
- `other` - Other

### Search by Topic

Find meetings discussing specific topics.

**Endpoint:** `POST /api/search/by-topic`

**Request Body:**
```json
{
  "topic": "affordable housing",
  "banana": "paloaltoCA",  // Optional: filter by city
  "limit": 50              // Optional: max results (default 50)
}
```

**Example:**
```bash
curl -X POST https://api.engagic.org/api/search/by-topic \
  -H "Content-Type: application/json" \
  -d '{"topic": "affordable housing", "banana": "paloaltoCA", "limit": 20}'
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
      "meeting": {
        "id": "meeting_123",
        "title": "City Council Meeting",
        "start": "2025-11-01T19:00:00",
        "city_name": "Palo Alto",
        "state": "CA",
        "banana": "paloaltoCA",
        "topics": ["housing", "zoning"]
      },
      "matching_items": [
        {
          "id": "item_456",
          "title": "Affordable Housing Development",
          "summary_markdown": "...",
          "topics": ["housing", "zoning"]
        }
      ]
    }
  ],
  "count": 15
}
```

**Topic Normalization:**
The API automatically normalizes topic variations:
- "affordable housing" → `housing`
- "traffic safety" → `transportation`
- "rezoning" → `zoning`

### Get Popular Topics

Get topics sorted by frequency across all meetings.

**Endpoint:** `GET /api/topics/popular`

**Query Parameters:**
- `limit` (optional) - Max topics to return (default: 20)

**Example:**
```bash
curl https://api.engagic.org/api/topics/popular?limit=10
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
    },
    {
      "topic": "budget",
      "display_name": "Budget & Finance",
      "count": 215
    }
  ],
  "count": 10
}
```

---

## Meeting Endpoints

### Get Random Best Meeting

Get a random high-quality meeting for discovery.

**Endpoint:** `GET /api/random-best-meeting`

**Example:**
```bash
curl https://api.engagic.org/api/random-best-meeting
```

**Response:**
```json
{
  "success": true,
  "meeting": {
    "id": "meeting_123",
    "title": "Planning Commission Meeting",
    "start": "2025-10-15T18:00:00",
    "city_name": "Berkeley",
    "state": "CA",
    "banana": "berkeleyCA",
    "topics": ["housing", "zoning"],
    "summary_markdown": "..."
  }
}
```

### Get Random Meeting with Items

Get a random meeting that has granular agenda items.

**Endpoint:** `GET /api/random-meeting-with-items`

**Example:**
```bash
curl https://api.engagic.org/api/random-meeting-with-items
```

**Response:**
```json
{
  "success": true,
  "meeting": { ... },
  "items": [
    {
      "id": "item_123",
      "title": "...",
      "summary_markdown": "...",
      "topics": ["housing"]
    }
  ]
}
```

---

## Vote Endpoints

Endpoints for accessing voting records, tallies, and council member voting history.

### Get Matter Votes

Get all votes on a matter across all meetings with per-meeting tallies.

**Endpoint:** `GET /api/matters/{matter_id}/votes`

**Example:**
```bash
curl https://api.engagic.org/api/matters/nashvilleTN_BL2025-1098/votes
```

**Response:**
```json
{
  "success": true,
  "matter_id": "nashvilleTN_BL2025-1098",
  "matter_title": "Budget Amendment FY2025",
  "votes": [
    {
      "council_member_id": "nashvilleTN_a3f2c8d1",
      "matter_id": "nashvilleTN_BL2025-1098",
      "meeting_id": "nashvilleTN_2025-11-10",
      "vote": "yes",
      "vote_date": "2025-11-10T00:00:00"
    }
  ],
  "votes_by_meeting": [
    {
      "meeting_id": "nashvilleTN_2025-11-10",
      "meeting_title": "City Council - Regular Meeting",
      "meeting_date": "2025-11-10T18:00:00",
      "committee": "Budget Committee",
      "votes": [...],
      "computed_tally": {"yes": 25, "no": 5, "abstain": 2, "absent": 3},
      "vote_outcome": "passed"
    }
  ],
  "tally": {"yes": 25, "no": 5, "abstain": 2, "absent": 3},
  "outcomes": [...]
}
```

### Get Meeting Votes

Get all votes cast in a specific meeting, grouped by matter.

**Endpoint:** `GET /api/meetings/{meeting_id}/votes`

**Example:**
```bash
curl https://api.engagic.org/api/meetings/nashvilleTN_2025-11-10/votes
```

**Response:**
```json
{
  "success": true,
  "meeting_id": "nashvilleTN_2025-11-10",
  "meeting_title": "City Council - Regular Meeting",
  "meeting_date": "2025-11-10T18:00:00",
  "matters_with_votes": [
    {
      "matter_id": "nashvilleTN_BL2025-1098",
      "matter_title": "Budget Amendment FY2025",
      "matter_file": "BL2025-1098",
      "votes": [...],
      "tally": {"yes": 25, "no": 5},
      "outcome": "passed"
    }
  ],
  "total": 35
}
```

### Get Council Member Votes

Get voting record for a specific council member.

**Endpoint:** `GET /api/council-members/{member_id}/votes`

**Query Parameters:**
- `limit` (optional) - Max votes to return (default: 100)

**Example:**
```bash
curl "https://api.engagic.org/api/council-members/nashvilleTN_a3f2c8d1/votes?limit=50"
```

**Response:**
```json
{
  "success": true,
  "member": {
    "id": "nashvilleTN_a3f2c8d1",
    "name": "Freddie O'Connell",
    "title": "Council Member",
    "district": "District 19",
    "vote_count": 312
  },
  "voting_record": [...],
  "total": 50,
  "statistics": {"yes": 280, "no": 20, "abstain": 8, "absent": 4}
}
```

### Get City Council Roster

Get all council members for a city.

**Endpoint:** `GET /api/city/{banana}/council-members`

**Example:**
```bash
curl https://api.engagic.org/api/city/nashvilleTN/council-members
```

**Response:**
```json
{
  "success": true,
  "city_name": "Nashville",
  "state": "TN",
  "banana": "nashvilleTN",
  "council_members": [
    {
      "id": "nashvilleTN_a3f2c8d1",
      "name": "Freddie O'Connell",
      "title": "Mayor",
      "district": null,
      "status": "active",
      "sponsorship_count": 45,
      "vote_count": 312
    }
  ],
  "total": 40
}
```

---

## Committee Endpoints

Endpoints for committee information, rosters, and voting history.

### Get City Committees

Get all committees for a city.

**Endpoint:** `GET /api/city/{banana}/committees`

**Query Parameters:**
- `status` (optional) - Filter by status: `active`, `inactive`

**Example:**
```bash
curl "https://api.engagic.org/api/city/sanfranciscoCA/committees?status=active"
```

**Response:**
```json
{
  "success": true,
  "city_name": "San Francisco",
  "state": "CA",
  "banana": "sanfranciscoCA",
  "committees": [
    {
      "id": "sanfranciscoCA_b7d4e9f2",
      "name": "Planning Commission",
      "description": "Oversees land use and development",
      "status": "active",
      "member_count": 7
    }
  ],
  "total": 15
}
```

### Get Committee Details

Get details for a specific committee.

**Endpoint:** `GET /api/committees/{committee_id}`

**Example:**
```bash
curl https://api.engagic.org/api/committees/sanfranciscoCA_b7d4e9f2
```

**Response:**
```json
{
  "success": true,
  "committee": {
    "id": "sanfranciscoCA_b7d4e9f2",
    "name": "Planning Commission",
    "description": "Oversees land use and development",
    "status": "active",
    "banana": "sanfranciscoCA"
  },
  "city_name": "San Francisco",
  "state": "CA",
  "members": [...],
  "member_count": 7
}
```

### Get Committee Members

Get current or historical roster for a committee.

**Endpoint:** `GET /api/committees/{committee_id}/members`

**Query Parameters:**
- `active_only` (optional) - Only current members (default: true)
- `as_of` (optional) - Historical date (ISO format)

**Example:**
```bash
# Current roster
curl https://api.engagic.org/api/committees/sanfranciscoCA_b7d4e9f2/members

# Historical roster as of June 2024
curl "https://api.engagic.org/api/committees/sanfranciscoCA_b7d4e9f2/members?as_of=2024-06-01"
```

**Response:**
```json
{
  "success": true,
  "committee_id": "sanfranciscoCA_b7d4e9f2",
  "committee_name": "Planning Commission",
  "as_of": null,
  "members": [
    {
      "council_member_id": "sanfranciscoCA_c8e5f0a3",
      "name": "Jane Smith",
      "role": "Chair",
      "joined_at": "2024-01-15T00:00:00"
    }
  ],
  "total": 7
}
```

### Get Committee Voting History

Get voting history for a committee.

**Endpoint:** `GET /api/committees/{committee_id}/votes`

**Query Parameters:**
- `limit` (optional) - Max votes to return (default: 50, max: 200)

**Example:**
```bash
curl "https://api.engagic.org/api/committees/sanfranciscoCA_b7d4e9f2/votes?limit=20"
```

**Response:**
```json
{
  "success": true,
  "committee_id": "sanfranciscoCA_b7d4e9f2",
  "committee_name": "Planning Commission",
  "votes": [...],
  "total": 20
}
```

### Get Member's Committee Assignments

Get committees a council member serves on.

**Endpoint:** `GET /api/council-members/{member_id}/committees`

**Query Parameters:**
- `active_only` (optional) - Only current assignments (default: true)

**Example:**
```bash
curl https://api.engagic.org/api/council-members/sanfranciscoCA_c8e5f0a3/committees
```

**Response:**
```json
{
  "success": true,
  "member_id": "sanfranciscoCA_c8e5f0a3",
  "member_name": "Jane Smith",
  "committees": [
    {
      "committee_id": "sanfranciscoCA_b7d4e9f2",
      "name": "Planning Commission",
      "role": "Chair",
      "joined_at": "2024-01-15T00:00:00"
    }
  ],
  "total": 3
}
```

---

## Engagement Endpoints

User engagement tracking: watches, activity logging, trending content.

### Watch Entity (Requires Auth)

Add entity to user's watch list.

**Endpoint:** `POST /api/watch/{entity_type}/{entity_id}`

**Entity Types:** `matter`, `meeting`, `topic`, `city`, `council_member`

**Example:**
```bash
curl -X POST https://api.engagic.org/api/watch/matter/nashvilleTN_BL2025-1098 \
  -H "Authorization: Bearer your-jwt-token"
```

**Response:**
```json
{
  "success": true,
  "status": "watching"
}
```

### Unwatch Entity (Requires Auth)

Remove entity from user's watch list.

**Endpoint:** `DELETE /api/watch/{entity_type}/{entity_id}`

**Example:**
```bash
curl -X DELETE https://api.engagic.org/api/watch/matter/nashvilleTN_BL2025-1098 \
  -H "Authorization: Bearer your-jwt-token"
```

**Response:**
```json
{
  "success": true,
  "status": "unwatched"
}
```

### Get User's Watch List (Requires Auth)

Get entities the user is watching.

**Endpoint:** `GET /api/me/watching`

**Query Parameters:**
- `entity_type` (optional) - Filter by entity type

**Example:**
```bash
curl "https://api.engagic.org/api/me/watching?entity_type=matter" \
  -H "Authorization: Bearer your-jwt-token"
```

**Response:**
```json
{
  "success": true,
  "watches": [
    {
      "id": 123,
      "entity_type": "matter",
      "entity_id": "nashvilleTN_BL2025-1098",
      "created_at": "2025-11-10T12:00:00"
    }
  ],
  "total": 5
}
```

### Get Trending Matters

Get matters with highest engagement.

**Endpoint:** `GET /api/trending/matters`

**Query Parameters:**
- `limit` (optional) - Max results (default: 20, max: 100)

**Example:**
```bash
curl "https://api.engagic.org/api/trending/matters?limit=10"
```

**Response:**
```json
{
  "success": true,
  "trending": [
    {
      "matter_id": "nashvilleTN_BL2025-1098",
      "title": "Budget Amendment FY2025",
      "engagement": 145,
      "unique_users": 42,
      "status": "active"
    }
  ]
}
```

### Get Matter Engagement

Get engagement stats for a matter.

**Endpoint:** `GET /api/matters/{matter_id}/engagement`

**Example:**
```bash
curl https://api.engagic.org/api/matters/nashvilleTN_BL2025-1098/engagement
```

**Response:**
```json
{
  "success": true,
  "matter_id": "nashvilleTN_BL2025-1098",
  "watch_count": 42,
  "is_watching": false
}
```

### Get Meeting Engagement

Get engagement stats for a meeting.

**Endpoint:** `GET /api/meetings/{meeting_id}/engagement`

**Example:**
```bash
curl https://api.engagic.org/api/meetings/nashvilleTN_2025-11-10/engagement
```

**Response:**
```json
{
  "success": true,
  "meeting_id": "nashvilleTN_2025-11-10",
  "watch_count": 25,
  "is_watching": false
}
```

### Log View (Analytics)

Log a page view for analytics tracking.

**Endpoint:** `POST /api/activity/view/{entity_type}/{entity_id}`

Works for both authenticated and anonymous users.

**Example:**
```bash
curl -X POST https://api.engagic.org/api/activity/view/meeting/nashvilleTN_2025-11-10
```

**Response:**
```json
{
  "success": true
}
```

### Log Search (Analytics)

Log a search query for analytics tracking.

**Endpoint:** `POST /api/activity/search`

**Query Parameters:**
- `query` - The search query

**Example:**
```bash
curl -X POST "https://api.engagic.org/api/activity/search?query=affordable%20housing"
```

**Response:**
```json
{
  "success": true
}
```

---

## Feedback Endpoints

User feedback for quality improvement: ratings and issue reporting.

### Rate Entity

Submit a rating (1-5 stars) for an entity.

**Endpoint:** `POST /api/rate/{entity_type}/{entity_id}`

**Entity Types:** `item`, `meeting`, `matter`

**Request Body:**
```json
{
  "rating": 4
}
```

Works for authenticated users or anonymous users with `session_id` cookie.

**Example:**
```bash
curl -X POST https://api.engagic.org/api/rate/item/paloaltoCA_2025-11-10_item_5 \
  -H "Content-Type: application/json" \
  -d '{"rating": 4}'
```

**Response:**
```json
{
  "success": true,
  "status": "rated"
}
```

### Report Issue

Report an issue with a summary (inaccurate, incomplete, misleading).

**Endpoint:** `POST /api/report/{entity_type}/{entity_id}`

**Request Body:**
```json
{
  "issue_type": "inaccurate",
  "description": "Summary misses key budget details about the 5% increase"
}
```

**Issue Types:** `inaccurate`, `incomplete`, `misleading`, `other`

**Example:**
```bash
curl -X POST https://api.engagic.org/api/report/item/paloaltoCA_2025-11-10_item_5 \
  -H "Content-Type: application/json" \
  -d '{"issue_type": "incomplete", "description": "Missing info about the amendment..."}'
```

**Response:**
```json
{
  "success": true,
  "issue_id": 123
}
```

### Get Entity Rating

Get rating statistics for an entity.

**Endpoint:** `GET /api/{entity_type}/{entity_id}/rating`

**Example:**
```bash
curl https://api.engagic.org/api/item/paloaltoCA_2025-11-10_item_5/rating
```

**Response:**
```json
{
  "success": true,
  "entity_type": "item",
  "entity_id": "paloaltoCA_2025-11-10_item_5",
  "avg_rating": 3.8,
  "rating_count": 25,
  "distribution": {"1": 2, "2": 3, "3": 5, "4": 8, "5": 7},
  "user_rating": 4
}
```

### Get Entity Issues

Get issues reported for an entity.

**Endpoint:** `GET /api/{entity_type}/{entity_id}/issues`

**Query Parameters:**
- `status` (optional) - Filter by status: `open`, `resolved`, `dismissed`

**Example:**
```bash
curl "https://api.engagic.org/api/item/paloaltoCA_2025-11-10_item_5/issues?status=open"
```

**Response:**
```json
{
  "success": true,
  "entity_type": "item",
  "entity_id": "paloaltoCA_2025-11-10_item_5",
  "open_issue_count": 2,
  "issues": [
    {
      "id": 123,
      "issue_type": "incomplete",
      "description": "Missing info about amendment...",
      "status": "open",
      "created_at": "2025-11-10T14:00:00"
    }
  ]
}
```

### Get Open Issues (Admin)

Get all unresolved issues for admin review.

**Endpoint:** `GET /api/admin/issues`

**Requires:** Authentication

**Query Parameters:**
- `limit` (optional) - Max issues (default: 100)

**Example:**
```bash
curl https://api.engagic.org/api/admin/issues \
  -H "Authorization: Bearer your-jwt-token"
```

**Response:**
```json
{
  "success": true,
  "issues": [...],
  "total": 12
}
```

### Resolve Issue (Admin)

Mark an issue as resolved or dismissed.

**Endpoint:** `POST /api/admin/issues/{issue_id}/resolve`

**Requires:** Authentication

**Request Body:**
```json
{
  "status": "resolved",
  "admin_notes": "Fixed in reprocessing batch #42"
}
```

**Example:**
```bash
curl -X POST https://api.engagic.org/api/admin/issues/123/resolve \
  -H "Authorization: Bearer your-jwt-token" \
  -H "Content-Type: application/json" \
  -d '{"status": "resolved", "admin_notes": "Fixed"}'
```

**Response:**
```json
{
  "success": true,
  "status": "resolved"
}
```

### Get Low-Rated Entities (Admin)

Get entities with low ratings for reprocessing consideration.

**Endpoint:** `GET /api/admin/low-rated`

**Requires:** Authentication

**Query Parameters:**
- `threshold` (optional) - Rating threshold (default: 2.5)
- `min_ratings` (optional) - Minimum ratings required (default: 3)

**Example:**
```bash
curl "https://api.engagic.org/api/admin/low-rated?threshold=2.0&min_ratings=5" \
  -H "Authorization: Bearer your-jwt-token"
```

**Response:**
```json
{
  "success": true,
  "threshold": 2.0,
  "min_ratings": 5,
  "entities": [
    {"entity_type": "item", "entity_id": "paloaltoCA_2025-11-10_item_3"}
  ],
  "total": 8
}
```

---

## System Endpoints

### Health Check

Check if the API is operational.

**Endpoint:** `GET /api/health`

**Example:**
```bash
curl https://api.engagic.org/api/health
```

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-10-31T12:34:56Z",
  "database": "connected",
  "version": "1.0.0"
}
```

### Stats

Get cache statistics and system metrics.

**Endpoint:** `GET /api/stats`

**Example:**
```bash
curl https://api.engagic.org/api/stats
```

**Response:**
```json
{
  "success": true,
  "total_cities": 527,
  "total_meetings": 9847,
  "total_items": 42156,
  "cache_hit_rate": 0.94,
  "avg_response_time_ms": 45
}
```

### Queue Stats

Get processing queue statistics.

**Endpoint:** `GET /api/queue-stats`

**Example:**
```bash
curl https://api.engagic.org/api/queue-stats
```

**Response:**
```json
{
  "success": true,
  "pending_jobs": 142,
  "processing_jobs": 3,
  "completed_jobs": 8924,
  "failed_jobs": 12
}
```

### Metrics

Get detailed system metrics (Prometheus-compatible).

**Endpoint:** `GET /api/metrics`

**Example:**
```bash
curl https://api.engagic.org/api/metrics
```

**Response:**
```json
{
  "requests_total": 15234,
  "requests_by_endpoint": {
    "/api/search": 8421,
    "/api/topics": 3142
  },
  "cache_hits": 14321,
  "cache_misses": 913
}
```

### Analytics

Get usage analytics and insights.

**Endpoint:** `GET /api/analytics`

**Example:**
```bash
curl https://api.engagic.org/api/analytics
```

**Response:**
```json
{
  "success": true,
  "top_searched_cities": [
    {"banana": "paloaltoCA", "count": 842},
    {"banana": "berkeleyCA", "count": 721}
  ],
  "top_topics": [
    {"topic": "housing", "count": 342},
    {"topic": "zoning", "count": 278}
  ]
}
```

---

## Admin Endpoints

**Authentication Required:** `X-Admin-Token` header

### Sync City

Trigger immediate sync for a specific city.

**Endpoint:** `POST /api/admin/sync-city/{banana}`

**Example:**
```bash
curl -X POST https://api.engagic.org/api/admin/sync-city/paloaltoCA \
  -H "X-Admin-Token: your-admin-token"
```

**Response:**
```json
{
  "success": true,
  "message": "Sync triggered for paloaltoCA",
  "banana": "paloaltoCA"
}
```

### Process Meeting

Trigger processing for a specific meeting.

**Endpoint:** `POST /api/admin/process-meeting`

**Request Body:**
```json
{
  "meeting_id": "meeting_123"
}
```

**Example:**
```bash
curl -X POST https://api.engagic.org/api/admin/process-meeting \
  -H "X-Admin-Token: your-admin-token" \
  -H "Content-Type: application/json" \
  -d '{"meeting_id": "meeting_123"}'
```

**Response:**
```json
{
  "success": true,
  "message": "Processing queued for meeting_123"
}
```

---

## Error Codes

### HTTP Status Codes

| Code | Meaning | Description |
|------|---------|-------------|
| 200 | OK | Request successful |
| 400 | Bad Request | Invalid parameters or malformed request |
| 401 | Unauthorized | Missing or invalid admin token |
| 404 | Not Found | Resource not found |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Server error |

### Common Errors

**Empty query:**
```json
{
  "detail": "Search query cannot be empty"
}
```

**Rate limit exceeded:**
```json
{
  "detail": "Rate limit exceeded. Try again in 42 seconds."
}
```

**Topic not found:**
```json
{
  "detail": "Topic 'invalid-topic' not recognized"
}
```

**Admin auth failed:**
```json
{
  "detail": "Invalid admin token"
}
```

---

## Best Practices

### Cache-First Architecture
- API never fetches live data
- Background daemon syncs cities every 72 hours
- Always check `cached` field in response
- Empty meetings array means data not synced yet

### Topic Search
- Use normalized topic names from `/api/topics`
- API automatically normalizes variations
- Filter by city using `banana` parameter
- Limit results to improve response time

### Error Handling
```javascript
try {
  const response = await fetch('https://api.engagic.org/api/search', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({query: '94301'})
  });

  if (response.status === 429) {
    // Rate limited - wait and retry
    const retryAfter = response.headers.get('Retry-After');
    await sleep(retryAfter * 1000);
    // retry...
  }

  const data = await response.json();
  if (!data.success) {
    // Handle unsuccessful response
  }
} catch (error) {
  // Network or parsing error
}
```

---

## Examples

### Get all housing meetings in Palo Alto
```bash
curl -X POST https://api.engagic.org/api/search/by-topic \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "housing",
    "banana": "paloaltoCA",
    "limit": 20
  }'
```

### Find cities in California
```bash
curl -X POST https://api.engagic.org/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "California"}'
```

### Check system health and stats
```bash
curl https://api.engagic.org/api/health
curl https://api.engagic.org/api/stats
```

---

## Support

**Questions:** See [documentation](README.md)
**Issues:** Create GitHub issue with request details

---

**Last Updated:** December 3, 2025 (Added Vote, Committee, Engagement, and Feedback endpoints - 24 new endpoints documented)

**See Also:** [../server/README.md](../server/README.md) for server code architecture and implementation
