# Frontend Styling System

**Last Updated:** 2025-11-02
**Total Styles:** ~1,126 lines of CSS
**Framework:** Vanilla CSS (no Tailwind, no CSS-in-JS)
**Typography:** IBM Plex Mono + Georgia serif

---

## Table of Contents

1. [Overview](#overview)
2. [Design System](#design-system)
3. [CSS Architecture](#css-architecture)
4. [Typography](#typography)
5. [Color System](#color-system)
6. [Layout System](#layout-system)
7. [Accessibility](#accessibility)
8. [Animations](#animations)
9. [Responsive Design](#responsive-design)

---

## Overview

We use **vanilla CSS with CSS custom properties (variables)** for styling. No framework, no preprocessor, no CSS-in-JS. This choice is intentional:

### Why Vanilla CSS?

**Pros:**
- Zero runtime cost (just static CSS)
- No build step complexity
- Native browser features
- Smaller bundle size
- Easier to debug
- No framework lock-in

**Cons:**
- More verbose than Tailwind
- Manual class naming
- Potential for specificity issues

**We accept the verbosity trade-off for simplicity and performance.**

### CSS Organization

```
app.css                    # Global styles (1,126 lines)
├── Imports (fonts)
├── CSS custom properties
├── Reset & base styles
├── Accessibility
├── Typography
├── Layout system
├── Components
├── Utilities
└── Responsive overrides
```

**Component-scoped styles** live in `.svelte` files:

```svelte
<style>
  .meeting-card {
    /* Scoped to this component */
  }
</style>
```

---

## Design System

### Brand Colors

**CSS Custom Properties in `:root`:**

```css
:root {
  /* Primary brand colors */
  --civic-blue: #4f46e5;     /* Primary brand, links, CTAs */
  --civic-green: #10b981;    /* Success, AI summaries */
  --civic-gray: #475569;     /* Secondary text */
  --civic-dark: #0f172a;     /* Primary text */

  /* Neutrals */
  --civic-light: #f8fafc;    /* Backgrounds */
  --civic-white: #ffffff;    /* Cards, containers */
  --civic-border: #e2e8f0;   /* Borders, dividers */

  /* Semantic colors */
  --civic-red: #ef4444;      /* Errors, alerts */
  --civic-yellow: #eab308;   /* Warnings, agenda available */
  --civic-orange: #f97316;   /* Meeting packets */
  --civic-accent: #8b5cf6;   /* Focus indicators */
}
```

### Color Usage

| Color | Use Cases | Examples |
|-------|-----------|----------|
| **Blue** | Primary actions, links, branding | Search button, logo, active states |
| **Green** | Success, AI-generated content | "AI Summary" badges, borders |
| **Yellow** | Warnings, partially available | "Agenda Available" badges |
| **Orange** | Incomplete data | "Meeting Packet" badges |
| **Red** | Errors, alerts, cancellations | "Meeting cancelled" alerts |
| **Purple** | Focus indicators | Keyboard navigation outlines |
| **Gray** | Secondary text, disabled states | Hints, placeholders |
| **Dark** | Primary text | Body copy, headings |

---

## CSS Architecture

### Progressive Width System

**Content gets wider as it gets denser:**

```css
:root {
  --width-search: 600px;     /* Homepage (search bar)  */
  --width-meetings: 800px;   /* City pages (meeting list) */
  --width-detail: 1000px;    /* Meeting details (lots of content) */
}
```

**Rationale:**
- Search page: narrow focus, single input
- Meetings list: moderate width, scannable cards
- Meeting detail: wide layout, agenda items + content

**Usage:**

```css
/* Homepage */
.container {
  width: var(--width-search);
}

/* City pages */
.container {
  width: var(--width-meetings);
}

/* Meeting detail */
.container {
  width: var(--width-detail);
}
```

### CSS Reset

**Minimal reset for consistency:**

```css
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html {
  overflow-x: hidden;
  width: 100%;
}

body {
  font-family: Georgia, 'Times New Roman', Times, serif;
  background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
  color: var(--civic-dark);
  line-height: 1.7;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
```

---

## Typography

### Font Stack

**Two typefaces:**

1. **IBM Plex Mono** (monospace)
   - Headers, logos, UI elements
   - Clean, technical feel
   - 400, 500, 600 weights

2. **Georgia** (serif)
   - Body text, long-form content
   - Readable, classic
   - System font (no download)

**Rationale:**
- Mono for structure/data (dates, titles, city names)
- Serif for readability (summaries, descriptions)
- Contrast creates visual hierarchy

### Typography Scale

```css
/* Headers (IBM Plex Mono) */
h1 { font-size: 2rem; }      /* 32px */
h2 { font-size: 1.5rem; }    /* 24px */
h3 { font-size: 1.25rem; }   /* 20px */

/* Body (Georgia) */
p { font-size: 1rem; }        /* 16px */
small { font-size: 0.875rem; }  /* 14px */

/* Line heights */
body { line-height: 1.7; }    /* Generous for readability */
code { line-height: 1.4; }    /* Tighter for code */
```

### Font Loading

**Self-hosted via @fontsource:**

```css
@import '@fontsource/ibm-plex-mono/400.css';  /* Regular */
@import '@fontsource/ibm-plex-mono/500.css';  /* Medium */
@import '@fontsource/ibm-plex-mono/600.css';  /* Semibold */
```

**Why self-host?**
- No Google Fonts tracking
- Faster (served from same domain)
- Works offline (PWA)
- Privacy-friendly

---

## Color System

### Status Colors (Meeting Cards)

**Visual hierarchy via border colors:**

```css
/* AI Summary available */
.status-border-ai {
  border-left: 4px solid var(--civic-green);
}

/* Agenda available (no AI yet) */
.status-border-agenda {
  border-left: 4px solid var(--civic-yellow);
}

/* Packet available (no agenda) */
.status-border-packet {
  border-left: 4px solid var(--civic-orange);
}

/* No documents yet */
.status-border-none {
  border-left: 4px solid var(--civic-gray);
}

/* Meeting cancelled/postponed */
.has-alert {
  border-left: 4px solid var(--civic-red);
}
```

**Progression:** Gray → Orange → Yellow → Green
**Meaning:** Less data → More data → AI-enhanced

### Text Colors

```css
/* Primary content */
color: var(--civic-dark);

/* Secondary/meta content */
color: var(--civic-gray);

/* Links */
color: var(--civic-blue);

/* Errors */
color: var(--civic-red);
```

---

## Layout System

### Flexbox-First

**Primary layout tool:**

```css
.container {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
```

### Spacing Scale

**Consistent rhythm:**

```css
/* Tight spacing (within components) */
gap: 0.5rem;   /* 8px */

/* Standard spacing (between elements) */
gap: 1rem;     /* 16px */

/* Generous spacing (between sections) */
gap: 2rem;     /* 32px */

/* Large spacing (page sections) */
margin-bottom: 4rem;  /* 64px */
```

### Container Pattern

```css
.container {
  width: var(--width-search);   /* Or --width-meetings, --width-detail */
  padding: 4rem 1rem;            /* Vertical + horizontal padding */
  min-height: 100vh;             /* Full viewport height */
  display: flex;
  flex-direction: column;
}
```

---

## Accessibility

### Focus Indicators

**Keyboard navigation:**

```css
/* Hide default outline */
*:focus {
  outline: none;
}

/* Show clear focus indicator for keyboard users */
*:focus-visible {
  outline: 3px solid var(--civic-accent);
  outline-offset: 3px;
  border-radius: 2px;
}
```

**Why `:focus-visible`?**
- Only shows for keyboard navigation
- Doesn't show for mouse clicks
- Better UX than always showing outlines

### Skip to Main Content

**Screen reader + keyboard users:**

```css
.skip-to-main {
  position: absolute;
  top: -100px;              /* Hidden above viewport */
  left: 0;
  background: var(--civic-blue);
  color: white;
  padding: 0.75rem 1.5rem;
  z-index: 1000;
}

.skip-to-main:focus {
  top: 0;                   /* Visible when focused */
}
```

**HTML:**
```html
<a href="#main-content" class="skip-to-main">
  Skip to main content
</a>

<main id="main-content">
  <!-- Page content -->
</main>
```

### Reduced Motion

**Respect user preferences:**

```css
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

**Disables:**
- Entrance animations
- Transition effects
- Smooth scrolling
- Any motion-based UI

---

## Animations

### Navigation Loading Bar

```css
.navigation-loading {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: rgba(255, 255, 255, 0.9);
  z-index: 9999;
  animation: navigation-progress 1s ease-in-out;
  transform-origin: left;
}

@keyframes navigation-progress {
  0% { transform: scaleX(0); }
  50% { transform: scaleX(0.7); }
  100% { transform: scaleX(0.95); }
}
```

**Behavior:**
- Appears instantly on navigation
- Grows from 0% → 95% over 1s
- Disappears when page loads
- Controlled by SvelteKit's `$navigating` store

### Svelte Transitions

**Component-level animations:**

```svelte
<script>
  import { fly } from 'svelte/transition';
</script>

<div in:fly={{ y: 20, duration: 300 }}>
  Content slides in from below
</div>
```

**Used in:**
- MeetingCard entrance animations
- Error messages
- Modal dialogs (future)

---

## Responsive Design

### Breakpoints

**Mobile-first approach:**

```css
/* Mobile (default, <640px) */
.container {
  width: 100%;
  padding: 2rem 1rem;
}

/* Tablet (640px+) */
@media (min-width: 640px) {
  .container {
    width: var(--width-meetings);
    padding: 4rem 1rem;
  }
}

/* Desktop (1024px+) */
@media (min-width: 1024px) {
  .container {
    width: var(--width-detail);
  }
}
```

### Mobile Optimizations

**Key changes for mobile:**

1. **Narrower containers**
```css
@media (max-width: 640px) {
  .container {
    width: 100%;  /* Full width on mobile */
  }
}
```

2. **Smaller fonts**
```css
@media (max-width: 640px) {
  h1 { font-size: 1.5rem; }  /* Down from 2rem */
  .city-title { font-size: 1.5rem; }
}
```

3. **Reduced padding**
```css
@media (max-width: 640px) {
  .container {
    padding: 2rem 1rem;  /* Down from 4rem */
  }
}
```

4. **Stacked layouts**
```css
@media (max-width: 640px) {
  .meeting-card-header {
    flex-direction: column;  /* Stack on mobile */
    align-items: flex-start;
  }
}
```

5. **Fewer topics displayed**
```typescript
// In component logic
const maxTopics = isMobile ? 3 : 5;
```

---

## Component Scoped Styles

**Svelte scopes styles automatically:**

```svelte
<!-- MeetingCard.svelte -->
<style>
  .meeting-card {
    /* Only applies to .meeting-card in THIS component */
  }
</style>
```

**No name collisions across components!**

### Global Styles from Components

**Use `:global()` for global styles:**

```svelte
<style>
  :global(body) {
    /* Applies globally */
  }

  :global(.meeting-card .title) {
    /* Applies to .title anywhere in the document */
  }
</style>
```

**Use sparingly** - prefer global styles in `app.css`.

---

## Utility Classes

**Minimal utilities (we're not Tailwind):**

```css
/* Visibility */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border-width: 0;
}

/* Text utilities */
.text-center { text-align: center; }
.text-muted { color: var(--civic-gray); }

/* Spacing utilities */
.mt-1 { margin-top: 0.5rem; }
.mb-2 { margin-bottom: 1rem; }
```

**Philosophy:**
- Only create utilities when used 3+ times
- Prefer component-scoped styles
- Avoid utility bloat

---

## Styling Best Practices

### DO:

✅ Use CSS custom properties for colors/spacing
✅ Scope styles to components
✅ Use semantic class names (`.meeting-card`, not `.blue-box`)
✅ Mobile-first responsive design
✅ Include `:focus-visible` styles
✅ Respect `prefers-reduced-motion`
✅ Use flexbox for layout

### DON'T:

❌ Use inline styles (except dynamic values)
❌ Use `!important` (except for resets)
❌ Create deeply nested selectors
❌ Use IDs for styling
❌ Forget mobile styles
❌ Skip accessibility features
❌ Use pixel values (use rem for most things)

---

## Future Improvements

### Short Term
1. **Dark mode** - Add `prefers-color-scheme` media query
2. **CSS layers** - Use `@layer` for better cascade control
3. **Container queries** - Component-responsive styles

### Long Term
1. **Design tokens** - Formalize spacing/color/typography scales
2. **CSS-in-TS** - Type-safe theme tokens (if needed)
3. **CSS modules** - Scoped class names at build time (alternative to Svelte scoping)

---

**Last Updated:** 2025-11-02
**See Also:** [FRONTEND.md](./FRONTEND.md) for architecture overview
