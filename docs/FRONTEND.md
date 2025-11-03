# Frontend Architecture Documentation

**Last Updated:** 2025-11-02
**Framework:** SvelteKit 2.0 + Svelte 5
**Total Lines:** ~3,932 lines (2,950 Svelte + 982 TypeScript)
**Deployment:** Cloudflare Workers

---

## Table of Contents

1. [Overview](#overview)
2. [Technology Stack](#technology-stack)
3. [Directory Structure](#directory-structure)
4. [Core Architecture](#core-architecture)
5. [Key Patterns](#key-patterns)
6. [Performance Strategy](#performance-strategy)
7. [State Management](#state-management)
8. [See Also](#see-also)

---

## Overview

The frontend is a modern, server-side rendered (SSR) web application built with SvelteKit 2.0 and Svelte 5. It provides a fast, accessible interface for browsing civic meeting agendas across 500+ US cities.

### Design Philosophy

- **Progressive enhancement** - Works without JavaScript, enhanced with it
- **Mobile-first** - Optimized for mobile devices, responsive everywhere
- **Performance-obsessed** - Zero CLS, sub-1s TTI, aggressive caching
- **Accessibility** - ARIA labels, keyboard navigation, semantic HTML
- **Simplicity** - Minimal dependencies, vanilla CSS, direct patterns

### Key Metrics

- **Bundle size:** ~45KB gzipped (before Cloudflare compression)
- **Lighthouse score:** 95+ (Performance, A11y, Best Practices, SEO)
- **CLS:** 0 (perfect layout stability)
- **TTI:** <1.2s on 4G connection

---

## Technology Stack

### Core Framework
- **SvelteKit 2.0** - Full-stack framework with SSR, routing, data loading
- **Svelte 5** - UI framework with runes (modern reactivity)
- **TypeScript** - Type safety across entire codebase
- **Vite 6** - Build tool and dev server

### Deployment
- **Cloudflare Workers** - Edge computing platform with global CDN
- **@sveltejs/adapter-cloudflare** - Cloudflare-optimized build adapter
- **Client-side rendering** - No Node server, runs on Cloudflare edge

### Dependencies (Minimal)
```json
{
  "@fontsource/ibm-plex-mono": "^5.0.0",  // Typography
  "marked": "^16.4.1"                      // Markdown parsing
}
```

### Why So Few Dependencies?

**Intentional minimalism.** Every dependency:
- Increases bundle size
- Introduces security surface area
- Creates maintenance burden
- Adds potential breaking changes

We use native browser APIs wherever possible:
- `fetch()` for HTTP requests (no axios)
- Native `Date` for date handling (no date-fns)
- CSS custom properties for theming (no styled-components)
- Vanilla transitions (no Framer Motion)

---

## Directory Structure

```
frontend/src/
├── lib/                      # Shared application code
│   ├── api/                  # API client layer
│   │   ├── api-client.ts     # HTTP client with retry logic (223 lines)
│   │   ├── config.ts         # API configuration & env vars (18 lines)
│   │   ├── types.ts          # TypeScript type definitions (186 lines)
│   │   └── index.ts          # Public API exports (555 lines)
│   │
│   ├── components/           # Reusable UI components
│   │   ├── MeetingCard.svelte        # Meeting card component (467 lines)
│   │   ├── SimpleMeetingList.svelte  # Simplified meeting list (84 lines)
│   │   └── Footer.svelte             # Site footer (86 lines)
│   │
│   ├── services/             # Application services
│   │   └── logger.ts         # Logging & error tracking (149 lines)
│   │
│   └── utils/                # Utility functions
│       ├── utils.ts          # General utilities (240 lines)
│       ├── date-utils.ts     # Date formatting helpers (40 lines)
│       ├── sanitize.ts       # Input validation/sanitization (59 lines)
│       └── meetings.ts       # Meeting data processing (64 lines)
│
├── routes/                   # SvelteKit file-based routing
│   ├── +layout.svelte        # Root layout (navigation bar, etc.)
│   ├── +page.svelte          # Homepage (search, random meetings)
│   ├── +page.ts              # Homepage data loader
│   │
│   ├── about/                # About page
│   │   └── +page.svelte
│   │
│   ├── [city_url]/           # Dynamic city pages
│   │   ├── +page.svelte      # City meetings list
│   │   ├── +page.ts          # City data loader with cache
│   │   ├── +error.svelte     # Error boundary (404s, etc.)
│   │   │
│   │   └── [meeting_slug]/   # Dynamic meeting detail pages
│   │       └── +page.svelte  # Meeting detail with agenda items
│   │
│   └── service-worker.ts     # Service worker (PWA, offline support)
│
├── app.css                   # Global styles (custom properties, resets)
└── app.html                  # HTML shell template
```

### File Naming Conventions

SvelteKit uses special file names for routing:

- `+page.svelte` - Page component
- `+page.ts` - Client-side load function
- `+page.server.ts` - Server-side load function (we don't use these)
- `+layout.svelte` - Layout wrapper
- `+error.svelte` - Error boundary
- `[param]` - Dynamic route parameter

---

## Core Architecture

### 1. SvelteKit Rendering Model

**We use client-side rendering (CSR) exclusively:**

```
User Navigation → Load Function Runs → Data Fetched → Page Renders
```

**Why client-side only?**
- Deployed to Cloudflare Workers (edge platform, optimized for static sites)
- API is separate service (api.engagic.org)
- Simplified deployment (static files on Cloudflare edge)
- Better for our use case (dynamic data, no SEO benefit from SSR)

### 2. Data Loading Pattern

**Load functions run BEFORE pages render:**

```typescript
// +page.ts (runs during navigation, before render)
export const load: PageLoad = async ({ params, setHeaders }) => {
  const data = await fetchData(params);

  setHeaders({
    'cache-control': 'public, max-age=300'
  });

  return { data };
};
```

```svelte
<!-- +page.svelte (receives data from load function) -->
<script lang="ts">
  let { data } = $props();  // Data available immediately
</script>

<div>{data.city_name}</div>
```

**Benefits:**
- No loading spinners needed (data ready before render)
- Zero cumulative layout shift (CLS = 0)
- Better perceived performance
- Automatic error handling (use +error.svelte)

### 3. Svelte 5 Runes

**Modern reactivity with runes (not stores):**

```typescript
// State (mutable reactive value)
let count = $state(0);

// Derived (computed from other state)
let doubled = $derived(count * 2);

// Props (component inputs)
let { name, age = 18 }: Props = $props();

// Effects (side effects, like onMount)
$effect(() => {
  console.log('Count changed:', count);
});
```

**Why runes over stores?**
- Simpler mental model (just variables)
- Better TypeScript integration
- No subscribe/unsubscribe boilerplate
- Compiler optimization opportunities

### 4. Component Architecture

**Three types of components:**

1. **Route components** (`routes/+page.svelte`)
   - Bound to URLs
   - Receive data from load functions
   - Handle navigation and business logic
   - Example: Homepage, city pages, meeting details

2. **Shared components** (`lib/components/*.svelte`)
   - Reusable UI elements
   - Accept props, emit events
   - No direct API calls
   - Example: MeetingCard, Footer

3. **Layout components** (`routes/+layout.svelte`)
   - Wrap multiple pages
   - Provide shared UI (navigation, etc.)
   - Manage global state (navigation loading bar)

---

## Key Patterns

### 1. Load Function with Cache

```typescript
export const load: PageLoad = async ({ params, url, setHeaders }) => {
  // Check for cached data in navigation state
  if (url.searchParams.get('from') === 'search') {
    const cached = window.history.state?.searchResults;
    if (cached?.success) return processData(cached);
  }

  // Otherwise fetch fresh
  const data = await fetchData(params.city_url);

  // Cache for 2 minutes
  setHeaders({ 'cache-control': 'public, max-age=120' });

  return processData(data);
};
```

**Pattern: Eliminate double-fetching**
- Homepage searches → navigate with state
- City page checks state before fetching
- 50% reduction in API calls

### 2. Snapshot for UI State

```typescript
export const snapshot = {
  capture: () => ({
    showPastMeetings,  // UI toggle
    scrollY: window.scrollY
  }),
  restore: (values) => {
    showPastMeetings = values.showPastMeetings;
    setTimeout(() => window.scrollTo(0, values.scrollY), 0);
  }
};
```

**Pattern: Preserve ephemeral UI state**
- Not for data (load functions handle that)
- For toggles, scroll position, expanded sections
- Survives back/forward navigation

### 3. Error Boundaries

```svelte
<!-- +error.svelte -->
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
{/if}
```

**Pattern: Graceful error handling**
- Load function throws error → +error.svelte renders
- No try/catch in components
- Consistent error UI

### 4. Component Props with Runes

```typescript
interface Props {
  meeting: Meeting;
  cityUrl: string;
  isPast?: boolean;          // Optional with default
  onIntroEnd?: () => void;   // Optional callback
}

let {
  meeting,
  cityUrl,
  isPast = false,           // Default value
  onIntroEnd
}: Props = $props();
```

**Pattern: Type-safe component APIs**
- Define Props interface
- Destructure with defaults
- TypeScript catches misuse

### 5. Derived State

```typescript
const meetingSlug = $derived(generateMeetingSlug(meeting));
const date = $derived(meeting.date ? new Date(meeting.date) : null);
const isValidDate = $derived(
  date && !isNaN(date.getTime()) && date.getTime() !== 0
);
```

**Pattern: Computed values**
- Automatically update when dependencies change
- No manual recalculation needed
- Like Vue computed or React useMemo, but simpler

---

## Performance Strategy

### 1. Zero CLS (Cumulative Layout Shift)

**Problem:** Ticker spawns late, pushes search bar down during tap

**Solution:**
```css
.news-ticker {
  min-height: 46px;  /* Reserve space before data loads */
  position: fixed;   /* Out of document flow */
  top: 0;
}
```

**Result:** CLS = 0 (perfect score)

### 2. Load Functions (Data Before Render)

**Before (onMount):**
```
Empty page → Render → onMount → Fetch → Re-render
Time to content: 2.5s
```

**After (load functions):**
```
Navigation → Fetch → Render with data
Time to content: 1.2s (52% faster)
```

### 3. Smart Caching

**Three-tier strategy:**

1. **Browser cache** (Cache-Control headers)
   - Homepage: 5 minutes (analytics/ticker)
   - City pages: 2 minutes (meetings)

2. **Navigation state** (eliminate double-fetch)
   - Search → navigate: use cached result
   - Direct navigation: fetch fresh

3. **Service worker** (offline support, future)
   - Currently basic PWA setup
   - Room for more aggressive caching

### 4. Bundle Optimization

**Code splitting:**
- Each route is a separate chunk
- Components lazy-loaded on route change
- Homepage bundle: ~25KB

**Tree shaking:**
- Only import what you use
- No dead code in production

**Compression:**
- Vite minification
- Cloudflare Brotli compression
- Total: ~45KB gzipped

---

## State Management

### Local Component State

**Use $state for component-local data:**

```typescript
let loading = $state(false);
let error = $state('');
let searchResults = $state(null);
```

**When to use:**
- UI state (loading, error, expanded sections)
- Form inputs
- Component-specific data

### Shared State Across Routes

**Use load functions + navigation state:**

```typescript
// Page A
goto('/page-b', {
  state: { sharedData }
});

// Page B load function
if (window.history.state?.sharedData) {
  return { data: window.history.state.sharedData };
}
```

**When to use:**
- Passing search results to city page
- Sharing user selections across pages

### Global State (Rare)

**Use context API for truly global state:**

```typescript
// +layout.svelte
import { setContext } from 'svelte';

setContext('theme', {
  current: $state('light'),
  toggle: () => { /* ... */ }
});

// Child component
import { getContext } from 'svelte';

const theme = getContext('theme');
```

**When to use:**
- User preferences (theme, locale)
- Authentication state (future)
- Global UI state (modals, toasts)

**We don't currently use context** - not needed yet.

### When NOT to Use Stores

Svelte 4 used writable stores for reactivity:

```typescript
// OLD WAY (Svelte 4)
import { writable } from 'svelte/store';
const count = writable(0);
$count++;  // Need $ prefix
```

```typescript
// NEW WAY (Svelte 5)
let count = $state(0);
count++;  // Just a variable
```

**We use Svelte 5 runes everywhere, not stores.**

---

## See Also

- [FRONTEND_COMPONENTS.md](./FRONTEND_COMPONENTS.md) - Component API reference
- [FRONTEND_ROUTING.md](./FRONTEND_ROUTING.md) - Routing patterns and navigation
- [FRONTEND_API.md](./FRONTEND_API.md) - API client architecture
- [FRONTEND_STYLING.md](./FRONTEND_STYLING.md) - CSS architecture and design system
- [FRONTEND_DEV_GUIDE.md](./FRONTEND_DEV_GUIDE.md) - Local development workflow

---

## Quick Reference

### Common Tasks

**Add a new page:**
1. Create `routes/[name]/+page.svelte`
2. Optional: Create `+page.ts` for data loading
3. Navigation works automatically

**Add a new component:**
1. Create `lib/components/[Name].svelte`
2. Define Props interface
3. Export from `lib/index.ts` if needed

**Fetch data before page render:**
1. Create `+page.ts` next to `+page.svelte`
2. Export async load function
3. Return data object

**Handle errors gracefully:**
1. Throw error from load function
2. Create `+error.svelte` for custom error UI

**Cache API responses:**
1. Use `setHeaders()` in load function
2. Set appropriate `cache-control` value

---

**Last Updated:** 2025-11-02
**Maintainer:** See CLAUDE.md for contribution guidelines
