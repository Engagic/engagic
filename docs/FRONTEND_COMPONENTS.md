# Frontend Components Reference

**Last Updated:** 2025-11-02
**Component Count:** 3 shared components
**Total Lines:** ~637 lines of Svelte

---

## Table of Contents

1. [Overview](#overview)
2. [MeetingCard](#meetingcard)
3. [SimpleMeetingList](#simplemeetinglist)
4. [Footer](#footer)
5. [Component Patterns](#component-patterns)
6. [Creating New Components](#creating-new-components)

---

## Overview

We have a **minimal component library by design.** Most UI is in route components, not extracted into shared components. Only create shared components when:

1. **Reused 3+ times** across different routes
2. **Complex enough** to warrant isolation (>100 lines)
3. **Stable API** unlikely to change frequently

### Current Shared Components

| Component | Lines | Purpose | Used In |
|-----------|-------|---------|---------|
| MeetingCard | 467 | Display meeting summary in list | City pages |
| SimpleMeetingList | 84 | Minimal meeting list | (Backup/legacy) |
| Footer | 86 | Site footer with links | All pages |

---

## MeetingCard

**File:** `lib/components/MeetingCard.svelte` (467 lines)
**Purpose:** Primary UI for displaying meeting information in list views

### Props API

```typescript
interface Props {
  meeting: Meeting;           // Meeting data object (required)
  cityUrl: string;            // City URL slug for navigation (required)
  isPast?: boolean;           // Style as past meeting (default: false)
  animationDelay?: number;    // Stagger animation delay in ms (default: 0)
  animationDuration?: number; // Animation duration in ms (default: 0)
  onIntroEnd?: () => void;    // Callback when animation completes
}
```

### Usage Example

```svelte
<script>
  import MeetingCard from '$lib/components/MeetingCard.svelte';
  import type { Meeting } from '$lib/api/types';

  let meetings: Meeting[] = $state([...]);
  let cityUrl = 'paloaltoCA';
</script>

{#each meetings as meeting, index}
  <MeetingCard
    {meeting}
    {cityUrl}
    isPast={false}
    animationDuration={300}
    animationDelay={index * 50}
    onIntroEnd={() => console.log('Animation done')}
  />
{/each}
```

### Visual States

**Border color indicates data availability:**

1. **Green border** (AI Summary)
   - Has `meeting.summary` OR
   - Has items with summaries

2. **Yellow border** (Agenda Available)
   - Has `meeting.agenda_url`
   - No AI summary yet

3. **Orange border** (Meeting Packet)
   - Has `meeting.packet_url`
   - No agenda or summary

4. **Gray border** (No Documents)
   - No documents available yet

5. **Red border** (Alert)
   - Meeting cancelled/postponed
   - `meeting.meeting_status` set

### Topics Display

**Responsive topic limiting:**
- **Mobile (≤640px):** Show first 3 topics + "+N more"
- **Desktop (>640px):** Show first 5 topics + "+N more"

**Implementation:**
```typescript
let isMobile = $state(false);

onMount(() => {
  isMobile = window.innerWidth <= 640;
  // Listen for resize...
});
```

```svelte
{@const maxTopics = isMobile ? 3 : 5}
{@const displayTopics = meeting.topics.slice(0, maxTopics)}
{@const remainingCount = meeting.topics.length - maxTopics}
```

### Status Indicators

**Right column shows data status:**

```svelte
{#if meeting.items?.some(item => item.summary)}
  <div class="meeting-status status-items">
    <span class="status-icon">✓</span> AI Summary
  </div>
{:else if meeting.summary}
  <div class="meeting-status status-summary">
    <span class="status-icon">✓</span> AI Summary
  </div>
{:else if meeting.agenda_url}
  <div class="meeting-status status-agenda">
    <span class="status-icon">📄</span> Agenda Available
  </div>
{:else if meeting.packet_url}
  <div class="meeting-status status-packet">
    <span class="status-icon">📋</span> Meeting Packet
  </div>
{:else}
  <div class="meeting-status status-none">
    <span class="status-icon">⏳</span> Coming Soon
  </div>
{/if}
```

### Animations

**Staggered entrance using Svelte transitions:**

```svelte
<a
  in:fly|global={{ y: 20, duration: animationDuration, delay: animationDelay }}
  onintroend={onIntroEnd}
>
```

**Purpose:**
- `y: 20` - Slide up from 20px below
- `duration` - How long animation lasts
- `delay` - Stagger each card (index * 50ms)
- `|global` - Play even when parent isn't transitioning
- `onintroend` - Callback when done (used to disable for snapshot restores)

### Date Handling

**Robust date parsing and formatting:**

```typescript
const date = $derived(meeting.date ? new Date(meeting.date) : null);
const isValidDate = $derived(
  date && !isNaN(date.getTime()) && date.getTime() !== 0
);
const dayOfWeek = $derived(
  isValidDate ? date.toLocaleDateString('en-US', { weekday: 'short' }) : null
);
const monthDay = $derived(
  isValidDate ? date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : null
);
const timeStr = $derived(extractTime(meeting.date));
```

**Display format:** `Wed, Nov 2 • 7:00 PM`

### Performance Considerations

1. **Mobile detection cached** - Check once on mount, not every render
2. **Derived state** - Computed values only recalculate when dependencies change
3. **Animations disabled for snapshots** - Use `onIntroEnd` to disable after first load
4. **Topic slicing** - Only render visible topics, not all

---

## SimpleMeetingList

**File:** `lib/components/SimpleMeetingList.svelte` (84 lines)
**Purpose:** Minimal meeting list without animations or fancy status

### Props API

```typescript
interface Props {
  meetings: Meeting[];        // Array of meetings (required)
  cityUrl: string;            // City URL slug (required)
  showItemCount?: boolean;    // Show agenda item count (default: false)
}
```

### Usage Example

```svelte
<script>
  import SimpleMeetingList from '$lib/components/SimpleMeetingList.svelte';

  let meetings: Meeting[] = $state([...]);
</script>

<SimpleMeetingList
  {meetings}
  cityUrl="paloaltoCA"
  showItemCount={true}
/>
```

### When to Use

**Use SimpleMeetingList when:**
- Embedded in another component
- Don't want entrance animations
- Need minimal, lightweight list
- Performance is critical

**Use MeetingCard when:**
- Primary meeting list view
- Want visual polish (animations, status indicators)
- Need topic display
- Standard city page

### Display Format

Simple, clean list:
```
📅 [Meeting Title]
    Nov 2, 2024 • 7:00 PM
    [5 agenda items]  // if showItemCount
```

---

## Footer

**File:** `lib/components/Footer.svelte` (86 lines)
**Purpose:** Site-wide footer with navigation and credits

### Props API

```typescript
// No props - fully self-contained
```

### Usage Example

```svelte
<script>
  import Footer from '$lib/components/Footer.svelte';
</script>

<div class="page-content">
  <!-- Page content -->
</div>

<Footer />
```

### Contents

1. **About link** - `/about` page
2. **GitHub link** - Source code repository (opens new tab)
3. **Tagline** - "All your code is open source and readily auditable. made with love and rizz"

### Accessibility Features

```svelte
<a
  href="https://github.com/Engagic/engagic"
  target="_blank"
  rel="noopener"                    // Security best practice
  aria-label="View source code on GitHub"  // Screen reader text
>
  <svg
    aria-hidden="true"               // Hide decorative icon
    focusable="false"                // Prevent tab focus
  >
```

**Why these attributes?**
- `rel="noopener"` - Prevents new tab from accessing `window.opener` (security)
- `aria-label` - Descriptive text for screen readers
- `aria-hidden="true"` - Icon is decorative, don't announce it
- `focusable="false"` - Don't trap keyboard focus on SVG

---

## Component Patterns

### 1. Runes-Based Props

**Modern Svelte 5 pattern:**

```typescript
interface Props {
  required: string;
  optional?: number;
}

let {
  required,
  optional = 42  // Default value
}: Props = $props();
```

**Not this (Svelte 4):**
```typescript
export let required: string;
export let optional: number = 42;
```

### 2. Derived State

**Use $derived for computed values:**

```typescript
let meeting: Meeting = $props();

// ✅ Good - recalculates when meeting changes
const slug = $derived(generateMeetingSlug(meeting));

// ❌ Bad - doesn't update when meeting changes
const slug = generateMeetingSlug(meeting);
```

### 3. Conditional Rendering

**Use {@const} for scoped variables in templates:**

```svelte
{#if meeting.topics}
  {@const maxTopics = isMobile ? 3 : 5}
  {@const displayTopics = meeting.topics.slice(0, maxTopics)}

  {#each displayTopics as topic}
    <span>{topic}</span>
  {/each}
{/if}
```

### 4. Scoped Styles

**All styles are scoped by default:**

```svelte
<style>
  .meeting-card {
    /* Only applies to this component */
  }
</style>
```

**For global styles, use `:global()`:**

```svelte
<style>
  :global(body) {
    /* Applies globally */
  }
</style>
```

### 5. Animations

**Use Svelte's built-in transitions:**

```svelte
<script>
  import { fly, fade } from 'svelte/transition';
</script>

<div in:fly={{ y: 20 }} out:fade>
  Content
</div>
```

**Common transitions:**
- `fly` - Slide + fade
- `fade` - Opacity only
- `slide` - Height/width animation
- `scale` - Scale transform

---

## Creating New Components

### Checklist

Before creating a new component, ask:

- [ ] Is this used in 3+ places?
- [ ] Is it >100 lines of code?
- [ ] Does it have a stable, clear API?
- [ ] Would extraction improve readability?

If yes to 3+, extract to component.

### Template

```svelte
<script lang="ts">
  // 1. Define Props interface
  interface Props {
    required: string;
    optional?: number;
  }

  // 2. Destructure props with defaults
  let {
    required,
    optional = 42
  }: Props = $props();

  // 3. Local state
  let localState = $state(0);

  // 4. Derived values
  let computed = $derived(localState * 2);

  // 5. Functions
  function handleClick() {
    localState++;
  }
</script>

<!-- 6. Template -->
<div class="component">
  <button onclick={handleClick}>
    {required}: {computed}
  </button>
</div>

<!-- 7. Scoped styles -->
<style>
  .component {
    padding: 1rem;
  }
</style>
```

### File Naming

- **Components:** `PascalCase.svelte` (e.g., `MeetingCard.svelte`)
- **Routes:** `+page.svelte`, `+layout.svelte`
- **Location:** `lib/components/[Name].svelte`

### Export for Use

```typescript
// lib/index.ts
export { default as MeetingCard } from './components/MeetingCard.svelte';
export { default as Footer } from './components/Footer.svelte';
```

Now other files can import:

```typescript
import { MeetingCard, Footer } from '$lib';
// or
import MeetingCard from '$lib/components/MeetingCard.svelte';
```

### Testing Components

**Manual testing workflow:**

1. Run dev server: `npm run dev`
2. Navigate to page that uses component
3. Test all prop combinations
4. Test responsive behavior (mobile/desktop)
5. Test keyboard navigation
6. Test screen reader (VoiceOver/NVDA)

**No automated component tests yet** - could add Playwright or Vitest component tests in future.

---

## Component Best Practices

### DO:

✅ Keep components small and focused
✅ Use TypeScript for prop types
✅ Use $derived for computed values
✅ Provide sensible defaults for optional props
✅ Use semantic HTML
✅ Include ARIA labels where needed
✅ Scope styles to component

### DON'T:

❌ Make "god components" (>500 lines)
❌ Put business logic in components (use load functions)
❌ Make components fetch data directly (pass as props)
❌ Use global styles unless necessary
❌ Forget to handle loading/error states
❌ Skip accessibility attributes
❌ Use `any` types

---

## Future Components

**Candidates for extraction:**

1. **TopicPill** - Topic tag display (currently inline)
2. **StatusBadge** - Meeting status indicator (currently inline)
3. **DateDisplay** - Formatted date/time (currently inline)
4. **LoadingSpinner** - Currently no loading component
5. **ErrorBoundary** - Reusable error display (currently +error.svelte)

**When to extract:** When we need them in 3+ places.

---

**Last Updated:** 2025-11-02
**See Also:** [FRONTEND.md](./FRONTEND.md) for architecture overview
