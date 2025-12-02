<script>
	import '../app.css';
	import { navigating, page } from '$app/stores';
	import { themeState } from '$lib/stores/theme.svelte';
	import { authState } from '$lib/stores/auth.svelte';
	import ThemeToggle from '$lib/components/ThemeToggle.svelte';

	// Only show nav on homepage
	const showNav = $derived($page.url.pathname === '/');

	// Theme is applied via:
	// 1. Inline script in svelte:head (prevents flash)
	// 2. ThemeState constructor when Svelte hydrates
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

{#if showNav}
	<nav class="main-nav">
		<div class="nav-container">
			<a href="/" class="nav-logo">Engagic</a>
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
{/if}

<main id="main-content">
	<slot />
</main>

<style>
	.main-nav {
		background: var(--surface-primary);
		border-bottom: 1px solid var(--border-primary);
		padding: 1rem 0;
		position: sticky;
		top: 0;
		z-index: 100;
		transition: background var(--transition-normal), border-color var(--transition-normal);
	}

	.nav-container {
		max-width: 1200px;
		margin: 0 auto;
		padding: 0 2rem;
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.nav-logo {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.25rem;
		font-weight: 600;
		color: var(--civic-blue);
		text-decoration: none;
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
		font-family: 'IBM Plex Mono', monospace;
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
		font-family: 'IBM Plex Mono', monospace;
		padding: 0.6rem 1.25rem;
		background: var(--civic-blue);
		color: var(--civic-white);
		text-decoration: none;
		font-size: 0.9rem;
		font-weight: 600;
		border-radius: var(--radius-md);
		transition: all var(--transition-fast);
		box-shadow: 0 2px 8px rgba(79, 70, 229, 0.2);
	}

	.nav-link-primary:hover {
		background: var(--civic-accent);
		transform: translateY(-1px);
		box-shadow: 0 4px 12px rgba(139, 92, 246, 0.3);
	}

	.nav-link-primary:active {
		transform: translateY(0);
		box-shadow: 0 1px 4px rgba(79, 70, 229, 0.2);
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