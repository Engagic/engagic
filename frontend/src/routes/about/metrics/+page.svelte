<script lang="ts">
	import { getAnalytics, type AnalyticsData } from '$lib/api/index';
	import { onMount } from 'svelte';

	let analytics: AnalyticsData | null = $state(null);
	let loading = $state(true);
	let errorMessage = $state('');

	onMount(async () => {
		try {
			analytics = await getAnalytics();
		} catch (err) {
			console.error('Failed to load analytics:', err);
			errorMessage = err instanceof Error ? err.message : 'Failed to load analytics';
		} finally {
			loading = false;
		}
	});

	function formatNumber(num: number): string {
		if (num >= 1000000) {
			return (num / 1000000).toFixed(1) + 'M';
		} else if (num >= 1000) {
			return (num / 1000).toFixed(1) + 'K';
		}
		return num.toLocaleString();
	}
</script>

<svelte:head>
	<title>Impact Metrics - Engagic</title>
	<meta name="description" content="Real-time metrics on Engagic's coverage, processing, and civic engagement impact" />
</svelte:head>

<article class="metrics-content">
	{#if !loading && analytics}
		<section class="section">
			<h1 class="section-heading">Coverage Overview</h1>
			<div class="metrics-grid">
				<div class="metric-card">
					<div class="metric-value-group">
						<span class="metric-number">{formatNumber(analytics.real_metrics.frequently_updated_cities)}</span>
						<span class="metric-divider">/</span>
						<span class="metric-total">{formatNumber(analytics.real_metrics.cities_covered)}</span>
					</div>
					<div class="metric-label">Frequently Updated Cities</div>
					<div class="metric-desc">Cities with 7+ meetings with summaries</div>
				</div>

				<div class="metric-card">
					<div class="metric-number">{formatNumber(analytics.real_metrics.meetings_tracked)}</div>
					<div class="metric-label">Meetings Tracked</div>
					<div class="metric-desc">City council sessions monitored</div>
				</div>

				<div class="metric-card">
					<div class="metric-number">{formatNumber(analytics.real_metrics.matters_tracked)}</div>
					<div class="metric-label">Legislative Matters</div>
					<div class="metric-desc">Across {formatNumber(analytics.real_metrics.agenda_items_processed)} agenda items</div>
				</div>

				<div class="metric-card">
					<div class="metric-number">{formatNumber(analytics.real_metrics.unique_item_summaries)}</div>
					<div class="metric-label">Unique Summaries</div>
					<div class="metric-desc">Across {formatNumber(analytics.real_metrics.meetings_with_items)} item-level meetings</div>
				</div>
			</div>
		</section>

	{:else if loading}
		<div class="loading-state">
			<div class="loading-spinner"></div>
			<p>Loading impact metrics...</p>
		</div>
	{:else if errorMessage}
		<div class="error-state">
			<p class="error-message">{errorMessage}</p>
			<button onclick={() => window.location.reload()}>Retry</button>
		</div>
	{/if}
</article>

<style>
	.metrics-content {
		display: flex;
		flex-direction: column;
		gap: var(--space-xl);
		padding-bottom: var(--space-xl);
		color: var(--text-primary);
	}

	.section {
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
	}

	.section-heading {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 2rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
		line-height: 1.2;
	}

	h1.section-heading {
		font-size: 2.5rem;
	}

	.metrics-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
		gap: var(--space-lg);
	}

	.metric-card {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: var(--space-md);
		padding: var(--space-2xl) var(--space-xl);
		background: var(--surface-primary);
		border: 2px solid var(--border-primary);
		border-radius: var(--radius-md);
		text-align: center;
		min-height: 180px;
		transition: all var(--transition-normal);
	}

	.metric-card:hover {
		border-color: var(--civic-blue);
		box-shadow: 0 8px 24px var(--shadow-lg);
		transform: translateY(-2px);
	}

	.metric-value-group {
		display: flex;
		align-items: baseline;
		gap: 0.25rem;
	}

	.metric-number {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 3rem;
		font-weight: 600;
		color: var(--civic-blue);
		line-height: 1;
	}

	.metric-divider {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 2rem;
		color: var(--text-secondary);
	}

	.metric-total {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 2rem;
		font-weight: 500;
		color: var(--text-secondary);
	}

	.metric-label {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.1rem;
		font-weight: 600;
		color: var(--text-primary);
	}

	.metric-desc {
		font-size: 0.9rem;
		color: var(--text-secondary);
		line-height: 1.5;
	}

	.coming-soon {
		background: var(--surface-secondary);
		border: 1px dashed var(--border-primary);
		border-radius: var(--radius-md);
		padding: var(--space-2xl);
	}

	.coming-soon p {
		font-size: 1.0625rem;
		line-height: 1.7;
		color: var(--text-secondary);
		font-style: italic;
		text-align: center;
		margin: 0;
	}

	.loading-state,
	.error-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: var(--space-3xl) var(--space-xl);
		text-align: center;
	}

	.loading-spinner {
		width: 48px;
		height: 48px;
		border: 4px solid var(--border-primary);
		border-top-color: var(--civic-blue);
		border-radius: 50%;
		animation: spin 1s linear infinite;
		margin-bottom: var(--space-lg);
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	.loading-state p {
		font-family: 'IBM Plex Mono', monospace;
		color: var(--text-secondary);
		font-size: 1.1rem;
		margin: 0;
	}

	.error-message {
		font-family: 'IBM Plex Mono', monospace;
		color: var(--civic-red);
		font-size: 1.1rem;
		margin-bottom: var(--space-lg);
	}

	.error-state button {
		font-family: 'IBM Plex Mono', monospace;
		padding: var(--space-sm) var(--space-lg);
		background: var(--civic-blue);
		color: white;
		border: none;
		border-radius: var(--radius-sm);
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.error-state button:hover {
		background: var(--civic-accent);
		transform: translateY(-2px);
	}

	@media (max-width: 768px) {
		h1.section-heading {
			font-size: 2rem;
		}

		.section-heading {
			font-size: 1.5rem;
		}

		.metrics-grid {
			grid-template-columns: 1fr;
		}

		.metric-card {
			padding: var(--space-lg);
			min-height: 150px;
		}

		.metric-number {
			font-size: 2.5rem;
		}

		.metric-value-group {
			flex-wrap: wrap;
			justify-content: center;
		}
	}
</style>
