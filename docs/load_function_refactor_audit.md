# Load Function Refactor Audit

## Executive Summary

The refactor successfully moves from `onMount` to SvelteKit load functions, eliminating CLS and improving perceived performance. However, there are **5 critical bugs** that will cause runtime errors, plus several performance and architectural improvements to consider.

---

## Critical Bugs (Must Fix)

### 1. Broken Snapshot in City Page
**File:** `frontend/src/routes/[city_url]/+page.svelte:30-31`
**Issue:** References non-existent variables `loading` and `error` in snapshot capture

```typescript
// BROKEN CODE:
capture: () => ({
  showPastMeetings,
  searchResults,
  upcomingMeetings,
  pastMeetings,
  loading,  // ❌ Does not exist
  error,    // ❌ Does not exist
  scrollY: typeof window !== 'undefined' ? window.scrollY : 0
}),
```

**Fix:** Remove these variables from snapshot since load functions handle state

### 2. Missing Type Import
**File:** `frontend/src/routes/[city_url]/+page.svelte:36`
**Issue:** `SearchResult` type used but not imported

```typescript
restore: (values: {
  showPastMeetings: boolean;
  searchResults: SearchResult | null;  // ❌ Not imported
  // ...
```

**Fix:** Add import: `import type { SearchResult } from '$lib/api/types';`

### 3. Incorrect Redirect Implementation
**File:** `frontend/src/routes/[city_url]/+page.ts:10-14`
**Issue:** Returns object instead of using SvelteKit's redirect helper

```typescript
// INCORRECT:
if (city_url === 'about') {
  return {
    redirect: '/about'  // ❌ This does nothing
  };
}
```

**Fix:** Use proper redirect:
```typescript
import { error, redirect } from '@sveltejs/kit';

if (city_url === 'about') {
  throw redirect(307, '/about');
}
```

### 4. No Error Page
**File:** Missing `frontend/src/routes/[city_url]/+error.svelte`
**Issue:** When load function throws error, user sees blank page or default browser error

**Fix:** Create error boundary page to handle 404s gracefully

### 5. Redundant State Passing
**File:** `frontend/src/routes/+page.svelte:90`
**Issue:** Passes searchResults in navigation state, but +page.ts ignores it and refetches

```typescript
goto(`/${cityUrl}`, { state: { searchResults: result } });
// City page load function ignores this and fetches again ❌
```

**Fix:** Either use the passed state or remove the state passing

---

## Performance Improvements

### 6. No Navigation Loading Indicator
**Issue:** User has no feedback during data fetching
**Impact:** Poor UX on slow connections

**Recommendation:** Add loading bar using `$app/stores`:
```typescript
import { navigating } from '$app/stores';

{#if $navigating}
  <div class="loading-bar"></div>
{/if}
```

### 7. No Cache Strategy
**Issue:** Every navigation refetches identical data
**Impact:** Unnecessary API calls, slower navigation, higher costs

**Recommendation:** Add cache headers in load functions:
```typescript
export const load: PageLoad = async ({ fetch }) => {
  const response = await fetch('/api/analytics', {
    headers: { 'Cache-Control': 'max-age=300' } // 5 min cache
  });
  // ...
};
```

### 8. Homepage Refetches on Every Mount
**Issue:** Navigate away and back = refetch analytics/ticker
**Impact:** Wasted API calls for static-ish data

**Recommendation:** Add `maxage` to load function or use SvelteKit's cache

---

## Code Quality Improvements

### 9. Duplicate Date Parsing Logic
**File:** `frontend/src/routes/[city_url]/+page.ts:30-60`
**Issue:** 31 lines of date parsing/splitting logic in load function

**Recommendation:** Extract to utility:
```typescript
// utils/meetings.ts
export function splitMeetingsByDate(meetings: Meeting[]) {
  const now = new Date();
  const upcoming: Meeting[] = [];
  const past: Meeting[] = [];

  for (const meeting of meetings) {
    if (!meeting.date || meeting.date === 'null' || meeting.date === '') {
      upcoming.push(meeting);
      continue;
    }

    const meetingDate = new Date(meeting.date);
    if (isNaN(meetingDate.getTime()) || meetingDate.getTime() === 0) {
      upcoming.push(meeting);
      continue;
    }

    if (meetingDate >= now) {
      upcoming.push(meeting);
    } else {
      past.push(meeting);
    }
  }

  return { upcoming, past };
}
```

Then load function becomes:
```typescript
if (result.meetings) {
  result.meetings.sort(sortMeetingsByDate);
  const { upcoming, past } = splitMeetingsByDate(result.meetings);
  return { searchResults: result, upcomingMeetings: upcoming, pastMeetings: past };
}
```

### 10. Snapshot Might Be Redundant
**Issue:** With load functions, SvelteKit already preserves component state during back/forward navigation

**Recommendation:** Test if snapshots are still needed. They might only be needed for:
- `showPastMeetings` toggle state
- Scroll position

Could simplify to:
```typescript
export const snapshot = {
  capture: () => ({ showPastMeetings, scrollY: window.scrollY }),
  restore: (values) => {
    showPastMeetings = values.showPastMeetings;
    setTimeout(() => window.scrollTo(0, values.scrollY), 0);
  }
};
```

### 11. Missing Type Annotations
**File:** `frontend/src/routes/[city_url]/+page.ts:40-41`

```typescript
const upcomingMeetings = [];  // ❌ Implicit any[]
const pastMeetings = [];      // ❌ Implicit any[]
```

**Fix:**
```typescript
const upcomingMeetings: Meeting[] = [];
const pastMeetings: Meeting[] = [];
```

---

## Architectural Considerations

### 12. SSR vs CSR Strategy
**Question:** Should these load functions run on server or client?

**Current:** Client-side only (no `+page.server.ts`)
**Consideration:**
- Server load = SEO benefits, faster perceived load
- Client load = simpler deployment (no Node server needed)

**Recommendation:** Since you're on Cloudflare Pages (static adapter), client-side is correct. Document this decision.

### 13. Preloading Strategy
**Opportunity:** SvelteKit can preload data on link hover

**Recommendation:** Add to `svelte.config.js`:
```javascript
kit: {
  prerender: {
    crawl: true,
    entries: ['*']
  },
  router: {
    prefetch: 'hover' // Loads data on link hover
  }
}
```

### 14. Error Handling Consistency
**Issue:** Homepage uses try/catch with error state, city page uses thrown errors

**Recommendation:** Pick one pattern:
- **Option A:** All errors thrown (cleaner, uses SvelteKit error pages)
- **Option B:** All errors caught and returned (more control, inline error UI)

---

## Testing Checklist

Before deploying:

- [ ] Fix snapshot variables (bug #1)
- [ ] Add SearchResult import (bug #2)
- [ ] Fix redirect (bug #3)
- [ ] Create +error.svelte (bug #4)
- [ ] Fix redundant state passing (bug #5)
- [ ] Test navigation loading states
- [ ] Test error states (invalid city URL, network failure)
- [ ] Test back/forward navigation with snapshots
- [ ] Test mobile layout shift (the original issue)
- [ ] Verify no console errors on navigation
- [ ] Check bundle size impact

---

## Performance Metrics to Track

After deployment:

1. **Time to Interactive (TTI)** - Should be faster
2. **Cumulative Layout Shift (CLS)** - Should be near 0
3. **API call count** - Should decrease with caching
4. **Navigation speed** - Measure with prefetching
5. **Error rate** - Ensure error handling works

---

## Elegant Solution Missing

The refactor is 80% there, but there's one more insight:

**The Paradox You Sensed:** The homepage and city page are doing the same work twice.

1. User searches "Palo Alto" on homepage
2. Homepage calls `searchMeetings()`
3. Homepage navigates to `/paloaltoCA`
4. City page calls `searchMeetings()` again ← **redundant!**

**The Elegant Fix:**

Use SvelteKit's `load` function dependencies and `invalidate()`:

```typescript
// +page.ts (homepage)
export const load: PageLoad = async ({ depends }) => {
  depends('app:analytics');
  return { analytics, tickerItems };
};

// When search succeeds, pass data to city page via URL
goto(`/${cityUrl}?from=search`, {
  state: { searchResults: result }
});

// [city_url]/+page.ts
export const load: PageLoad = async ({ params, url, data }) => {
  // Check if we came from search with fresh data
  if (url.searchParams.get('from') === 'search') {
    const state = history.state?.searchResults;
    if (state) return processSearchResults(state);
  }

  // Otherwise fetch fresh
  return await fetchCityMeetings(params.city_url);
};
```

This eliminates the double-fetch while keeping load functions as source of truth.

---

## Priority Fix Order

1. **Critical bugs** (1-5) - Fix immediately, will cause errors
2. **Navigation loading** (#6) - Important UX
3. **Extract date logic** (#9) - Code quality win
4. **Error page** (#4) - User experience
5. **Cache strategy** (#7-8) - Performance optimization
6. **Eliminate double-fetch** (Elegant Solution) - Architectural win

---

## Confidence Level

**Refactor Direction:** 9/10 - Correct approach, much better than onMount
**Implementation Quality:** 6/10 - Good start, critical bugs need fixing
**Performance Improvement:** 8/10 - Will be excellent once caching added

The foundation is solid. Fix the bugs, add the missing pieces, and this will rip.
