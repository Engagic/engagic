<script lang="ts">
	import CityMap from '$lib/components/CityMap.svelte';
	import ThemeToggle from '$lib/components/ThemeToggle.svelte';
</script>

<svelte:head>
	<title>Coverage Map | engagic</title>
	<meta name="description" content="Explore engagic's coverage of local government meetings across the United States" />
</svelte:head>

<div class="country-page">
	<header class="page-header">
		<div class="header-left">
			<a href="/" class="back-link">
				<svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
					<path d="M12.5 15L7.5 10L12.5 5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
				</svg>
				Back
			</a>
			<h1 class="page-title">Coverage</h1>
		</div>
		<div class="header-right">
			<a href="/signup" class="request-cta">Request a City</a>
			<ThemeToggle />
		</div>
	</header>

	<div class="map-section">
		<CityMap />
	</div>

	<footer class="page-footer">
		<p class="footer-text">
			Click any highlighted city to explore its meetings.
			<a href="/about/general" class="footer-link">Learn more</a> about how engagic works.
		</p>
	</footer>
</div>

<style>
	.country-page {
		display: flex;
		flex-direction: column;
		height: 100vh;
		background: var(--bg-gradient-start);
	}

	.page-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: var(--space-md) var(--space-lg);
		background: var(--surface-primary);
		border-bottom: 1px solid var(--border-primary);
		flex-shrink: 0;
	}

	.header-left {
		display: flex;
		align-items: center;
		gap: var(--space-md);
	}

	.header-right {
		display: flex;
		align-items: center;
		gap: var(--space-md);
	}

	.back-link {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.875rem;
		color: var(--text-secondary);
		text-decoration: none;
		transition: color var(--transition-fast);
	}

	.back-link:hover {
		color: var(--civic-blue);
	}

	.page-title {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.25rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
	}

	.request-cta {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8rem;
		font-weight: 500;
		color: var(--civic-blue);
		text-decoration: none;
		padding: var(--space-xs) var(--space-sm);
		border: 1px solid var(--civic-blue);
		border-radius: var(--radius-sm);
		transition: all var(--transition-fast);
	}

	.request-cta:hover {
		background: var(--civic-blue);
		color: var(--civic-white);
	}

	.map-section {
		flex: 1;
		min-height: 0;
		padding: var(--space-md);
	}

	.page-footer {
		padding: var(--space-md) var(--space-lg);
		background: var(--surface-primary);
		border-top: 1px solid var(--border-primary);
		flex-shrink: 0;
	}

	.footer-text {
		font-family: system-ui, -apple-system, sans-serif;
		font-size: 0.875rem;
		color: var(--text-secondary);
		margin: 0;
		text-align: center;
	}

	.footer-link {
		color: var(--civic-blue);
		text-decoration: underline;
		text-underline-offset: 2px;
	}

	.footer-link:hover {
		color: var(--civic-accent);
	}

	@media (max-width: 640px) {
		.page-header {
			padding: var(--space-sm) var(--space-md);
		}

		.page-title {
			font-size: 1rem;
		}

		.request-cta {
			display: none;
		}

		.map-section {
			padding: var(--space-sm);
		}

		.page-footer {
			padding: var(--space-sm) var(--space-md);
		}

		.footer-text {
			font-size: 0.8rem;
		}
	}
</style>
