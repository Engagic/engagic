# Frontend Changelog

All notable changes to the Engagic frontend are documented here.

**Tech Stack**: SvelteKit 2.x (Svelte 5 runes), TypeScript, Cloudflare Pages

Format: [Date] - [Component] - [Change Description]

---

## [2025-11-04] Flyer Generation: Clear Separation of Concerns

**Philosophy achieved.** Refactored flyer functionality to enforce "backend = data, frontend = display" principle with type safety and single source of truth.

**Problems Identified:**
1. **CSS in Python** - 170 lines of CSS hardcoded in Python f-string
2. **No type safety** - Position values and constraints duplicated across backend/frontend
3. **Template maintenance** - HTML structure mixed with Python logic
4. **Constraint duplication** - Max lengths defined in multiple places

**Optimizations:**

**1. Extracted CSS into Template** (`server/services/flyer_template.html`)
- Created standalone HTML template file (195 lines)
- Removed CSS from Python string literal
- Clean `.format()` substitution for data injection
- `flyer.py` reduced from 442 → 244 lines (45% smaller)

**2. Added TypeScript Type Safety** (`src/lib/api/types.ts:161-182`)
```typescript
type FlyerPosition = 'support' | 'oppose' | 'more_info';
interface FlyerRequest { meeting_id, item_id, position, custom_message, user_name }
const FLYER_CONSTRAINTS = { MAX_MESSAGE_LENGTH: 500, MAX_NAME_LENGTH: 100 }
```
- Mirrors backend Pydantic models
- Compile-time validation of position values
- Documents API contract

**3. Single Source of Truth** (`src/routes/[city_url]/[meeting_slug]/+page.svelte`)
- Replaced hardcoded `maxlength="500"` with `FLYER_CONSTRAINTS.MAX_MESSAGE_LENGTH`
- Added reactive enforcement via `$effect()` to trim overlong inputs
- Character counters use constant values

**4. Verified Separation**
- Backend `_clean_summary_for_flyer()`: LLM artifacts → HTML for print
- Frontend `cleanSummary()`: LLM artifacts → markdown for web display
- Different outputs for different contexts (not duplication)

**Impact:**
- ✅ 45% smaller backend service file
- ✅ Type-safe flyer state and requests
- ✅ Constraints defined once, enforced everywhere
- ✅ Template changes don't require Python edits
- ✅ Clear contract between backend/frontend

**Files Modified:**
- `server/services/flyer.py` - Extracted CSS, use template (442 → 244 lines)
- `server/services/flyer_template.html` - NEW, clean HTML template
- `src/lib/api/types.ts` - Added `FlyerRequest`, `FlyerPosition`, `FLYER_CONSTRAINTS`
- `src/routes/[city_url]/[meeting_slug]/+page.svelte` - Typed state, reactive constraints

**Developer Experience:**
- CSS changes in proper HTML file (not Python)
- TypeScript catches position typos at compile time
- Frontend/backend constraints stay in sync automatically

---

## [2025-11-02] Meeting Detail Page: Redesign with System Typography

**The redesign.** Complete visual overhaul of meeting detail page with collapsible items, system sans-serif typography, and improved thinking trace display.

**Visual Changes:**

**1. Typography Upgrade**
- Switched from IBM Plex Mono to system sans-serif stack:
  ```css
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
               "Helvetica Neue", Arial, sans-serif;
  ```
- Better readability for long-form content
- Native OS fonts load instantly (no web font delay)
- Consistent with modern web applications

**2. Collapsible Item UI** (`+page.svelte`)
- Items collapsed by default (show title + first 2 lines)
- Click anywhere to expand full summary
- Visual indicator: "▶ Click to expand" / "▼ Click to collapse"
- Smooth transitions for better UX
- Persistent state using `SvelteSet<string>` for `expandedItems`

**3. Thinking Trace Integration**
- "💭 Thinking trace (click to expand/collapse)" button
- Nested within item summary (not separate section)
- Markdown rendering via `marked()` for bullet formatting
- Collapsible to reduce clutter

**4. Improved Visual Hierarchy**
- Meeting header: larger city name, prominent date
- Item titles: truncate at semicolon, "..." expansion toggle
- Summary sections: gray background, left border accent
- Action buttons: consistent styling across item/meeting level

**Layout Improvements:**
- Responsive max-width containers
- Proper spacing between sections
- Clear visual separation of agenda items
- Mobile-friendly touch targets

**Impact:**
- ✅ Faster page load (no web fonts)
- ✅ Better content scannability
- ✅ Reduced visual clutter (collapsed by default)
- ✅ Native platform look and feel

**Files Modified:**
- `src/routes/[city_url]/[meeting_slug]/+page.svelte` - Complete redesign (2,079 lines)
- Thinking parsing logic: `parseSummaryForThinking()` (lines 94-130)
- Collapsible state management: `expandedItems`, `expandedThinking` SvelteSet
- Typography: System font stack throughout

---

## [2025-11] Foundation: SvelteKit 2 + Svelte 5 Runes

**The foundation.** Initial SvelteKit 2 application with Svelte 5 runes for reactive state management.

**Architecture:**

**1. Routes**
- `/` - Homepage with city search
- `/[city_url]` - City meetings list
- `/[city_url]/[meeting_slug]` - Meeting detail with items
- Server-side data loading via `+page.server.ts`

**2. State Management**
- Svelte 5 runes: `$state`, `$derived`, `$effect`
- No external state library needed
- Reactive derived values for computed properties
- `SvelteSet` for managing expanded/collapsed UI state

**3. API Client** (`src/lib/api/`)
- Typed API responses with discriminated unions
- Error handling with `ApiError` and `NetworkError`
- Config management for base URLs
- Functions: `searchMeetings`, `getMeeting`, `getAnalytics`, `searchByTopic`

**4. Components**
- `Footer.svelte` - Site footer with links
- Markdown rendering via `marked` library
- Date utilities for formatting

**5. TypeScript Types** (`src/lib/api/types.ts`)
- `SearchResult` - Discriminated union (success | ambiguous | error)
- `Meeting` - Meeting with optional items array
- `AgendaItem` - Individual agenda items with summaries
- `CityOption` - City selection data
- Type guards: `isSearchSuccess()`, `isSearchAmbiguous()`, `isSearchError()`

**6. Styling**
- CSS custom properties for theming
- Responsive design with mobile-first approach
- Print-optimized styles for flyer generation
- System fonts for performance

**Deployment:**
- Cloudflare Pages for static hosting
- Edge-optimized SvelteKit adapter
- Environment-based config (dev/prod API URLs)

**Philosophy:**
- Backend handles data processing and HTML generation
- Frontend handles presentation and user interaction
- Type-safe contracts between frontend/backend
- Progressive enhancement (works without JS for basic navigation)

**Tech Decisions:**
- Svelte 5 runes over stores (simpler, more performant)
- TypeScript strict mode (catch errors at compile time)
- Discriminated unions for exhaustive type checking
- No CSS framework (custom CSS for full control)

---

**Last Updated:** 2025-11-04

**See Also:**
- Backend CHANGELOG.md for server/database changes
- CLAUDE.md for overall architecture documentation
- VISION.md for roadmap and feature planning
