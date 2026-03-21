<script lang="ts">
	import '../app.css';
	import { afterNavigate } from '$app/navigation';
	import { navigating, page } from '$app/stores';
	import { authState } from '$lib/stores/auth.svelte';
	import { logger } from '$lib/services/logger';
	import ThemeToggle from '$lib/components/ThemeToggle.svelte';
	import Toast from '$lib/components/Toast.svelte';
	import type { Snippet } from 'svelte';

	let { children }: { children: Snippet } = $props();

	const isHomepage = $derived($page.url.pathname === '/');

	// Pages that handle their own navigation (have back-link + compact-logo)
	const selfNavPaths = $derived(
		$page.url.pathname.startsWith('/about/') ||
		$page.url.pathname === '/' ||
		$page.url.pathname === '/country'
	);

	// Determine if this is a city or meeting page for topographic background
	const isTopoPage = $derived(() => {
		const path = $page.url.pathname;
		// Exclude known non-city routes
		if (path === '/' || path === '/country' || path.startsWith('/about/') ||
			path.startsWith('/dashboard') || path.startsWith('/login') ||
			path.startsWith('/signup') || path.startsWith('/state/') ||
			path.startsWith('/matter/') || path.startsWith('/search')) {
			return false;
		}
		// Match /:city_url or /:city_url/:meeting_slug patterns
		const segments = path.split('/').filter(Boolean);
		return segments.length >= 1 && segments.length <= 2;
	});

	// Apply body class reactively
	$effect(() => {
		if (typeof document !== 'undefined') {
			document.body.classList.toggle('bg-topo', isTopoPage());
		}
	});

	// Track page views on navigation
	afterNavigate(({ from, to }) => {
		if (to?.url) {
			logger.trackPageView(to.url.pathname, from?.url?.pathname);
		}
	});
</script>

<svelte:head>
	{@html `<script>
		(function() {
			var t = localStorage.getItem('theme') || 'system';
			document.documentElement.classList.add(
				t === 'system'
					? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
					: t
			);
		})();
	</script>`}
</svelte:head>

{#if $navigating}
	<div class="navigation-loading"></div>
{/if}

<a href="#main-content" class="skip-to-main">Skip to main content</a>

{#if isHomepage}
	<nav class="main-nav">
		<div class="nav-container">
			<a href="/" class="nav-logo">engagic</a>
			<div class="nav-links">
				{#if authState.isAuthenticated}
					<a href="/dashboard" class="nav-link">Dashboard</a>
					<ThemeToggle />
				{:else}
					<a href="/login" class="nav-link">Log In</a>
					<a href="/signup" class="nav-link-primary">Sign Up</a>
					<ThemeToggle />
				{/if}
			</div>
		</div>
	</nav>
{:else if !selfNavPaths}
	<nav class="main-nav main-nav-minimal">
		<div class="nav-container">
			<a href="/" class="nav-logo">engagic</a>
			<div class="nav-links">
				{#if authState.isAuthenticated}
					<a href="/dashboard" class="nav-link">Dashboard</a>
				{/if}
				<ThemeToggle />
			</div>
		</div>
	</nav>
{/if}

<main id="main-content">
	{@render children()}
</main>

<Toast />

<style>
	.main-nav {
		background: transparent;
		border-bottom: 1px solid var(--border-primary);
		padding: 1rem 0;
		position: sticky;
		top: 0;
		z-index: 100;
		backdrop-filter: blur(12px);
		-webkit-backdrop-filter: blur(12px);
		transition: border-color var(--transition-normal);
	}

	.main-nav-minimal {
		padding: 0.5rem 0;
	}

	.nav-container {
		max-width: var(--width-global);
		margin: 0 auto;
		padding: 0 2rem;
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.nav-logo {
		font-family: var(--font-display);
		font-size: 1.4rem;
		font-weight: 400;
		color: var(--text-primary);
		text-decoration: none;
		letter-spacing: -0.01em;
		transition: color var(--transition-normal);
	}

	.nav-logo:hover {
		color: var(--civic-accent);
	}

	.nav-links {
		display: flex;
		align-items: center;
		gap: 1.5rem;
	}

	.nav-link {
		font-family: var(--font-mono);
		color: var(--text-secondary);
		text-decoration: none;
		font-size: 0.9rem;
		font-weight: 500;
		transition: color var(--transition-normal);
		padding: 0.5rem 0.75rem;
		border-radius: var(--radius-sm);
	}

	.nav-link:hover {
		color: var(--civic-blue);
		background: var(--surface-hover);
	}

	.nav-link-primary {
		font-family: var(--font-mono);
		padding: 0.6rem 1.25rem;
		background: var(--civic-blue);
		color: var(--civic-white);
		text-decoration: none;
		font-size: 0.9rem;
		font-weight: 600;
		border-radius: var(--radius-md);
		transition: all var(--transition-fast);
	}

	.nav-link-primary:hover {
		background: var(--civic-accent);
	}

	@media (max-width: 640px) {
		.nav-container {
			padding: 0 1rem;
		}

		.nav-logo {
			font-size: 1.1rem;
		}

		.nav-links {
			gap: 1rem;
		}

		.nav-link {
			font-size: 0.85rem;
			padding: 0.4rem 0.6rem;
		}

		.nav-link-primary {
			padding: 0.5rem 1rem;
			font-size: 0.85rem;
		}
	}
</style>