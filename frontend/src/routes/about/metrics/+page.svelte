<script lang="ts">
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

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

<article class="metrics-container">
	{#if data.analytics}
		<section class="metrics-section">
			<h1 class="primary-heading">Coverage Overview</h1>
			<div class="cards-grid">
				<div class="stats-card">
					<div class="stat-numbers-split">
						<span class="number-primary">{formatNumber(data.analytics.real_metrics.frequently_updated_cities)}</span>
						<span class="number-separator">/</span>
						<span class="number-secondary">{formatNumber(data.analytics.real_metrics.cities_covered)}</span>
					</div>
					<div class="stat-title">Frequently Updated Cities</div>
					<div class="stat-description">Cities with 7+ meetings with summaries</div>
				</div>

				<div class="stats-card">
					<div class="number-primary">{formatNumber(data.analytics.real_metrics.meetings_tracked)}</div>
					<div class="stat-title">Meetings Tracked</div>
					<div class="stat-description">City council sessions monitored</div>
				</div>

				<div class="stats-card">
					<div class="number-primary">{formatNumber(data.analytics.real_metrics.matters_tracked)}</div>
					<div class="stat-title">Legislative Matters</div>
					<div class="stat-description">Across {formatNumber(data.analytics.real_metrics.agenda_items_processed)} agenda items</div>
				</div>

				<div class="stats-card">
					<div class="number-primary">{formatNumber(data.analytics.real_metrics.unique_item_summaries)}</div>
					<div class="stat-title">Unique Summaries</div>
					<div class="stat-description">Across {formatNumber(data.analytics.real_metrics.meetings_with_items)} item-level meetings</div>
				</div>
			</div>
		</section>

	{:else}
		<div class="loading-container">Loading metrics...</div>
	{/if}
</article>

<style>
	.metrics-container {
		display: flex;
		flex-direction: column;
		gap: var(--space-3xl);
		padding-bottom: var(--space-3xl);
		color: var(--text);
	}

	.metrics-section {
		display: flex;
		flex-direction: column;
		gap: var(--space-lg);
	}

	.primary-heading {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 2rem;
		font-weight: 600;
		color: var(--text);
		margin: 0;
		line-height: 1.2;
	}

	h1.primary-heading {
		font-size: 2.5rem;
	}

	.cards-grid {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: var(--space-lg);
		max-width: 1400px;
	}

	@media (max-width: 1200px) {
		.cards-grid {
			grid-template-columns: repeat(2, 1fr);
		}
	}

	.stats-card {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: var(--space-md);
		padding: var(--space-2xl) var(--space-xl);
		background: var(--surface);
		border: 2px solid var(--border);
		border-radius: var(--radius-md);
		text-align: center;
		min-height: 180px;
		transition: all var(--transition-normal);
	}

	.stats-card:hover {
		border-color: var(--color-info);
		box-shadow: 0 8px 24px var(--shadow-md);
		transform: translateY(-2px);
	}

	.stat-numbers-split {
		display: flex;
		align-items: baseline;
		gap: 0.25rem;
	}

	.number-primary {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 3rem;
		font-weight: 600;
		color: var(--color-info);
		line-height: 1;
	}

	.number-separator {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 2rem;
		color: var(--text-secondary);
	}

	.number-secondary {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 2rem;
		font-weight: 500;
		color: var(--text-secondary);
	}

	.stat-title {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.1rem;
		font-weight: 600;
		color: var(--text);
	}

	.stat-description {
		font-size: 0.9rem;
		color: var(--text-secondary);
		line-height: 1.5;
	}

	.loading-container {
		display: flex;
		align-items: center;
		justify-content: center;
		padding: var(--space-3xl);
		font-family: 'IBM Plex Mono', monospace;
		color: var(--text-secondary);
	}

	@media (max-width: 768px) {
		.cards-grid {
			grid-template-columns: 1fr;
		}
	}

	@media (max-width: 640px) {
		h1.primary-heading {
			font-size: 2rem;
		}

		.primary-heading {
			font-size: 1.5rem;
		}

		.number-primary {
			font-size: 2.5rem;
		}
	}
</style>
