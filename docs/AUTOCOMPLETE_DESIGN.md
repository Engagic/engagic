# Progressive Autocomplete Design

**Status:** Design Document (Not Implemented)
**Created:** 2025-11-05
**Effort:** ~4-5 hours implementation
**Priority:** High (User retention feature)

---

## Overview

Progressive dynamic autocomplete for the search input on the homepage. As users type city names, zipcodes, or states, real-time suggestions appear with meeting statistics, enabling faster discovery and reducing friction.

**Key Goals:**
- Fast feedback (show suggestions after 3 characters, <100ms response)
- Reduce typing (autocomplete common cities)
- Surface statistics (show meeting counts inline)
- Preserve existing behavior (fallback to full search)
- Mobile-friendly (touch targets, keyboard navigation)

---

## User Experience Flow

```
User types "pal" → [debounce 300ms]
  ↓
GET /api/suggest?q=pal&limit=10
  ↓
Dropdown appears:
  ┌─────────────────────────────────────┐
  │ Palo Alto, CA        [142 | 89 | 76]│
  │ Palm Springs, CA      [89 | 67 | 54]│
  │ Palatine, IL          [56 | 43 | 38]│
  │ Palm Beach, FL        [34 | 28 | 22]│
  └─────────────────────────────────────┘
       [total | packet | summarized]

User presses ↓ (highlights first)
User presses Enter → Navigate to /paloaltoCA
```

**Interaction patterns:**
- Type 1-2 chars: No suggestions (too broad)
- Type 3+ chars: Suggestions appear after 300ms debounce
- Click suggestion: Navigate directly to city page
- Press Enter on input: Full search (existing behavior)
- Press Escape: Close dropdown
- Arrow keys: Navigate suggestions
- Click outside: Close dropdown

---

## Backend Design

### New Endpoint: GET /api/suggest

**Location:** `server/routes/search.py`

**Parameters:**
- `q` (required): Query string (3+ characters)
- `limit` (optional): Max suggestions, default 10

**Response:**
```json
{
  "suggestions": [
    {
      "city_name": "Palo Alto",
      "state": "CA",
      "banana": "paloaltoCA",
      "display_name": "Palo Alto, CA",
      "vendor": "legistar",
      "total_meetings": 142,
      "meetings_with_packet": 89,
      "summarized_meetings": 76
    }
  ],
  "query": "pal"
}
```

**Implementation:**
```python
# server/routes/search.py
@router.get("/suggest")
async def suggest_cities(
    q: str,
    limit: int = 10,
    db: UnifiedDatabase = Depends(get_db)
):
    """
    Fast city suggestions for autocomplete
    Returns city metadata + meeting stats (no full meeting data)
    """
    if len(q) < 3:
        return {"suggestions": [], "query": q}

    # Use existing fuzzy matching logic
    suggestions = handle_city_suggestions(q, limit, db)
    return suggestions
```

**Service function:**
```python
# server/services/search.py
def handle_city_suggestions(query: str, limit: int, db: UnifiedDatabase):
    """
    Get city suggestions with fuzzy matching
    Reuses existing ambiguous city logic but lighter
    """
    query_lower = query.lower().strip()

    # Try exact prefix match first (fast)
    cities = db.get_cities(name_prefix=query_lower)

    # If no match, try fuzzy (existing logic)
    if not cities:
        all_cities = db.get_cities()
        city_names = [city.name.lower() for city in all_cities]
        close_matches = get_close_matches(query_lower, city_names, n=limit, cutoff=0.6)

        if close_matches:
            fuzzy_cities = []
            for match in close_matches:
                matched = db.get_cities(name=match.title())
                fuzzy_cities.extend(matched)
            cities = fuzzy_cities[:limit]

    # Build response with stats
    bananas = [city.banana for city in cities]
    stats = db.get_city_meeting_stats(bananas)

    suggestions = []
    for city in cities:
        city_stats = stats.get(city.banana, {
            "total_meetings": 0,
            "meetings_with_packet": 0,
            "summarized_meetings": 0
        })
        suggestions.append({
            "city_name": city.name,
            "state": city.state,
            "banana": city.banana,
            "display_name": f"{city.name}, {city.state}",
            "vendor": city.vendor,
            "total_meetings": city_stats["total_meetings"],
            "meetings_with_packet": city_stats["meetings_with_packet"],
            "summarized_meetings": city_stats["summarized_meetings"]
        })

    return {"suggestions": suggestions, "query": query}
```

**Database changes needed:**
Add prefix matching to `database/repositories/cities.py`:
```python
def get_cities(self, name_prefix: str = None, ...):
    """Add name_prefix parameter for fast prefix matching"""
    if name_prefix:
        query += " AND LOWER(name) LIKE ?"
        params.append(f"{name_prefix}%")
```

**Performance expectations:**
- Query execution: <20ms (indexed)
- Stats aggregation: <30ms (batch query)
- Total response: <100ms

---

## Frontend Design

### New Component: SearchAutocomplete.svelte

**Location:** `frontend/src/lib/components/SearchAutocomplete.svelte`

**Props:**
- `placeholder: string` (default: "Enter zipcode, city, or state")
- `disabled: boolean` (default: false)
- `onselect: (banana: string) => void` (callback when suggestion selected)

**Component structure:**
```svelte
<script lang="ts">
  import { onMount } from 'svelte';

  let searchQuery = $state('');
  let suggestions = $state<CitySuggestion[]>([]);
  let showDropdown = $state(false);
  let selectedIndex = $state(-1);
  let loading = $state(false);
  let debounceTimer: ReturnType<typeof setTimeout>;

  // Debounced fetch
  async function fetchSuggestions(query: string) {
    if (query.length < 3) {
      suggestions = [];
      showDropdown = false;
      return;
    }

    loading = true;
    try {
      const result = await apiClient.getSuggestions(query);
      suggestions = result.suggestions;
      showDropdown = suggestions.length > 0;
      selectedIndex = -1;
    } catch (err) {
      logger.error('Suggestion fetch failed', err);
      suggestions = [];
    } finally {
      loading = false;
    }
  }

  // Handle input with debounce
  function handleInput() {
    clearTimeout(debounceTimer);

    if (searchQuery.length < 3) {
      suggestions = [];
      showDropdown = false;
      return;
    }

    debounceTimer = setTimeout(() => {
      fetchSuggestions(searchQuery);
    }, 300);
  }

  // Keyboard navigation
  function handleKeydown(event: KeyboardEvent) {
    if (!showDropdown) {
      if (event.key === 'Enter') {
        // Trigger full search (existing behavior)
        onFullSearch(searchQuery);
      }
      return;
    }

    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        selectedIndex = Math.min(selectedIndex + 1, suggestions.length - 1);
        break;
      case 'ArrowUp':
        event.preventDefault();
        selectedIndex = Math.max(selectedIndex - 1, -1);
        break;
      case 'Enter':
        event.preventDefault();
        if (selectedIndex >= 0) {
          selectSuggestion(suggestions[selectedIndex]);
        } else {
          onFullSearch(searchQuery);
        }
        break;
      case 'Escape':
        event.preventDefault();
        showDropdown = false;
        selectedIndex = -1;
        break;
    }
  }

  // Select suggestion
  function selectSuggestion(suggestion: CitySuggestion) {
    showDropdown = false;
    suggestions = [];
    selectedIndex = -1;
    onselect(suggestion.banana);
  }

  // Click outside to close
  function handleClickOutside(event: MouseEvent) {
    const target = event.target as HTMLElement;
    if (!target.closest('.autocomplete-container')) {
      showDropdown = false;
      selectedIndex = -1;
    }
  }

  onMount(() => {
    document.addEventListener('click', handleClickOutside);
    return () => {
      document.removeEventListener('click', handleClickOutside);
      clearTimeout(debounceTimer);
    };
  });
</script>

<div class="autocomplete-container">
  <input
    type="text"
    class="search-input"
    bind:value={searchQuery}
    oninput={handleInput}
    onkeydown={handleKeydown}
    placeholder={placeholder}
    disabled={disabled}
    aria-autocomplete="list"
    aria-controls="suggestions-list"
    aria-expanded={showDropdown}
  />

  {#if loading}
    <div class="loading-indicator">...</div>
  {/if}

  {#if showDropdown}
    <ul
      id="suggestions-list"
      class="suggestions-dropdown"
      role="listbox"
    >
      {#each suggestions as suggestion, index}
        <li
          class="suggestion-item"
          class:selected={index === selectedIndex}
          role="option"
          aria-selected={index === selectedIndex}
          onclick={() => selectSuggestion(suggestion)}
        >
          <div class="suggestion-main">
            <span class="city-name">{suggestion.display_name}</span>
            <span class="vendor-badge">{suggestion.vendor}</span>
          </div>
          <div class="suggestion-stats">
            <span class="stat-total">{suggestion.total_meetings}</span>
            <span class="stat-separator">|</span>
            <span class="stat-packets">{suggestion.meetings_with_packet}</span>
            <span class="stat-separator">|</span>
            <span class="stat-summaries">{suggestion.summarized_meetings}</span>
          </div>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .autocomplete-container {
    position: relative;
    width: 100%;
  }

  .suggestions-dropdown {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    margin-top: 0.5rem;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    max-height: 400px;
    overflow-y: auto;
    z-index: 1000;
    list-style: none;
    padding: 0;
    margin: 0;
  }

  .suggestion-item {
    padding: 0.75rem 1rem;
    cursor: pointer;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid var(--color-border-light);
    transition: background-color 0.15s ease;
  }

  .suggestion-item:last-child {
    border-bottom: none;
  }

  .suggestion-item:hover,
  .suggestion-item.selected {
    background-color: var(--color-hover);
  }

  .suggestion-main {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex: 1;
  }

  .city-name {
    font-weight: 500;
    color: var(--color-text);
  }

  .vendor-badge {
    font-size: 0.75rem;
    padding: 0.125rem 0.375rem;
    background: var(--color-muted);
    border-radius: 4px;
    color: var(--color-text-secondary);
  }

  .suggestion-stats {
    display: flex;
    gap: 0.375rem;
    font-size: 0.875rem;
    color: var(--color-text-secondary);
    font-family: ui-monospace, monospace;
  }

  .stat-total {
    color: var(--color-text-secondary);
  }

  .stat-packets {
    color: var(--color-primary);
  }

  .stat-summaries {
    color: var(--color-success);
  }

  .loading-indicator {
    position: absolute;
    right: 1rem;
    top: 50%;
    transform: translateY(-50%);
    color: var(--color-text-secondary);
  }

  /* Mobile optimizations */
  @media (max-width: 640px) {
    .suggestions-dropdown {
      max-height: 300px;
      font-size: 0.875rem;
    }

    .suggestion-item {
      padding: 0.625rem 0.75rem;
    }

    .vendor-badge {
      display: none; /* Save space on mobile */
    }

    .suggestion-stats {
      font-size: 0.75rem;
    }
  }
</style>
```

**API client addition:**
```typescript
// frontend/src/lib/api/api-client.ts
async getSuggestions(query: string): Promise<SuggestionsResult> {
  const response = await this.get(`/suggest?q=${encodeURIComponent(query)}`);
  return response.data;
}
```

**Type definitions:**
```typescript
// frontend/src/lib/api/types.ts
export interface CitySuggestion {
  city_name: string;
  state: string;
  banana: string;
  display_name: string;
  vendor: string;
  total_meetings: number;
  meetings_with_packet: number;
  summarized_meetings: number;
}

export interface SuggestionsResult {
  suggestions: CitySuggestion[];
  query: string;
}
```

---

## Integration into Homepage

**Replace existing search input in `frontend/src/routes/+page.svelte`:**

```svelte
<script lang="ts">
  import SearchAutocomplete from '$lib/components/SearchAutocomplete.svelte';

  function handleCitySelect(banana: string) {
    // Navigate directly to city page
    goto(`/${banana}`);
  }

  function handleFullSearch(query: string) {
    // Fallback to existing search logic
    // (zipcodes, state searches, etc.)
    searchQuery = query;
    handleSearch();
  }
</script>

<SearchAutocomplete
  placeholder="Enter zipcode, city, or state"
  disabled={loading}
  onselect={handleCitySelect}
  onfullsearch={handleFullSearch}
/>
```

---

## Edge Cases & Considerations

### 1. Zipcode Handling
**Issue:** Autocomplete is for cities, but we also support zipcodes
**Solution:** If input is 5 digits, skip autocomplete and do full search

```typescript
function handleInput() {
  if (/^\d{5}$/.test(searchQuery)) {
    // It's a zipcode - skip autocomplete
    suggestions = [];
    showDropdown = false;
    return;
  }
  // Normal autocomplete flow...
}
```

### 2. State Searches
**Issue:** User types "California" - should we show all cities?
**Solution:** Detect state queries and show state disambiguation (existing behavior)

```typescript
function handleInput() {
  if (isStateQuery(searchQuery)) {
    // Trigger state search instead
    suggestions = [];
    showDropdown = false;
    return;
  }
  // Normal autocomplete flow...
}
```

### 3. Rate Limiting
**Issue:** Rapid typing could spam backend
**Solution:** 300ms debounce (implemented) + request cancellation

```typescript
let abortController: AbortController;

async function fetchSuggestions(query: string) {
  // Cancel previous request
  abortController?.abort();
  abortController = new AbortController();

  try {
    const result = await apiClient.getSuggestions(query, {
      signal: abortController.signal
    });
    // ...
  } catch (err) {
    if (err.name === 'AbortError') return; // Ignore cancelled requests
    // Handle other errors...
  }
}
```

### 4. Mobile Experience
**Challenge:** Small screen, touch targets, keyboard
**Solution:**
- Larger touch targets (48px min height)
- Hide vendor badge on mobile (save space)
- Close dropdown on scroll
- Support both tap and keyboard

### 5. Accessibility
**Requirements:**
- Screen reader announcements
- ARIA attributes (aria-autocomplete, aria-controls, aria-expanded)
- Keyboard navigation (arrows, enter, escape)
- Focus management

```svelte
<input
  aria-autocomplete="list"
  aria-controls="suggestions-list"
  aria-expanded={showDropdown}
  aria-activedescendant={selectedIndex >= 0 ? `suggestion-${selectedIndex}` : undefined}
/>

<ul id="suggestions-list" role="listbox">
  {#each suggestions as suggestion, index}
    <li
      id={`suggestion-${index}`}
      role="option"
      aria-selected={index === selectedIndex}
    >
      <!-- ... -->
    </li>
  {/each}
</ul>
```

### 6. Performance
**Optimization points:**
- Debounce: 300ms (tuned for responsiveness vs load)
- Limit: 10 suggestions (balance UX vs query cost)
- Prefix index: LOWER(name) LIKE 'query%' (fast)
- Request cancellation: Abort in-flight requests
- Cache: Consider client-side caching for repeated queries

### 7. Empty States
**Scenarios:**
- No matches found: Show "No cities found" message
- Query too short: Show nothing (wait for 3+ chars)
- Error state: Fall back to full search

---

## Implementation Phases

### Phase 1: Backend (1 hour)
1. Add `/api/suggest` endpoint to `server/routes/search.py`
2. Add `handle_city_suggestions()` to `server/services/search.py`
3. Add `name_prefix` parameter to `database/repositories/cities.py`
4. Test with curl: `curl "http://localhost:8000/api/suggest?q=palo"`

### Phase 2: Frontend Component (2 hours)
1. Create `SearchAutocomplete.svelte` component
2. Add API client method `getSuggestions()`
3. Add TypeScript types to `types.ts`
4. Implement debounce, keyboard nav, click outside
5. Style dropdown with existing design system

### Phase 3: Integration (30 minutes)
1. Replace search input in `+page.svelte` with new component
2. Wire up navigation callbacks
3. Preserve existing search button behavior

### Phase 4: Polish (1 hour)
1. Test on mobile (touch, viewport, keyboard)
2. Add loading states
3. Tune debounce timing (300ms baseline)
4. Handle edge cases (zipcodes, states)
5. Accessibility audit (keyboard, screen reader)
6. Error handling and fallbacks

### Phase 5: Testing (30 minutes)
1. Manual testing: Type, keyboard nav, mobile
2. Edge cases: Empty, errors, slow network
3. Cross-browser: Chrome, Safari, Firefox
4. A/B comparison: Time to first click vs old UI

---

## Success Metrics

**User behavior:**
- % of searches using autocomplete vs full search
- Time to first city click (should decrease)
- Bounce rate on homepage (should decrease)
- Mobile vs desktop usage patterns

**Technical:**
- Autocomplete endpoint latency (target: <100ms p95)
- Error rate (target: <0.1%)
- Suggestion relevance (fuzzy match accuracy)

---

## Future Enhancements

**Not in initial scope:**

1. **Recent searches** - Store last 5 searches in localStorage
2. **Popular cities** - Show trending cities when input is empty
3. **Highlights** - Bold matching characters in suggestions
4. **Icons** - Vendor icons next to city names
5. **Metadata** - Show last updated time, city population
6. **Caching** - Client-side cache for repeated queries
7. **Prefetch** - Preload top 3 suggestions on hover
8. **Analytics** - Track which suggestions users click

---

## Technical Specifications

### Dependencies
- **Backend:** None (uses existing database, services)
- **Frontend:** None (vanilla Svelte, no autocomplete library)

### Browser Support
- Chrome 90+
- Safari 14+
- Firefox 88+
- Mobile: iOS Safari 14+, Chrome Android 90+

### Performance Budget
- Endpoint response: <100ms p95
- Component render: <16ms (60fps)
- Dropdown animation: CSS transitions (GPU-accelerated)
- Bundle size impact: +5KB gzipped (component + styles)

### Database Impact
- Add index: `CREATE INDEX idx_cities_name_lower ON cities(LOWER(name))`
- Query complexity: Simple prefix match + existing stats query
- Load impact: Minimal (cache-first, debounced, limited to 10 results)

---

## Questions & Decisions

### Q: Should we show suggestions for incomplete words?
**A:** Yes, after 3 characters. "pal" → "Palo Alto" (fuzzy match handles this)

### Q: What about cities with no meetings?
**A:** Show them with [0 | 0 | 0] stats. Still useful for discovery.

### Q: Should zipcode autocomplete show nearby cities?
**A:** No, keep zipcode behavior as-is (direct resolution). Only cities get autocomplete.

### Q: Mobile keyboard: Should Enter submit or select?
**A:** If dropdown is open and item highlighted: Select. Otherwise: Full search.

### Q: Should we cache suggestions client-side?
**A:** Not in v1. Add if latency becomes issue. Backend is fast enough (<100ms).

### Q: Should we prefetch top cities on page load?
**A:** No. Wait for user to type. Reduces initial load, respects bandwidth.

---

## Related Documentation

- `FRONTEND_COMPONENTS.md` - Component architecture
- `FRONTEND_API.md` - API client patterns
- `API.md` - Backend endpoint reference
- `SCHEMA.md` - Database schema and indexes

---

**Last Updated:** 2025-11-05
**Implementation Status:** Design complete, not yet implemented
**Next Step:** Build Phase 1 (backend endpoint)
