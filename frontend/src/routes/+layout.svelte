<script>
	import '../app.css';
	import { navigating } from '$app/stores';
	import { themeState } from '$lib/stores/theme.svelte';
	import { authState } from '$lib/stores/auth.svelte';
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

<nav class="main-nav">
	<div class="nav-container">
		<a href="/" class="logo">Engagic</a>
		<div class="nav-links">
			{#if authState.isAuthenticated}
				<a href="/dashboard" class="nav-link">Dashboard</a>
				<span class="nav-divider">|</span>
				<ThemeToggle />
			{:else}
				<a href="/login" class="nav-link">Log In</a>
				<a href="/signup" class="nav-link-primary">Sign Up</a>
				<span class="nav-divider">|</span>
				<ThemeToggle />
			{/if}
		</div>
	</div>
</nav>

<main id="main-content">
	<slot />
</main>

<style>
	.main-nav {
		background: var(--color-bg-primary);
		border-bottom: 1px solid var(--color-border);
		padding: 1rem 0;
		position: sticky;
		top: 0;
		z-index: 100;
	}

	.nav-container {
		max-width: 1200px;
		margin: 0 auto;
		padding: 0 2rem;
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.logo {
		font-size: 1.25rem;
		font-weight: bold;
		color: var(--color-primary);
		text-decoration: none;
		transition: opacity 0.2s;
	}

	.logo:hover {
		opacity: 0.8;
	}

	.nav-links {
		display: flex;
		align-items: center;
		gap: 1rem;
	}

	.nav-link {
		color: var(--color-text-secondary);
		text-decoration: none;
		font-size: 0.875rem;
		font-weight: 500;
		transition: color 0.2s;
	}

	.nav-link:hover {
		color: var(--color-primary);
	}

	.nav-link-primary {
		padding: 0.5rem 1rem;
		background: var(--color-primary);
		color: white;
		text-decoration: none;
		font-size: 0.875rem;
		font-weight: 600;
		border-radius: 6px;
		transition: all 0.2s;
	}

	.nav-link-primary:hover {
		background: var(--color-primary-hover);
		transform: translateY(-1px);
	}

	.nav-divider {
		color: var(--color-border);
	}

	@media (max-width: 640px) {
		.nav-container {
			padding: 0 1rem;
		}

		.nav-links {
			gap: 0.75rem;
		}

		.nav-link-primary {
			padding: 0.4rem 0.75rem;
		}
	}
</style>