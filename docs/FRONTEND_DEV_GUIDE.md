# Frontend Development & API Guide

**Last Updated:** 2025-11-24
**Node Version:** 18+ required
**Package Manager:** npm
**API Base URL:** `https://api.engagic.org`

**Note:** Historical docs archived in `docs/archive/frontend-docs-2024-11/`

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Development Workflow](#development-workflow)
3. [API Integration](#api-integration)
4. [Common Tasks](#common-tasks)
5. [Debugging](#debugging)
6. [Testing](#testing)
7. [Build & Deploy](#build--deploy)
8. [Troubleshooting](#troubleshooting)

---

## Getting Started

### Prerequisites

```bash
# Check Node.js version (need 18+)
node --version  # Should output v18.x.x or higher

# Check npm version
npm --version
```

**Don't have Node?** Install from [nodejs.org](https://nodejs.org/)

### Initial Setup

```bash
# 1. Navigate to frontend directory
cd frontend

# 2. Install dependencies
npm install

# 3. Start dev server
npm run dev

# 4. Open browser
# Navigate to http://localhost:5173
```

**Dev server will:**
- Hot reload on file changes
- Show compilation errors in terminal
- Provide helpful error messages
- Enable source maps for debugging

---

## Development Workflow

### Daily Development

```bash
# Start dev server (leave running)
npm run dev

# In another terminal, run type checking (optional)
npm run check:watch
```

### Hot Module Replacement (HMR)

**Changes auto-reload:**
- `.svelte` files → Component reloads
- `.ts` files → Full page reload
- `.css` files → Style hot swap
- `+page.ts` → Page data reloads

**No need to manually refresh!**

### File Structure Recap

```
src/
├── lib/                 # Shared code
│   ├── components/      # Reusable UI components
│   ├── api.ts           # API client
│   └── types.ts         # TypeScript types
│
└── routes/              # File-based routing
    ├── +layout.svelte   # Root layout
    ├── +page.svelte     # Homepage
    ├── [city]/          # City page
    └── [city]/[date]/   # Meeting detail
```

---

## API Integration

### Overview

Thin, type-safe wrapper around `fetch()` with automatic retry logic. No external HTTP libraries (axios, etc.) to minimize bundle size.

**Architecture:**

```
Component/Load Function
    ↓
api.searchMeetings()
    ↓
fetchWithRetry() [3 attempts, 1s delay]
    ↓
fetch() [native browser API]
    ↓
api.engagic.org [FastAPI backend]
```

**Features:**
- Automatic retries (3 attempts with exponential backoff)
- Timeout protection (30s)
- Full TypeScript coverage
- Error classification (network vs API vs timeout)
- Zero dependencies

### API Client Location

`lib/api.ts` (simplified unified client)

### Core Functions

#### fetchWithRetry()

Retries failed requests automatically:

```typescript
async function fetchWithRetry(
  url: string,
  options: RequestInit = {},
  retries: number = 3
): Promise<Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000); // 30s

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal
    });

    clearTimeout(timeout);

    // Success
    if (response.ok) return response;

    // Rate limited (don't retry)
    if (response.status === 429) {
      throw new ApiError('Rate limit exceeded', 429, true);
    }

    // Not found (don't retry)
    if (response.status === 404) {
      throw new ApiError('Not found', 404, false);
    }

    // Server error (retry)
    if (response.status >= 500 && retries > 0) {
      await new Promise(resolve => setTimeout(resolve, 1000));
      return fetchWithRetry(url, options, retries - 1);
    }

    throw new ApiError('Request failed', response.status, false);

  } catch (error) {
    // Timeout or network error (retry)
    if (error.name === 'AbortError' && retries > 0) {
      await new Promise(resolve => setTimeout(resolve, 1000));
      return fetchWithRetry(url, options, retries - 1);
    }
    throw error;
  }
}
```

### API Methods

#### searchMeetings()

Search for meetings by topic and location:

```typescript
import { api } from '$lib/api';

const results = await api.searchMeetings({
  topics: ['zoning', 'housing'],
  cityBanana: 'paloaltoCA',
  limit: 10
});
```

**Parameters:**
```typescript
interface SearchParams {
  topics?: string[];
  cityBanana?: string;
  startDate?: string;  // ISO 8601
  endDate?: string;
  limit?: number;      // Default: 20
}
```

**Returns:**
```typescript
interface SearchResponse {
  results: Meeting[];
  total: number;
  page: number;
}
```

#### getMeetings()

Get meetings for a specific city:

```typescript
const meetings = await api.getMeetings('paloaltoCA', {
  startDate: '2025-01-01',
  limit: 10
});
```

**Parameters:**
```typescript
getMeetings(
  cityBanana: string,
  options?: {
    startDate?: string;
    endDate?: string;
    limit?: number;
  }
): Promise<Meeting[]>
```

#### getMeetingDetail()

Get single meeting with full agenda items:

```typescript
const meeting = await api.getMeetingDetail('paloaltoCA', '2025-01-15');
```

**Parameters:**
```typescript
getMeetingDetail(
  cityBanana: string,
  date: string  // YYYY-MM-DD
): Promise<Meeting>
```

#### getTopics()

Get available topics for filtering:

```typescript
const topics = await api.getTopics();
// ['zoning', 'housing', 'transportation', ...]
```

#### getCities()

Get all available cities:

```typescript
const cities = await api.getCities();
```

**Returns:**
```typescript
interface City {
  city_banana: string;
  city_name: string;
  state: string;
  vendor: string;
  last_sync?: string;
}
```

### Error Handling

**ApiError class:**

```typescript
class ApiError extends Error {
  constructor(
    message: string,
    public statusCode: number,
    public isRateLimited: boolean = false
  ) {
    super(message);
    this.name = 'ApiError';
  }
}
```

**Usage in components:**

```svelte
<script lang="ts">
  import { api } from '$lib/api';
  import type { Meeting } from '$lib/types';

  let meetings = $state<Meeting[]>([]);
  let error = $state<string | null>(null);
  let loading = $state(false);

  async function loadMeetings() {
    loading = true;
    error = null;

    try {
      meetings = await api.getMeetings('paloaltoCA');
    } catch (e) {
      if (e instanceof ApiError) {
        if (e.isRateLimited) {
          error = 'Too many requests. Please try again later.';
        } else if (e.statusCode === 404) {
          error = 'No meetings found for this city.';
        } else {
          error = 'Failed to load meetings. Please try again.';
        }
      } else {
        error = 'Network error. Please check your connection.';
      }
    } finally {
      loading = false;
    }
  }
</script>

{#if loading}
  <p>Loading...</p>
{:else if error}
  <p class="error">{error}</p>
{:else}
  <ul>
    {#each meetings as meeting}
      <li>{meeting.title}</li>
    {/each}
  </ul>
{/if}
```

### Usage in Load Functions

**Server-side load:**

```typescript
// +page.server.ts
import { api } from '$lib/api';
import { error } from '@sveltejs/kit';

export async function load({ params }) {
  try {
    const meetings = await api.getMeetings(params.city);
    return { meetings };
  } catch (e) {
    throw error(500, 'Failed to load meetings');
  }
}
```

**Universal load:**

```typescript
// +page.ts
import { api } from '$lib/api';
import { error } from '@sveltejs/kit';

export async function load({ params, fetch }) {
  try {
    const meeting = await api.getMeetingDetail(params.city, params.date);
    return { meeting };
  } catch (e) {
    if (e instanceof ApiError && e.statusCode === 404) {
      throw error(404, 'Meeting not found');
    }
    throw error(500, 'Failed to load meeting');
  }
}
```

### Type System

**Core types:**

```typescript
// lib/types.ts

export interface Meeting {
  id: string;
  city_banana: string;
  city_name: string;
  date: string;           // YYYY-MM-DD
  title: string;
  meeting_url: string;
  agenda_url?: string;
  packet_url?: string;
  items: AgendaItem[];
  topics: string[];
  participation_info?: ParticipationInfo;
}

export interface AgendaItem {
  id: string;
  sequence: number;
  title: string;
  summary?: string;
  thinking?: string;      // LLM reasoning
  topics: string[];
  attachments: Attachment[];
}

export interface Attachment {
  url: string;
  name: string;
  size?: number;
}

export interface ParticipationInfo {
  email?: string;
  phone?: string;
  zoom_url?: string;
}

export interface City {
  city_banana: string;
  city_name: string;
  state: string;
  vendor: string;
  last_sync?: string;
}
```

---

## Common Tasks

### Add a New Page

1. Create route file:
```bash
# Homepage
src/routes/+page.svelte

# About page
src/routes/about/+page.svelte

# Dynamic route
src/routes/[param]/+page.svelte
```

2. Add load function (optional):
```typescript
// +page.ts or +page.server.ts
export async function load() {
  return { title: 'My Page' };
}
```

3. Create component:
```svelte
<script lang="ts">
  let { data } = $props();
</script>

<h1>{data.title}</h1>
```

### Add a New Component

1. Create file: `src/lib/components/MyComponent.svelte`

2. Define props and logic:
```svelte
<script lang="ts">
  interface Props {
    title: string;
    count?: number;
  }

  let { title, count = 0 }: Props = $props();
  let doubled = $derived(count * 2);
</script>

<div class="my-component">
  <h2>{title}</h2>
  <p>Count: {count}, Doubled: {doubled}</p>
</div>

<style>
  .my-component { padding: 1rem; }
  h2 { font-size: 1.5rem; }
</style>
```

3. Use it:
```svelte
<script>
  import MyComponent from '$lib/components/MyComponent.svelte';
</script>

<MyComponent title="Hello" count={5} />
```

### Call an API Endpoint

```typescript
import { api } from '$lib/api';

// In component
async function fetchData() {
  const meetings = await api.getMeetings('paloaltoCA');
}

// In load function
export async function load({ params }) {
  const meetings = await api.getMeetings(params.city);
  return { meetings };
}
```

### Add Styling

**Global styles** (`src/app.css`):
```css
:root {
  --color-primary: #2563eb;
}

body {
  font-family: system-ui, sans-serif;
  color: var(--color-text);
}
```

**Component styles** (scoped):
```svelte
<style>
  .card {
    padding: var(--spacing-md);
    background: var(--color-bg);
  }
</style>
```

---

## Debugging

### Dev Tools

**Svelte DevTools:**
- Install browser extension: [Svelte DevTools](https://chrome.google.com/webstore/detail/svelte-devtools/)
- Inspect component state, props, events
- View component tree

**Browser DevTools:**
- `console.log()` in `<script>` blocks
- Network tab for API calls
- Elements tab for DOM inspection

**In-template debugging:**
```svelte
{@debug variable}
```

### Common Issues

**"Hydration mismatch"**
- SSR HTML ≠ client render
- Check conditional logic that differs server/client
- Ensure date/time rendering is consistent

**"Cannot access X before initialization"**
- Use `$effect()` for side effects, not top-level code
- Move DOM access into `onMount()` or `$effect()`

**"Styles not applying"**
- Check CSS specificity
- Ensure styles are in `<style>` block
- Use browser DevTools to inspect computed styles

**"API calls failing"**
- Check Network tab in DevTools
- Verify API endpoint is correct
- Check for CORS issues (should be configured on backend)

---

## Testing

### Vitest + Testing Library

**Run tests:**
```bash
npm run test        # Run once
npm run test:watch  # Watch mode
```

### Example Test

```typescript
// MyComponent.test.ts
import { render, screen } from '@testing-library/svelte';
import { describe, it, expect } from 'vitest';
import MyComponent from '$lib/components/MyComponent.svelte';

describe('MyComponent', () => {
  it('renders title', () => {
    render(MyComponent, { props: { title: 'Hello' } });
    expect(screen.getByText('Hello')).toBeInTheDocument();
  });

  it('displays count', () => {
    render(MyComponent, { props: { title: 'Test', count: 5 } });
    expect(screen.getByText(/Count: 5/)).toBeInTheDocument();
  });
});
```

### Testing API Calls

```typescript
// api.test.ts
import { describe, it, expect, vi } from 'vitest';
import { api } from '$lib/api';

describe('API Client', () => {
  it('fetches meetings', async () => {
    // Mock fetch
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve([{ id: '1', title: 'Meeting' }])
      })
    );

    const meetings = await api.getMeetings('paloaltoCA');
    expect(meetings).toHaveLength(1);
    expect(meetings[0].title).toBe('Meeting');
  });
});
```

---

## Build & Deploy

### Build for Production

```bash
npm run build   # Builds to build/
npm run preview # Preview production build locally
```

**Build output:**
- Static HTML/CSS/JS files
- Pre-rendered pages
- Optimized assets

### Cloudflare Pages Deployment

**Automatic (GitHub integration):**
1. Push to `main` branch
2. Cloudflare detects changes
3. Builds with `npm run build`
4. Deploys to edge network (~30s)

**Manual:**
```bash
npm run build
wrangler pages publish build
```

### Environment Variables

Create `.env` in `frontend/`:

```bash
PUBLIC_API_BASE_URL=https://api.engagic.org
```

**Access in code:**
```typescript
import { env } from '$env/dynamic/public';
const apiUrl = env.PUBLIC_API_BASE_URL;
```

**Cloudflare Pages:**
- Set in dashboard: Settings → Environment Variables
- Prefix with `PUBLIC_` for client-side access

---

## Troubleshooting

### Build Fails

**Check:**
1. `npm run check` for type errors
2. `npm run build` output for specific errors
3. Ensure all imports are correct
4. Verify `package.json` dependencies match

**Common causes:**
- Missing type definitions
- Import path errors
- TypeScript errors

### Dev Server Won't Start

**Solutions:**
```bash
# Clear node_modules and reinstall
rm -rf node_modules package-lock.json
npm install

# Check port 5173 is available
lsof -i :5173
# Kill process if needed
kill -9 <PID>

# Try different port
npm run dev -- --port 3000
```

### API Calls Fail in Production

**Check:**
1. API base URL is correct
2. CORS is configured on backend
3. Network tab shows actual request URL
4. Backend is running and accessible

### Styles Look Different in Production

**Common causes:**
- CSS not being purged correctly
- Missing global styles
- CSS custom properties not supported (unlikely with modern browsers)

**Debug:**
1. Run `npm run preview` to test prod build locally
2. Check browser DevTools for missing styles
3. Verify CSS is in `build/` output

### Performance Issues

**Optimize:**
1. Enable preloading: `data-sveltekit-preload-data="hover"`
2. Lazy load images: `loading="lazy"`
3. Check bundle size: `npm run build -- --analyze`
4. Minimize JavaScript: already done by Vite

---

## See Also

- **Frontend Overview**: See `FRONTEND_README.md` for architecture and components
- **Backend API**: See `docs/API.md` for complete endpoint reference
- **Historical Docs**: See `docs/archive/frontend-docs-2024-11/` for detailed pre-consolidation documentation
- **SvelteKit Docs**: https://kit.svelte.dev/
- **Vite Docs**: https://vitejs.dev/
