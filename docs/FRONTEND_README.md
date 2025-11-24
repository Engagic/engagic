# Frontend Documentation

**Last Updated:** 2025-11-24
**Framework:** SvelteKit 2.0 + Svelte 5
**Deployment:** Cloudflare Pages
**Total Lines:** ~3,932 lines (2,950 Svelte + 982 TypeScript)

**Note:** Detailed historical docs archived in `docs/archive/frontend-docs-2024-11/`

---

## Table of Contents

1. [Overview](#overview)
2. [Technology Stack](#technology-stack)
3. [Directory Structure](#directory-structure)
4. [Architecture](#architecture)
5. [Components](#components)
6. [Routing](#routing)
7. [Styling](#styling)
8. [Development](#development)

---

## Overview

Server-side rendered (SSR) web application providing fast, accessible civic meeting agendas for 500+ US cities.

### Design Philosophy

- **Progressive enhancement**: Works without JavaScript, enhanced with it
- **Mobile-first**: Optimized for mobile, responsive everywhere
- **Performance-obsessed**: Zero CLS, sub-1s TTI, aggressive caching
- **Accessibility**: ARIA labels, keyboard navigation, semantic HTML
- **Simplicity**: Minimal dependencies, vanilla CSS

### Key Metrics

- **Bundle size:** ~45KB gzipped
- **Lighthouse score:** 95+ (Performance, A11y, Best Practices, SEO)
- **CLS:** 0 (perfect layout stability)
- **TTI:** <1.2s on 4G connection

---

## Technology Stack

### Core Framework
- **SvelteKit 2.0**: Full-stack framework with SSR, routing, data loading
- **Svelte 5**: UI framework with runes (modern reactivity)
- **TypeScript**: Type safety across codebase
- **Vite 6**: Build tool and dev server

### Deployment
- **Cloudflare Pages**: Edge deployment, CDN, HTTPS
- **Static adapter**: Pre-renders pages at build time

### Styling
- **Vanilla CSS**: No preprocessor, no CSS-in-JS
- **Custom properties**: Design tokens for theming
- **System fonts**: No web fonts, instant text rendering

---

## Directory Structure

```
frontend/src/
├── routes/           # SvelteKit pages (file-based routing)
│   ├── +page.svelte          # Homepage (/)
│   ├── [city]/               # City page (/[city])
│   └── [city]/[date]/        # Meeting detail (/[city]/[date])
├── lib/              # Shared code
│   ├── components/   # Reusable UI components
│   ├── api.ts        # API client
│   └── types.ts      # TypeScript types
└── app.html          # HTML template
```

**File-based routing:**
- `+page.svelte`: Page component
- `+page.ts` / `+page.server.ts`: Data loading
- `+layout.svelte`: Shared layout wrapper
- `+error.svelte`: Error boundary

---

## Architecture

### Server-Side Rendering (SSR)

**Load functions** run on server, fetch data, pass to components:

```typescript
// +page.server.ts
export async function load({ params }) {
  const meetings = await api.getMeetings(params.city);
  return { meetings };
}
```

**Component receives data:**

```svelte
<!-- +page.svelte -->
<script lang="ts">
  let { data } = $props(); // data from load function
</script>
<h1>Meetings: {data.meetings.length}</h1>
```

### Svelte 5 Runes

Modern reactivity primitives (replaces `let` + `$:` from Svelte 4):

- **`$state()`**: Reactive state
- **`$derived()`**: Computed values
- **`$effect()`**: Side effects
- **`$props()`**: Component props

**Example:**

```svelte
<script lang="ts">
  let count = $state(0);
  let doubled = $derived(count * 2);

  $effect(() => {
    console.log('Count changed:', count);
  });
</script>
<button onclick={() => count++}>
  Count: {count}, Doubled: {doubled}
</button>
```

### Key Patterns

**Snapshot restoration** (preserves scroll + form state):
```typescript
export const snapshot = {
  capture: () => ({ scroll: window.scrollY }),
  restore: (snap) => window.scrollTo(0, snap.scroll)
};
```

**Error boundaries** (`+error.svelte`):
```svelte
<script lang="ts">
  import { page } from '$app/stores';
</script>
<h1>Error {$page.status}</h1>
<p>{$page.error.message}</p>
```

**Prefetching** (hover/tap to load):
```svelte
<a href="/[city]" data-sveltekit-preload-data="hover">City</a>
```

---

## Components

### MeetingCard

Primary UI component displaying meeting details.

**Props:**
```typescript
interface Props {
  meeting: Meeting;
  expandedItemId?: string | null;
  onItemToggle?: (itemId: string) => void;
}
```

**Usage:**
```svelte
<MeetingCard
  meeting={mtg}
  expandedItemId={activeId}
  onItemToggle={(id) => activeId = id}
/>
```

**Features:**
- Collapsible agenda items
- Participation info display (email/phone/Zoom)
- Topic badges
- Thinking traces (LLM reasoning)

### SimpleMeetingList

Minimal variant for listing many meetings.

**Props:**
```typescript
interface Props {
  meetings: Meeting[];
  cityBanana?: string;
}
```

**Usage:**
```svelte
<SimpleMeetingList meetings={results} cityBanana="paloaltoCA" />
```

### Footer

Site-wide footer with links and attribution.

```svelte
<Footer />
```

### Creating Components

**Template:**
```svelte
<!-- components/MyComponent.svelte -->
<script lang="ts">
  interface Props {
    title: string;
    count?: number;
  }

  let { title, count = 0 }: Props = $props();
  let doubled = $derived(count * 2);
</script>

<div>
  <h2>{title}</h2>
  <p>Count: {count}, Doubled: {doubled}</p>
</div>

<style>
  div { padding: 1rem; }
  h2 { font-size: 1.5rem; }
</style>
```

**Best practices:**
- Use `$props()` for component props
- Use `$derived()` for computed values
- Scope styles with component `<style>` blocks
- Export types from `types.ts`

---

## Routing

### File-Based Routing

SvelteKit maps files to URLs:

```
routes/
├── +page.svelte                  → /
├── about/+page.svelte            → /about
├── [city]/+page.svelte           → /paloaltoCA
└── [city]/[date]/+page.svelte    → /paloaltoCA/2025-01-15
```

**Dynamic routes** use `[param]` brackets.

### Data Loading

**Server-side load** (`+page.server.ts`):
```typescript
export async function load({ params, fetch }) {
  const meeting = await fetch(`/api/meetings/${params.city}/${params.date}`);
  return { meeting };
}
```

**Universal load** (`+page.ts` - runs on server + client):
```typescript
export async function load({ params, fetch }) {
  const data = await fetch(`/api/data/${params.id}`).then(r => r.json());
  return { data };
}
```

**When to use which:**
- `+page.server.ts`: Server-only (secrets, database access)
- `+page.ts`: Universal (public API calls, can run client-side)

### Navigation

**Programmatic navigation:**
```typescript
import { goto } from '$app/navigation';
goto('/city/meeting');
```

**Link prefetching:**
```svelte
<a href="/city" data-sveltekit-preload-data="hover">City</a>
```

**Back navigation:**
```typescript
import { goto } from '$app/navigation';
goto(-1); // Go back
```

### Layouts

**Shared layout** (`+layout.svelte`):
```svelte
<script lang="ts">
  import Header from '$lib/components/Header.svelte';
  import Footer from '$lib/components/Footer.svelte';
</script>

<Header />
<slot /> <!-- Page content renders here -->
<Footer />
```

---

## Styling

### CSS Architecture

**No preprocessor, no CSS-in-JS.** Vanilla CSS with custom properties.

**Global styles** (`app.css`):
```css
:root {
  --font-sans: system-ui, -apple-system, sans-serif;
  --color-primary: #2563eb;
  --spacing-unit: 0.25rem;
}
```

**Component styles** (scoped):
```svelte
<style>
  .card { padding: var(--spacing-unit); }
  .card:hover { background: var(--color-hover); }
</style>
```

### Design System

**CSS Custom Properties:**

```css
/* Typography */
--font-sans: system-ui, -apple-system, sans-serif;
--font-mono: 'SF Mono', Consolas, monospace;

/* Colors */
--color-text: #111;
--color-bg: #fff;
--color-primary: #2563eb;
--color-border: #e5e7eb;

/* Spacing */
--spacing-xs: 0.25rem;  /* 4px */
--spacing-sm: 0.5rem;   /* 8px */
--spacing-md: 1rem;     /* 16px */
--spacing-lg: 1.5rem;   /* 24px */
--spacing-xl: 2rem;     /* 32px */

/* Breakpoints */
--bp-mobile: 640px;
--bp-tablet: 768px;
--bp-desktop: 1024px;
```

### Responsive Design

**Mobile-first approach:**

```css
/* Base: mobile */
.card { padding: 1rem; }

/* Tablet and up */
@media (min-width: 768px) {
  .card { padding: 2rem; }
}

/* Desktop and up */
@media (min-width: 1024px) {
  .card { padding: 3rem; max-width: 1200px; }
}
```

### Typography

**System font stack** (no web fonts):

```css
font-family: system-ui, -apple-system, BlinkMacSystemFont,
             'Segoe UI', Roboto, sans-serif;
```

**Benefits:**
- Zero load time
- Native OS appearance
- Better text rendering

### Animations

**Transitions:**

```css
.card {
  transition: transform 0.2s ease-out, box-shadow 0.2s ease-out;
}
.card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 6px rgba(0,0,0,0.1);
}
```

**Collapsible content:**

```svelte
<script lang="ts">
  let expanded = $state(false);
</script>

<button onclick={() => expanded = !expanded}>Toggle</button>
{#if expanded}
  <div class="content" transition:slide={{ duration: 200 }}>
    Content here
  </div>
{/if}
```

---

## Development

### Quick Start

```bash
cd frontend
npm install
npm run dev     # Dev server at http://localhost:5173
```

### Build for Production

```bash
npm run build   # Builds to frontend/build/
npm run preview # Preview production build
```

### Cloudflare Pages Deployment

**Automatic deployment:**
1. Push to `main` branch
2. Cloudflare detects changes
3. Builds with `npm run build`
4. Deploys to edge network

**Manual deployment:**
```bash
npm run build
wrangler pages publish build
```

### Common Tasks

**Add a new page:**
1. Create `routes/pagename/+page.svelte`
2. Add load function in `+page.ts` if needed
3. Style in component `<style>` block

**Add a new component:**
1. Create `lib/components/ComponentName.svelte`
2. Export types in `lib/types.ts`
3. Import and use: `import Component from '$lib/components/Component.svelte'`

**Call API:**
```typescript
import { api } from '$lib/api';
const meetings = await api.getMeetings('paloaltoCA');
```

### Debugging

**Dev tools:**
- Svelte DevTools (browser extension)
- `console.log()` in `<script>` blocks
- `{@debug variable}` in templates

**Common issues:**
- **"Hydration mismatch"**: SSR HTML ≠ client render (check conditional logic)
- **"Cannot access X before initialization"**: Use `$effect()` for side effects
- **Styles not applying**: Check CSS specificity, scope

### Testing

**Vitest + Testing Library:**
```bash
npm run test        # Run tests
npm run test:watch  # Watch mode
```

**Example test:**
```typescript
import { render, screen } from '@testing-library/svelte';
import MeetingCard from '$lib/components/MeetingCard.svelte';

test('renders meeting title', () => {
  const meeting = { title: 'City Council' };
  render(MeetingCard, { props: { meeting } });
  expect(screen.getByText('City Council')).toBeInTheDocument();
});
```

---

## See Also

- **API Integration**: See `FRONTEND_DEV_GUIDE.md` for API client details
- **Backend API**: See `docs/API.md` for endpoint reference
- **Historical Docs**: See `docs/archive/frontend-docs-2024-11/` for pre-consolidation documentation
- **SvelteKit Docs**: https://kit.svelte.dev/
- **Svelte 5 Tutorial**: https://learn.svelte.dev/
