# Frontend API Integration Layer

**Last Updated:** 2025-11-02
**API Base URL:** `https://api.engagic.org`
**Total Lines:** 982 TypeScript lines
**Retry Strategy:** 3 attempts with 1s delay

---

## Table of Contents

1. [Overview](#overview)
2. [API Client](#api-client)
3. [Endpoints](#endpoints)
4. [Error Handling](#error-handling)
5. [Type System](#type-system)
6. [Configuration](#configuration)

---

## Overview

The API layer is a thin, type-safe wrapper around `fetch()` with automatic retry logic and error handling. We don't use external HTTP libraries (axios, etc.) to minimize bundle size.

### Architecture

```
Component/Load Function
    ↓
  apiClient.searchMeetings()
    ↓
  fetchWithRetry() [3 attempts, 1s delay]
    ↓
  fetch() [native browser API]
    ↓
  api.engagic.org [FastAPI backend]
```

### Key Features

- **Automatic retries** - 3 attempts with exponential backoff
- **Timeout protection** - 30s request timeout
- **Type safety** - Full TypeScript coverage
- **Error classification** - Network vs API vs timeout errors
- **Zero dependencies** - Pure fetch(), no axios

---

## API Client

**Location:** `lib/api/api-client.ts` (223 lines)

### fetchWithRetry()

**Core retry mechanism:**

```typescript
async function fetchWithRetry(
  url: string,
  options: RequestInit = {},
  retries: number = config.maxRetries  // Default: 3
): Promise<Response> {
  const controller = new AbortController();
  const timeout = setTimeout(
    () => controller.abort(),
    config.requestTimeout  // 30s
  );

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal
    });

    clearTimeout(timeout);

    // Success
    if (response.ok) {
      return response;
    }

    // Rate limited (don't retry)
    if (response.status === 429) {
      throw new ApiError(errorMessages.rateLimit, 429, true);
    }

    // Not found (don't retry)
    if (response.status === 404) {
      throw new ApiError(errorMessages.notFound, 404, false);
    }

    // Server error (retry)
    if (response.status >= 500 && retries > 0) {
      await new Promise(resolve => setTimeout(resolve, config.retryDelay));
      return fetchWithRetry(url, options, retries - 1);
    }

    throw new ApiError(errorMessages.generic, response.status, false);

  } catch (error) {
    if (error.name === 'AbortError') {
      // Timeout - retry
      if (retries > 0) {
        await new Promise(resolve => setTimeout(resolve, config.retryDelay));
        return fetchWithRetry(url, options, retries - 1);
      }
      throw new NetworkError(errorMessages.timeout);
    }

    // Network error - don't retry (user offline)
    if (error.message.includes('fetch')) {
      throw new NetworkError(errorMessages.network);
    }

    throw error;
  }
}
```

**Retry logic:**

| Error Type | Retry? | Why |
|------------|--------|-----|
| 429 (Rate Limit) | ❌ No | User needs to wait, retrying makes it worse |
| 404 (Not Found) | ❌ No | Data doesn't exist, retry won't help |
| 500-599 (Server) | ✅ Yes | Temporary issue, may recover |
| Timeout | ✅ Yes | Network hiccup, may recover |
| Network error | ❌ No | User offline, retry pointless |

### apiClient Object

**Public API:**

```typescript
export const apiClient = {
  searchMeetings(query: string): Promise<SearchResult>
  getAnalytics(): Promise<AnalyticsData>
  getRandomBestMeeting(): Promise<RandomMeetingResponse>
  getRandomMeetingWithItems(): Promise<RandomMeetingWithItemsResponse>
  searchByTopic(topic: string, banana?: string, limit?: number): Promise<TopicSearchResult>
  getMeeting(meetingId: number): Promise<MeetingResponse>
  getTicker(): Promise<TickerResponse>
};
```

---

## Endpoints

### 1. Search Meetings

**Method:** `apiClient.searchMeetings(query: string)`
**Endpoint:** `POST /api/search`
**Purpose:** Search for cities and their meetings

**Request:**
```typescript
{
  query: "Palo Alto, CA"  // City name, state, or zipcode
}
```

**Response:**
```typescript
// Success - Single city
{
  success: true,
  city_name: "Palo Alto",
  state: "CA",
  banana: "paloaltoCA",
  meetings: Meeting[],
  cached: true,
  query: "Palo Alto, CA",
  type: "city"
}

// Success - Multiple cities (ambiguous)
{
  success: false,
  ambiguous: true,
  message: "Multiple cities found",
  city_options: CityOption[]
}

// Error
{
  success: false,
  message: "City not found"
}
```

**Usage:**
```typescript
import { searchMeetings } from '$lib/api/index';

const result = await searchMeetings("Austin, TX");
if (result.success) {
  console.log(result.meetings);
}
```

---

### 2. Get Analytics

**Method:** `apiClient.getAnalytics()`
**Endpoint:** `GET /api/analytics`
**Purpose:** Fetch site-wide statistics

**Response:**
```typescript
{
  real_metrics: {
    cities_covered: 374,
    agendas_summarized: 1234,
    meetings_tracked: 10000
  }
}
```

**Usage:**
```typescript
import { getAnalytics } from '$lib/api/index';

const analytics = await getAnalytics();
console.log(`${analytics.real_metrics.cities_covered} cities tracked`);
```

---

### 3. Get Random Best Meeting

**Method:** `apiClient.getRandomBestMeeting()`
**Endpoint:** `GET /api/random-best-meeting`
**Purpose:** Get a random high-quality meeting (for discovery)

**Response:**
```typescript
{
  meeting: {
    id: 123,
    banana: "paloaltoCA",
    title: "City Council",
    date: "2024-11-02T19:00:00",
    packet_url: "https://...",
    quality_score: 0.95
  }
}
```

**Quality score based on:**
- Has AI summary
- Has agenda items
- Has participation info
- Recent (not too old)

**Usage:**
```typescript
const result = await apiClient.getRandomBestMeeting();
const meeting = result.meeting;
goto(`/${meeting.banana}/${generateMeetingSlug(meeting)}`);
```

---

### 4. Get Random Meeting with Items

**Method:** `apiClient.getRandomMeetingWithItems()`
**Endpoint:** `GET /api/random-meeting-with-items`
**Purpose:** Get a random meeting with structured agenda items

**Response:**
```typescript
{
  meeting: {
    id: 456,
    banana: "austinTX",
    title: "Planning Commission",
    date: "2024-11-05T18:00:00",
    item_count: 12
  }
}
```

**Filters:**
- Only meetings with `items` array populated
- Excludes monolithic packet meetings

**Usage:**
```typescript
const result = await apiClient.getRandomMeetingWithItems();
goto(`/${result.meeting.banana}/${generateMeetingSlug(result.meeting)}`);
```

---

### 5. Search by Topic

**Method:** `apiClient.searchByTopic(topic, banana?, limit?)`
**Endpoint:** `POST /api/search/by-topic`
**Purpose:** Find meetings discussing specific topics

**Request:**
```typescript
{
  topic: "housing",
  banana: "paloaltoCA",  // Optional: filter to city
  limit: 50              // Optional: result limit
}
```

**Response:**
```typescript
{
  success: true,
  topic: "housing",
  meetings: Meeting[]
}
```

**Available topics:**
- housing
- zoning
- budget
- transportation
- public-safety
- parks-recreation
- environment
- utilities
- education
- development
- infrastructure
- cannabis
- elections
- labor
- homelessness
- other

**Usage:**
```typescript
import { searchByTopic } from '$lib/api/index';

const result = await searchByTopic("housing", "paloaltoCA", 20);
console.log(`Found ${result.meetings.length} meetings about housing`);
```

---

### 6. Get Meeting

**Method:** `apiClient.getMeeting(meetingId)`
**Endpoint:** `GET /api/meeting/{id}`
**Purpose:** Fetch single meeting by ID (optimized)

**Response:**
```typescript
{
  success: true,
  meeting: Meeting,
  city_name: "Palo Alto",
  state: "CA",
  banana: "paloaltoCA"
}
```

**Usage:**
```typescript
import { getMeeting } from '$lib/api/index';

const meetingId = extractMeetingIdFromSlug(meeting_slug);
const result = await getMeeting(meetingId);
console.log(result.meeting.title);
```

**Performance benefit:**
- Direct ID lookup (no search)
- Single meeting returned (not full list)
- Faster than `searchMeetings()` + filter

---

### 7. Get Ticker

**Method:** `apiClient.getTicker()`
**Endpoint:** `GET /api/ticker`
**Purpose:** Fetch recent interesting meetings for homepage ticker

**Response:**
```typescript
{
  success: true,
  items: [
    {
      city: "Palo Alto",
      date: "Nov 2",
      excerpt: "Discussed new housing development...",
      url: "/paloaltoCA/123-city-council-nov-2-2024"
    },
    // ... more items
  ]
}
```

**Usage:**
```typescript
const ticker = await apiClient.getTicker();
if (ticker.success) {
  console.log(ticker.items);
}
```

---

## Error Handling

### Error Types

**Three error classes:**

```typescript
// API errors (4xx, 5xx)
class ApiError extends Error {
  statusCode: number;
  isRetryable: boolean;
}

// Network errors (offline, timeout)
class NetworkError extends Error {}

// Type guard functions
export function isNetworkError(error: unknown): error is NetworkError
export function isApiError(error: unknown): error is ApiError
```

### Error Messages

**Predefined user-friendly messages:**

```typescript
export const errorMessages = {
  network: 'Connection error. Please check your internet and try again.',
  rateLimit: 'Too many requests. Please wait a moment and try again.',
  notFound: 'No meetings found for this location.',
  noAgenda: 'Agenda not yet available. Packets are typically posted within 48 hours of the meeting.',
  generic: 'Something went wrong. Please try again.',
  timeout: 'Request timed out. Please try again.',
};
```

### Usage in Components

**Catch and display errors:**

```svelte
<script>
  import { apiClient } from '$lib/api/api-client';
  import { isNetworkError } from '$lib/api/types';

  let error = $state('');

  async function search() {
    try {
      const result = await apiClient.searchMeetings(query);
      // Handle success
    } catch (err) {
      if (isNetworkError(err)) {
        error = 'Check your internet connection';
      } else {
        error = err.message || 'Search failed';
      }
    }
  }
</script>

{#if error}
  <div class="error">{error}</div>
{/if}
```

**Or let load functions handle it:**

```typescript
export const load: PageLoad = async () => {
  const result = await searchMeetings(query);

  if (!result.success) {
    throw error(404, result.message);  // Triggers +error.svelte
  }

  return { result };
};
```

---

## Type System

**Location:** `lib/api/types.ts` (186 lines)

### Core Types

```typescript
// Meeting data
interface Meeting {
  id: number;
  banana: string;
  title: string;
  date: string | null;
  packet_url?: string;
  agenda_url?: string;
  summary?: string;
  topics?: string[];
  items?: AgendaItem[];
  meeting_status?: string;  // "cancelled", "postponed"
  participation?: ParticipationInfo;
}

// Agenda item (structured meetings)
interface AgendaItem {
  id: number;
  meeting_id: number;
  item_number: string;
  title: string;
  pdf_url?: string;
  page_count?: number;
  summary?: string;
  thinking?: string;
  topics?: string[];
}

// Participation info
interface ParticipationInfo {
  zoom_link?: string;
  phone_number?: string;
  email?: string;
}

// City option (ambiguous search)
interface CityOption {
  display_name: string;
  city_name: string;
  state: string;
  banana: string;
  total_meetings: number;
  meetings_with_packet: number;
  summarized_meetings: number;
}
```

### Search Result Types

```typescript
// Successful city search
interface SearchResultSuccess {
  success: true;
  city_name: string;
  state: string;
  banana: string;
  meetings: Meeting[];
  cached: boolean;
  query: string;
  type: 'city' | 'zipcode';
}

// Ambiguous search (multiple cities)
interface SearchResultAmbiguous {
  success: false;
  ambiguous: true;
  message: string;
  city_options: CityOption[];
}

// Failed search
interface SearchResultFailure {
  success: false;
  message: string;
}

// Union type
type SearchResult =
  | SearchResultSuccess
  | SearchResultAmbiguous
  | SearchResultFailure;
```

### Type Guards

**Narrow search results:**

```typescript
export function isSearchSuccess(result: SearchResult): result is SearchResultSuccess {
  return result.success === true;
}

export function isSearchAmbiguous(result: SearchResult): result is SearchResultAmbiguous {
  return result.success === false && result.ambiguous === true;
}

export function isSearchFailure(result: SearchResult): result is SearchResultFailure {
  return result.success === false && result.ambiguous !== true;
}
```

**Usage:**

```typescript
const result = await searchMeetings(query);

if (isSearchSuccess(result)) {
  // TypeScript knows: result.city_name, result.meetings exist
  console.log(result.city_name);
} else if (isSearchAmbiguous(result)) {
  // TypeScript knows: result.city_options exists
  console.log(result.city_options);
} else {
  // TypeScript knows: result.message exists
  console.error(result.message);
}
```

---

## Configuration

**Location:** `lib/api/config.ts` (18 lines)

```typescript
export const config = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL || 'https://api.engagic.org',
  maxRetries: 3,
  retryDelay: 1000,      // 1 second between retries
  requestTimeout: 30000,  // 30 second timeout
  debounceDelay: 300,    // Debounce user input (not used yet)
} as const;
```

### Environment Variables

**`.env` file (not committed):**

```bash
VITE_API_BASE_URL=https://api.engagic.org
```

**Development override:**

```bash
VITE_API_BASE_URL=http://localhost:8000
```

**Access in code:**

```typescript
const apiUrl = import.meta.env.VITE_API_BASE_URL;
```

**Why `VITE_` prefix?**
- Vite only exposes env vars with this prefix to client code
- Prevents accidental exposure of secrets
- Other vars (without prefix) only available in server code

---

## API Client Best Practices

### DO:

✅ Use `apiClient` methods instead of direct `fetch()`
✅ Handle errors gracefully
✅ Use type guards to narrow results
✅ Let load functions handle API calls (not `onMount`)
✅ Pass errors to +error.svelte when appropriate

### DON'T:

❌ Call APIs from components (use load functions)
❌ Ignore error states
❌ Assume all searches succeed
❌ Forget to handle ambiguous results
❌ Use `any` types (defeats purpose of TypeScript)
❌ Make redundant API calls (check cache first)

---

## Future Improvements

### Short Term

1. **Request deduplication** - Don't make identical concurrent requests
2. **Cache layer** - In-memory cache for repeated requests
3. **Request cancellation** - Cancel stale requests on navigation

### Long Term

1. **WebSocket support** - Real-time updates for new meetings
2. **Optimistic updates** - Update UI before API confirms
3. **GraphQL migration** - More flexible data fetching (if needed)

---

**Last Updated:** 2025-11-02
**See Also:**
- [FRONTEND.md](./FRONTEND.md) for architecture overview
- Backend API documentation at `/api/docs` (FastAPI Swagger)
