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

	function formatPopulation(num: number): string {
		if (num >= 1000000) {
			return (num / 1000000).toFixed(1) + 'M people';
		} else if (num >= 1000) {
			return Math.round(num / 1000) + 'K people';
		}
		return num.toLocaleString() + ' people';
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
					<div class="stat-description">
						{#if data.analytics.real_metrics.population_with_summaries > 0}
							{formatPopulation(data.analytics.real_metrics.population_with_summaries)}
						{:else}
							Cities with 7+ meetings with summaries
						{/if}
					</div>
				</div>

				<div class="stats-card">
					<div class="number-primary">{formatNumber(data.analytics.real_metrics.meetings_tracked)}</div>
					<div class="stat-title">Meetings Tracked</div>
					<div class="stat-description">
						{#if data.analytics.real_metrics.population_with_data > 0}
							{formatPopulation(data.analytics.real_metrics.population_with_data)}
						{:else}
							City council sessions monitored
						{/if}
					</div>
				</div>

				<div class="stats-card">
					<div class="number-primary">{formatNumber(data.analytics.real_metrics.matters_tracked)}</div>
					<div class="stat-title">Legislative Matters</div>
					<div class="stat-description">Across {formatNumber(data.analytics.real_metrics.agenda_items_processed)} agenda items</div>
				</div>

				<div class="stats-card">
					<div class="number-primary">{formatNumber(data.analytics.real_metrics.unique_item_summaries)}</div>
					<div class="stat-title">Unique Summaries</div>
					<div class="stat-description">
						{#if data.analytics.real_metrics.population_total > 0}
							{formatPopulation(data.analytics.real_metrics.population_total)} in coverage
						{:else}
							Across {formatNumber(data.analytics.real_metrics.meetings_with_items)} item-level meetings
						{/if}
					</div>
				</div>
			</div>
		</section>

		{#if data.platformMetrics}
			<section class="metrics-section">
				<h2 class="primary-heading">Civic Infrastructure</h2>
				<div class="cards-grid">
					<div class="stats-card">
						<div class="number-primary">{formatNumber(data.platformMetrics.civic_infrastructure.council_members)}</div>
						<div class="stat-title">Council Members</div>
						<div class="stat-description">Elected officials tracked</div>
					</div>

					<div class="stats-card">
						<div class="number-primary">{formatNumber(data.platformMetrics.civic_infrastructure.committees)}</div>
						<div class="stat-title">Committees</div>
						<div class="stat-description">Legislative bodies monitored</div>
					</div>

					<div class="stats-card">
						<div class="number-primary">{formatNumber(data.platformMetrics.civic_infrastructure.committee_assignments)}</div>
						<div class="stat-title">Committee Assignments</div>
						<div class="stat-description">Member-to-committee relationships</div>
					</div>

					<div class="stats-card">
						<div class="number-primary">{formatNumber(data.platformMetrics.content.matter_appearances)}</div>
						<div class="stat-title">Matter Appearances</div>
						<div class="stat-description">Items tracked across meetings</div>
					</div>
				</div>
			</section>

			<section class="metrics-section">
				<h2 class="primary-heading">Accountability Data</h2>
				<div class="cards-grid">
					<div class="stats-card highlight-card">
						<div class="number-primary">{formatNumber(data.platformMetrics.accountability.votes)}</div>
						<div class="stat-title">Votes Recorded</div>
						<div class="stat-description">Individual voting records captured</div>
					</div>

					<div class="stats-card">
						<div class="number-primary">{formatNumber(data.platformMetrics.accountability.sponsorships)}</div>
						<div class="stat-title">Sponsorships</div>
						<div class="stat-description">Legislation authorship tracked</div>
					</div>

					<div class="stats-card">
						<div class="number-primary">{formatNumber(data.platformMetrics.accountability.cities_with_votes)}</div>
						<div class="stat-title">Cities with Vote Data</div>
						<div class="stat-description">Full voting record coverage</div>
					</div>

					<div class="stats-card">
						<div class="stat-numbers-split">
							<span class="number-primary">{data.platformMetrics.processing.item_summary_rate}%</span>
						</div>
						<div class="stat-title">Item Summary Rate</div>
						<div class="stat-description">{formatNumber(data.platformMetrics.processing.summarized_items)} items processed</div>
					</div>
				</div>
			</section>
		{/if}

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
		color: var(--text-primary);
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
		color: var(--text-primary);
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
		background: var(--surface-primary);
		border: 2px solid var(--border-primary);
		border-radius: var(--radius-md);
		text-align: center;
		min-height: 180px;
		transition: all var(--transition-normal);
	}

	.stats-card:hover {
		border-color: var(--civic-blue);
		box-shadow: 0 8px 24px var(--shadow-lg);
		transform: translateY(-2px);
	}

	.stats-card.highlight-card {
		border-color: var(--civic-blue);
		background: linear-gradient(135deg, var(--surface-primary) 0%, rgba(var(--civic-blue-rgb, 59, 130, 246), 0.05) 100%);
	}

	.stats-card.highlight-card .number-primary {
		color: var(--civic-blue);
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
		color: var(--civic-blue);
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
		color: var(--text-primary);
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
			grid-template-columns: repeat(2, 1fr);
			gap: var(--space-sm);
		}

		.stats-card {
			padding: var(--space-md) var(--space-sm);
			min-height: 120px;
			gap: var(--space-xs);
		}

		.number-primary {
			font-size: 1.75rem;
		}

		.number-separator {
			font-size: 1.25rem;
		}

		.number-secondary {
			font-size: 1.25rem;
		}

		.stat-title {
			font-size: 0.85rem;
		}

		.stat-description {
			font-size: 0.75rem;
			line-height: 1.3;
		}

		.metrics-container {
			gap: var(--space-xl);
		}

		.metrics-section {
			gap: var(--space-sm);
		}
	}

	@media (max-width: 640px) {
		h1.primary-heading {
			font-size: 1.5rem;
		}

		.primary-heading {
			font-size: 1.25rem;
		}
	}
</style>
