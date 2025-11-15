<script>
	import '../app.css';
	import { navigating } from '$app/stores';
	import { themeState } from '$lib/stores/theme.svelte';
	import ThemeToggle from '$lib/components/ThemeToggle.svelte';
	import { onMount } from 'svelte';

	onMount(() => {
		document.documentElement.classList.add(themeState.effectiveTheme);
	});
</script>

<svelte:head>
	{@html `<script>
		(function() {
			const theme = localStorage.getItem('theme') || 'system';
			const effectiveTheme = theme === 'system'
				? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
				: theme;
			document.documentElement.classList.add(effectiveTheme);
			document.documentElement.setAttribute('data-theme', effectiveTheme);
		})();
	</script>`}
</svelte:head>

{#if $navigating}
	<div class="navigation-loading"></div>
{/if}

<a href="#main-content" class="skip-to-main">Skip to main content</a>

<nav class="site-nav">
	<div class="nav-content">
		<a href="/" class="nav-logo">engagic</a>
		<div class="nav-links">
			<a href="/dashboard" class="nav-link">Dashboard</a>
			<a href="/about" class="nav-link">About</a>
			<ThemeToggle />
		</div>
	</div>
</nav>

<main id="main-content">
	<slot />
</main>

<style>
	.site-nav {
		position: sticky;
		top: 0;
		z-index: 100;
		background: var(--bg-primary, white);
		border-bottom: 1px solid var(--border, rgba(0, 0, 0, 0.1));
		backdrop-filter: blur(8px);
	}

	.nav-content {
		max-width: 1400px;
		margin: 0 auto;
		padding: 1rem 2rem;
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.nav-logo {
		font-size: 1.25rem;
		font-weight: 700;
		color: var(--text-primary, #1a1a1a);
		text-decoration: none;
		transition: opacity 0.2s ease;
	}

	.nav-logo:hover {
		opacity: 0.7;
	}

	.nav-links {
		display: flex;
		align-items: center;
		gap: 1.5rem;
	}

	.nav-link {
		color: var(--text-secondary, #666);
		text-decoration: none;
		font-weight: 500;
		transition: color 0.2s ease;
	}

	.nav-link:hover {
		color: var(--text-primary, #1a1a1a);
	}

	@media (max-width: 768px) {
		.nav-content {
			padding: 1rem;
		}

		.nav-links {
			gap: 1rem;
		}
	}
</style>