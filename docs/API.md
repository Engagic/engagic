# Engagic API Reference

Complete reference for the Engagic public API endpoints.

**For server code architecture and implementation details, see:** [../server/README.md](../server/README.md)

**Base URL (Production):** `https://api.engagic.org`
**Base URL (Local):** `http://localhost:8000`

**Version:** v1
**Last Updated:** November 11, 2025

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

**Limit:** 30 requests per 60 seconds per IP address

**Headers:**
```http
X-RateLimit-Limit: 30
X-RateLimit-Remaining: 25
X-RateLimit-Reset: 1698765432
```

**Rate limit exceeded response:**
```json
{
  "detail": "Rate limit exceeded. Try again in X seconds."
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

**Last Updated:** November 11, 2025

**See Also:** [../server/README.md](../server/README.md) for server code architecture and implementation
