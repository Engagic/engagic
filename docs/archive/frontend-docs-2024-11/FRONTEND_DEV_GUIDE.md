# Frontend Development Guide

**Last Updated:** 2025-11-02
**Node Version:** 18+ required
**Package Manager:** npm (comes with Node)

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Development Workflow](#development-workflow)
3. [Common Tasks](#common-tasks)
4. [Debugging](#debugging)
5. [Testing](#testing)
6. [Build & Deploy](#build--deploy)
7. [Troubleshooting](#troubleshooting)

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
cd /path/to/engagic/frontend

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

**File Structure Recap:**

```
src/
├── lib/                 # Shared code (components, utils, API)
│   ├── components/      # Reusable UI components
│   ├── api/             # API client
│   ├── utils/           # Helper functions
│   └── services/        # Business logic
│
└── routes/              # File-based routing
    ├── +layout.svelte   # Root layout
    ├── +page.svelte     # Homepage
    ├── about/           # About page
    ├── [city_url]/      # Dynamic city routes
    └── service-worker.ts  # PWA service worker
```

### Hot Module Replacement (HMR)

**Changes auto-reload:**
- `.svelte` files → Component reloads
- `.ts` files → Full page reload
- `.css` files → Style hot swap
- `+page.ts` → Page data reloads

**No need to manually refresh!**

---

## Common Tasks

### 1. Add a New Page

```bash
# Create new route directory
mkdir src/routes/new-page

# Create page component
touch src/routes/new-page/+page.svelte
```

**Basic page template:**

```svelte
<script lang="ts">
  import Footer from '$lib/components/Footer.svelte';
</script>

<svelte:head>
  <title>New Page - engagic</title>
</svelte:head>

<div class="container">
  <div class="main-content">
    <h1>New Page</h1>
    <p>Content goes here...</p>
  </div>

  <Footer />
</div>
```

**Access at:** `http://localhost:5173/new-page`

### 2. Add a Data Loader

```bash
# Create load function
touch src/routes/new-page/+page.ts
```

```typescript
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ params }) => {
  // Fetch data
  const data = await fetchData();

  return {
    data
  };
};
```

**Receive in component:**

```svelte
<script lang="ts">
  import type { PageData } from './$types';

  let { data }: { data: PageData } = $props();
</script>

<div>{data.someField}</div>
```

### 3. Add a New Component

```bash
# Create component file
touch src/lib/components/MyComponent.svelte
```

```svelte
<script lang="ts">
  interface Props {
    title: string;
    count?: number;
  }

  let { title, count = 0 }: Props = $props();
</script>

<div class="my-component">
  <h2>{title}</h2>
  <p>Count: {count}</p>
</div>

<style>
  .my-component {
    padding: 1rem;
    border: 1px solid var(--civic-border);
  }
</style>
```

**Use in page:**

```svelte
<script>
  import MyComponent from '$lib/components/MyComponent.svelte';
</script>

<MyComponent title="Hello" count={5} />
```

### 4. Add API Endpoint Support

**1. Add type to `lib/api/types.ts`:**

```typescript
export interface NewDataType {
  id: number;
  name: string;
}
```

**2. Add method to `lib/api/api-client.ts`:**

```typescript
export const apiClient = {
  // ... existing methods

  async getNewData(): Promise<NewDataType> {
    const response = await fetchWithRetry(
      `${config.apiBaseUrl}/api/new-endpoint`
    );
    return response.json();
  }
};
```

**3. Export from `lib/api/index.ts`:**

```typescript
export const getNewData = apiClient.getNewData.bind(apiClient);
```

**4. Use in load function:**

```typescript
import { getNewData } from '$lib/api/index';

export const load: PageLoad = async () => {
  const data = await getNewData();
  return { data };
};
```

### 5. Add Environment Variable

```bash
# Create .env file in frontend/ directory
echo "VITE_NEW_VAR=value" >> .env
```

**Access in code:**

```typescript
const value = import.meta.env.VITE_NEW_VAR;
```

**IMPORTANT:** Prefix must be `VITE_` for client code access.

### 6. Add Global CSS

**In `src/app.css`:**

```css
/* Add at end of file */
.my-utility-class {
  color: var(--civic-blue);
  font-weight: 600;
}
```

**Automatically available everywhere** (imported in `+layout.svelte`).

---

## Debugging

### Browser DevTools

**Chrome/Firefox DevTools:**

1. **Open DevTools** - F12 or Cmd+Option+I (Mac)
2. **Sources tab** - View source files, set breakpoints
3. **Console tab** - See logs, errors, warnings
4. **Network tab** - Monitor API calls
5. **Application tab** - Check localStorage, service workers

### Svelte DevTools

**Chrome Extension:**

1. Install from [Chrome Web Store](https://chrome.google.com/webstore/detail/svelte-devtools)
2. Open DevTools → "Svelte" tab
3. Inspect component hierarchy
4. View component state
5. Track state changes

### Console Logging

**Development logging:**

```typescript
import { logger } from '$lib/services/logger';

// Info logging
logger.info('User clicked button', { userId: 123 });

// Error logging
logger.error('API call failed', error, { endpoint: '/api/search' });

// Event tracking
logger.trackEvent('search_success', { query: 'Austin' });
```

**Production logs:**
- Stored in localStorage (last 100)
- Access: `localStorage.getItem('engagic_logs')`
- Future: Send to monitoring service

### Common Issues

**1. Port already in use**

```bash
# Error: Port 5173 is already in use
# Solution: Kill existing process or use different port
npm run dev -- --port 5174
```

**2. Import errors**

```bash
# Error: Cannot find module '$lib/...'
# Solution: Run SvelteKit sync
npx svelte-kit sync
```

**3. Type errors**

```bash
# Run type checking
npm run check

# Watch mode (live feedback)
npm run check:watch
```

**4. Stale cache**

```bash
# Clear SvelteKit cache
rm -rf .svelte-kit

# Reinstall dependencies
rm -rf node_modules
npm install
```

---

## Testing

### Manual Testing

**No automated tests yet.** Manual testing workflow:

1. **Feature testing**
   - Test all user flows
   - Check responsive design (mobile/tablet/desktop)
   - Test keyboard navigation
   - Test with screen reader (VoiceOver/NVDA)

2. **Cross-browser testing**
   - Chrome (primary)
   - Firefox
   - Safari
   - Edge

3. **Accessibility testing**
   - Run Lighthouse audit
   - Test keyboard-only navigation
   - Check color contrast
   - Verify ARIA labels

### Type Checking

```bash
# Check types
npm run check

# Watch mode
npm run check:watch
```

**TypeScript catches:**
- Missing props
- Wrong types
- Undefined variables
- Typos in property names

### Lighthouse Audit

**Chrome DevTools:**

1. Open DevTools → Lighthouse tab
2. Select categories (Performance, Accessibility, Best Practices, SEO)
3. Run audit
4. Review scores and recommendations

**Target scores:**
- Performance: 90+
- Accessibility: 95+
- Best Practices: 95+
- SEO: 95+

---

## Build & Deploy

### Local Build

```bash
# Create production build
npm run build

# Preview production build
npm run preview
```

**Build output:** `.svelte-kit/output/`

**Build process:**
1. TypeScript compilation
2. Svelte component compilation
3. CSS extraction and minification
4. JavaScript bundling and minification
5. Asset optimization
6. Cloudflare adapter processing

### Deployment (Cloudflare Workers)

**Automated via GitHub Actions:**

1. Push to `main` branch
2. GitHub Actions runs
3. Build happens in CI
4. Deploy to Cloudflare Workers
5. Available at `https://engagic.org`

**Manual deployment (if needed):**

```bash
# Build locally
npm run build

# Deploy with Wrangler (requires Cloudflare account)
npx wrangler pages deploy .svelte-kit/output
```

### Environment Variables (Production)

**Cloudflare dashboard:**

1. Go to Workers & Pages → engagic
2. Settings → Environment Variables
3. Add production variables
4. Redeploy

**Required production env vars:**
- `VITE_API_BASE_URL` - API endpoint (https://api.engagic.org)

---

## Troubleshooting

### Build Fails

**"Cannot find module"**

```bash
# Reinstall dependencies
rm -rf node_modules package-lock.json
npm install
```

**"Out of memory"**

```bash
# Increase Node memory
export NODE_OPTIONS="--max-old-space-size=4096"
npm run build
```

**"Type error"**

```bash
# Run type checking to see specific errors
npm run check
```

### Dev Server Issues

**"Address already in use"**

```bash
# Find process using port 5173
lsof -i :5173

# Kill it
kill -9 <PID>

# Or use different port
npm run dev -- --port 5174
```

**"Module not found"**

```bash
# Sync SvelteKit types
npx svelte-kit sync
```

**"Hot reload not working"**

```bash
# Restart dev server
# Ctrl+C to stop
npm run dev
```

### API Connection Issues

**Check API is running:**

```bash
# Test API endpoint
curl https://api.engagic.org/api/analytics
```

**Use local API for development:**

```bash
# In .env
VITE_API_BASE_URL=http://localhost:8000

# Restart dev server
```

### Type Issues

**"Property does not exist on type"**

- Check type definitions in `lib/api/types.ts`
- Make sure interfaces match API responses
- Use optional chaining: `meeting?.date`

**"Cannot find name"**

- Check import paths
- Verify file exists
- Run `npx svelte-kit sync`

---

## Development Tips

### Productivity

**1. Use TypeScript**
- Catch errors before runtime
- Get autocomplete everywhere
- Refactor with confidence

**2. Use SvelteKit DevTools**
- Inspect component state
- Track reactivity
- Debug navigation

**3. Keep dev server running**
- Hot reload is instant
- See errors immediately
- No manual refresh

**4. Use type checking in watch mode**
```bash
npm run check:watch
```

**5. Learn keyboard shortcuts**
- Cmd+P - Quick file open (VS Code)
- Cmd+Shift+F - Global search
- F12 - Go to definition

### Code Quality

**Before committing:**

```bash
# 1. Type check
npm run check

# 2. Build test
npm run build

# 3. Manual test in browser
npm run preview
```

**Git workflow (reminder):**

```bash
# User handles all git commands
# Just tell them when code is ready

# Example message to user:
"Feature is complete and tested. Ready to commit:
- Added [feature name]
- Updated types
- No console errors
- Tested mobile/desktop"
```

---

## Quick Reference

### Commands

```bash
npm run dev          # Start dev server
npm run build        # Production build
npm run preview      # Preview production build
npm run check        # Type checking
npm run check:watch  # Type checking (watch mode)
```

### Imports

```typescript
// Components
import MyComponent from '$lib/components/MyComponent.svelte';

// API
import { searchMeetings } from '$lib/api/index';

// Utils
import { generateCityUrl } from '$lib/utils/utils';

// SvelteKit
import { goto } from '$app/navigation';
import { page } from '$app/stores';

// Types
import type { Meeting } from '$lib/api/types';
import type { PageData } from './$types';
```

### File Paths

- `$lib` → `src/lib/`
- `$app` → SvelteKit internal modules
- `./$types` → Generated types for current route

---

**Last Updated:** 2025-11-02
**See Also:**
- [FRONTEND.md](./FRONTEND.md) - Architecture overview
- [FRONTEND_COMPONENTS.md](./FRONTEND_COMPONENTS.md) - Component reference
- [FRONTEND_ROUTING.md](./FRONTEND_ROUTING.md) - Routing guide
- [FRONTEND_API.md](./FRONTEND_API.md) - API integration
- [FRONTEND_STYLING.md](./FRONTEND_STYLING.md) - Styling system
