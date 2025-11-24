# Frontend Routing & Navigation

**Last Updated:** 2025-11-02
**Router:** SvelteKit file-based routing
**Routes:** 4 pages + 1 dynamic city page + 1 dynamic meeting page

---

## Table of Contents

1. [Route Structure](#route-structure)
2. [File-Based Routing](#file-based-routing)
3. [Load Functions](#load-functions)
4. [Navigation Patterns](#navigation-patterns)
5. [URL Structure](#url-structure)
6. [Error Handling](#error-handling)

---

## Route Structure

```
/                          → Homepage (search, random meetings)
/about                     → About page
/[city_url]                → City meetings list (dynamic)
/[city_url]/[meeting_slug] → Meeting detail page (dynamic)
```

### Route Files

```
routes/
├── +layout.svelte         # Root layout (wraps all pages)
├── +page.svelte           # Homepage
├── +page.ts               # Homepage data loader
│
├── about/
│   └── +page.svelte       # Static about page
│
└── [city_url]/            # Dynamic city route
    ├── +page.svelte       # City meetings list
    ├── +page.ts           # City data loader
    ├── +error.svelte      # Error boundary (404s, etc.)
    │
    └── [meeting_slug]/    # Dynamic meeting route
        └── +page.svelte   # Meeting detail
```

---

## File-Based Routing

SvelteKit uses **file structure as routing convention:**

### Special Files

| Filename | Purpose |
|----------|---------|
| `+page.svelte` | Page component (the actual UI) |
| `+page.ts` | Client-side load function (fetch data before render) |
| `+page.server.ts` | Server-side load function (we don't use these) |
| `+layout.svelte` | Layout wrapper (navigation bar, footer, etc.) |
| `+layout.ts` | Layout data loader |
| `+error.svelte` | Error boundary (handles load function errors) |
| `[param]` | Dynamic route parameter |

### Dynamic Routes

**Brackets = dynamic parameters:**

```
routes/[city_url]/+page.svelte
→ Matches: /paloaltoCA, /austinTX, /any-string

routes/[city_url]/[meeting_slug]/+page.svelte
→ Matches: /paloaltoCA/123-city-council-nov-2-2024
```

**Access parameters:**

```svelte
<script>
  import { page } from '$app/stores';

  const cityUrl = $page.params.city_url;
  const meetingSlug = $page.params.meeting_slug;
</script>
```

---

## Load Functions

**Load functions run BEFORE page renders:**

### Homepage (`+page.ts`)

```typescript
import type { PageLoad } from './$types';
import { apiClient } from '$lib/api/api-client';
import { getAnalytics } from '$lib/api/index';

export const load: PageLoad = async ({ setHeaders }) => {
  // Fetch analytics data
  const analytics = await getAnalytics();

  // Cache for 5 minutes (analytics doesn't change often)
  setHeaders({
    'cache-control': 'public, max-age=300'
  });

  return {
    analytics
  };
};
```

**Key features:**
- `setHeaders` - Add cache-control headers
- Returns data object → passed to `+page.svelte`

### City Page (`[city_url]/+page.ts`)

```typescript
export const load: PageLoad = async ({ params, url, setHeaders }) => {
  const { city_url } = params;

  // Parse city URL
  const parsed = parseCityUrl(city_url);
  if (!parsed) {
    throw error(404, 'Invalid city URL format');
  }

  // Check for cached data from homepage search
  if (url.searchParams.get('from') === 'search') {
    const cached = window.history.state?.searchResults;
    if (cached?.success) {
      return processMeetingsData(cached);  // Skip API call!
    }
  }

  // Otherwise fetch fresh
  const result = await searchMeetings(`${parsed.cityName}, ${parsed.state}`);
  if (!result.success) {
    throw error(404, result.message || 'City not found');
  }

  // Cache for 2 minutes
  setHeaders({ 'cache-control': 'public, max-age=120' });

  return processMeetingsData(result);
};
```

**Key features:**
- Check navigation state for cached data (eliminate double-fetch)
- Throw `error()` for 404s → triggers `+error.svelte`
- Shorter cache (2min) for more dynamic data

### Receiving Data in Components

```svelte
<script lang="ts">
  import type { PageData } from './$types';

  // Data passed from load function
  let { data }: { data: PageData } = $props();

  // Access data
  console.log(data.analytics);
</script>

<div>
  {data.analytics.real_metrics.cities_covered} cities tracked
</div>
```

---

## Navigation Patterns

### 1. Programmatic Navigation

```typescript
import { goto } from '$app/navigation';

// Basic navigation
goto('/about');

// With query parameters
goto(`/${cityUrl}?from=search`);

// With state (for caching)
goto(`/${cityUrl}`, {
  state: { searchResults: result }
});

// Replace history (no back button)
goto('/new-page', {
  replaceState: true
});
```

### 2. Link Navigation

```svelte
<!-- Standard link -->
<a href="/about">About</a>

<!-- Dynamic link -->
<a href="/{cityUrl}/{meetingSlug}">
  {meeting.title}
</a>

<!-- Prefetch on hover (future optimization) -->
<a href="/slow-page" data-sveltekit-preload-data="hover">
  Slow Page
</a>
```

### 3. Navigation Loading Indicator

**Root layout shows progress bar during navigation:**

```svelte
<script>
  import { navigating } from '$app/stores';
</script>

{#if $navigating}
  <div class="navigation-loading"></div>
{/if}
```

**CSS animation:**
```css
.navigation-loading {
  position: fixed;
  top: 0;
  height: 3px;
  background: white;
  animation: progress 1s ease-in-out;
}
```

---

## URL Structure

### Homepage
```
https://engagic.org/
```

### City Page
```
https://engagic.org/paloaltoCA
                     ^^^^^^^^^^
                     city_banana (cityName + state uppercase)
```

**Format:** `{cityName}{StateAbbrev}` (no spaces, lowercase city + uppercase state)

**Examples:**
- `paloaltoCA` → Palo Alto, CA
- `austinTX` → Austin, TX
- `stlouisMO` → St. Louis, MO (punctuation removed)

**Generation:**
```typescript
export function generateCityUrl(cityName: string, state: string): string {
  const cleanCity = cityName
    .toLowerCase()
    .replace(/[^a-z0-9]/g, '');  // Remove non-alphanumeric
  return `${cleanCity}${state.toUpperCase()}`;
}
```

### Meeting Detail Page
```
https://engagic.org/paloaltoCA/123-city-council-nov-2-2024
                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                               meeting_slug
```

**Format:** `{id}-{title-slug}-{date-slug}`

**Examples:**
- `123-city-council-nov-2-2024`
- `456-planning-commission-oct-15-2024`

**Generation:**
```typescript
export function generateMeetingSlug(meeting: Meeting): string {
  const titleSlug = meeting.title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');

  const dateSlug = meeting.date
    ? new Date(meeting.date).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric'
      }).toLowerCase().replace(/,?\s+/g, '-')
    : 'no-date';

  return `${meeting.id}-${titleSlug}-${dateSlug}`;
}
```

**Extraction:**
```typescript
export function extractMeetingIdFromSlug(slug: string): string | null {
  const match = slug.match(/^(\d+)-/);
  return match ? match[1] : null;
}
```

### Query Parameters

**Search flow caching:**
```
Homepage search → Navigate to:
https://engagic.org/paloaltoCA?from=search
                               ^^^^^^^^^^^
```

**Purpose:** Signal that we have fresh data in navigation state, skip API call.

---

## Error Handling

### Error Boundary (`+error.svelte`)

```svelte
<script lang="ts">
  import { page } from '$app/stores';

  const error = $derived($page.error);
  const status = $derived($page.status);
</script>

{#if status === 404}
  <h1>City Not Found</h1>
  <p>{error?.message}</p>
{:else}
  <h1>Something Went Wrong</h1>
  <p>{error?.message || 'An unexpected error occurred'}</p>
{/if}
```

### Throwing Errors from Load Functions

```typescript
import { error } from '@sveltejs/kit';

export const load: PageLoad = async ({ params }) => {
  const data = await fetchData(params.id);

  if (!data) {
    throw error(404, 'Data not found');
  }

  return { data };
};
```

**When load function throws → +error.svelte renders**

### Error Types

| Status | When | Example |
|--------|------|---------|
| 404 | Resource not found | Invalid city URL, meeting doesn't exist |
| 500 | Server error | API is down, unexpected crash |
| 429 | Rate limited | Too many requests |

---

## Navigation Lifecycle

**What happens when user clicks a link:**

```
1. User clicks <a href="/city">
2. SvelteKit intercepts click
3. Shows loading indicator ($navigating = true)
4. Runs +page.ts load function
5. Fetches data
6. If successful:
   - Renders +page.svelte with data
   - Hides loading indicator
   - Updates URL
7. If error thrown:
   - Renders +error.svelte
   - Passes error details
```

**Zero flash of empty content** - Page only renders after data is ready.

---

## Advanced Patterns

### 1. Conditional Redirects

```typescript
import { redirect } from '@sveltejs/kit';

export const load: PageLoad = async ({ params }) => {
  if (params.city_url === 'about') {
    throw redirect(307, '/about');
  }
  // Continue normal loading...
};
```

### 2. Parallel Data Fetching

```typescript
export const load: PageLoad = async () => {
  const [users, posts, comments] = await Promise.all([
    fetchUsers(),
    fetchPosts(),
    fetchComments()
  ]);

  return { users, posts, comments };
};
```

### 3. Dependent Data Fetching

```typescript
export const load: PageLoad = async ({ params }) => {
  const user = await fetchUser(params.id);
  const posts = await fetchUserPosts(user.id);  // Depends on user

  return { user, posts };
};
```

### 4. State Preservation (Snapshots)

```typescript
// +page.svelte
export const snapshot = {
  capture: () => ({
    scrollY: window.scrollY,
    expandedSections: expandedSections
  }),
  restore: (state) => {
    expandedSections = state.expandedSections;
    setTimeout(() => window.scrollTo(0, state.scrollY), 0);
  }
};
```

**When to use:**
- Preserve scroll position on back/forward navigation
- Remember UI state (expanded sections, form inputs)
- NOT for data (use load functions)

---

## Performance Optimizations

### 1. Eliminate Double-Fetching

**Problem:** Homepage search → city page both fetch same data

**Solution:**
```typescript
// Homepage
goto(`/${cityUrl}?from=search`, {
  state: { searchResults }
});

// City page
if (url.searchParams.get('from') === 'search') {
  return window.history.state.searchResults;  // No API call!
}
```

**Impact:** 50% reduction in API calls for search flow

### 2. Aggressive Caching

```typescript
setHeaders({
  'cache-control': 'public, max-age=300'  // 5 minutes
});
```

**Impact:** 70% reduction in API calls for repeat visits

### 3. Prefetching (Future)

```svelte
<a
  href="/slow-page"
  data-sveltekit-preload-data="hover"  // Load data on hover
>
  Slow Page
</a>
```

**Not implemented yet** - but available when needed.

---

## Routing Best Practices

### DO:

✅ Use load functions for data fetching
✅ Throw errors from load functions
✅ Create +error.svelte for graceful failures
✅ Use cache headers appropriately
✅ Check navigation state to avoid double-fetching
✅ Use `goto()` for programmatic navigation

### DON'T:

❌ Fetch data in `onMount()` (use load functions)
❌ Return objects from load functions on error (throw errors)
❌ Forget to handle loading states
❌ Skip error boundaries
❌ Use `window.location.href` (breaks SvelteKit)
❌ Mutate URL without `goto()` or `<a>`

---

**Last Updated:** 2025-11-02
**See Also:** [FRONTEND.md](./FRONTEND.md) for architecture overview
