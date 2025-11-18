# Engagic Frontend

SvelteKit static web app for civic engagement. Deployed on Cloudflare Pages.

## Stack

- **Framework:** SvelteKit (Svelte 5)
- **Styling:** Custom CSS with design tokens (no framework)
- **Typography:** IBM Plex Mono + Georgia serif
- **Hosting:** Cloudflare Pages
- **Build:** Vite

## Design System

Custom design system inspired by [cobalt.tools](https://cobalt.tools) - a beautifully crafted media downloader with excellent UI patterns. We adopted their approach to:

- **Consistent design tokens** (spacing scale, border radius, transition timing)
- **Component-scoped styles** over monolithic CSS
- **Mobile-first responsive design** with safe area insets
- **Accessibility-first** patterns (focus management, reduced motion support)
- **Clean component architecture** with TypeScript

Big thanks to the cobalt team for building such a polished reference implementation. Their code quality and attention to detail set a high bar for civic tech UX.

## Development

```bash
npm install
npm run dev
```

## Build

```bash
npm run build
```

## License

AGPL-3.0 (same as parent project)
