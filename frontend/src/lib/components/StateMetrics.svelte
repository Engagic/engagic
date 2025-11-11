<script lang="ts">
	import { getStateMatters } from '$lib/api/index';
	import { onMount } from 'svelte';

	interface Props {
		stateCode: string;
		stateName?: string;
	}

	let { stateCode, stateName }: Props = $props();

	let metrics = $state<any>(null);
	let loading = $state(true);
	let error = $state('');
	let selectedTopic = $state<string | null>(null);

	onMount(async () => {
		try {
			const result = await getStateMatters(stateCode);
			metrics = result;
			loading = false;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load state metrics';
			loading = false;
		}
	});

	async function filterByTopic(topic: string) {
		selectedTopic = selectedTopic === topic ? null : topic;
		loading = true;
		try {
			const result = await getStateMatters(stateCode, selectedTopic || undefined);
			metrics = result;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to filter by topic';
		} finally {
			loading = false;
		}
	}

	const topTopics = $derived(() => {
		if (!metrics?.topic_distribution) return [];
		return Object.entries(metrics.topic_distribution)
			.sort(([, a], [, b]) => (b as number) - (a as number))
			.slice(0, 8);
	});

	const recentMatters = $derived(() => {
		if (!metrics?.matters) return [];
		return metrics.matters
			.filter((m: any) => m.last_seen)
			.sort((a: any, b: any) => new Date(b.last_seen).getTime() - new Date(a.last_seen).getTime())
			.slice(0, 5);
	});

	function formatDate(dateStr: string): string {
		if (!dateStr) return '';
		const date = new Date(dateStr);
		const now = new Date();
		const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));

		if (diffDays === 0) return 'Today';
		if (diffDays === 1) return 'Yesterday';
		if (diffDays < 7) return `${diffDays}d ago`;
		return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
	}
</script>

{#if loading}
	<div class="state-metrics loading">
		<div class="loading-text">Loading state-wide activity...</div>
	</div>
{:else if error}
	<div class="state-metrics error">
		<div class="error-text">{error}</div>
	</div>
{:else if metrics}
	<div class="state-metrics">
		<div class="metrics-header">
			<h3 class="metrics-title">
				{stateName || metrics.state} Legislative Activity
			</h3>
			<div class="metrics-stats">
				<div class="stat">
					<span class="stat-value">{metrics.total_matters}</span>
					<span class="stat-label">matters tracked</span>
				</div>
				<div class="stat">
					<span class="stat-value">{metrics.cities_count}</span>
					<span class="stat-label">cities</span>
				</div>
			</div>
		</div>

		{#if metrics.total_matters === 0}
			<div class="no-matters-message">
				<p>No recurring legislative matters found for this state.</p>
				<p class="explanation">We only track matters that appear in multiple meetings (2+ appearances).</p>
			</div>
		{/if}

		{#if topTopics().length > 0}
			<div class="topics-section">
				<h4 class="section-title">Hot Topics Across State</h4>
				<div class="topic-pills">
					{#each topTopics() as [topic, count]}
						<button
							class="topic-pill"
							class:selected={selectedTopic === topic}
							onclick={() => filterByTopic(topic)}
						>
							<span class="pill-label">{topic}</span>
							<span class="pill-count">{count}</span>
						</button>
					{/each}
				</div>
				{#if selectedTopic}
					<div class="filter-indicator">
						Showing {metrics.total_matters} matters about <strong>{selectedTopic}</strong>
						<button class="clear-filter" onclick={() => filterByTopic(selectedTopic)}>Clear</button>
					</div>
				{/if}
			</div>
		{/if}

		{#if recentMatters().length > 0}
			<div class="recent-section">
				<h4 class="section-title">Recent Activity</h4>
				<div class="recent-matters">
					{#each recentMatters() as matter}
						<div class="recent-matter">
							<div class="matter-header">
								<div class="matter-meta">
									{#if matter.matter_file}
										<span class="matter-badge">{matter.matter_file}</span>
									{/if}
									<span class="matter-city">{matter.city_name}</span>
									<span class="matter-date">{formatDate(matter.last_seen)}</span>
								</div>
								{#if matter.appearance_count > 1}
									<span class="appearance-badge">{matter.appearance_count}x</span>
								{/if}
							</div>
							<div class="matter-title">{matter.title}</div>
							{#if matter.canonical_topics}
								{@const topics = JSON.parse(matter.canonical_topics)}
								{#if topics.length > 0}
									<div class="matter-topics">
										{#each topics.slice(0, 3) as topic}
											<span class="mini-topic">{topic}</span>
										{/each}
									</div>
								{/if}
							{/if}
						</div>
					{/each}
				</div>
			</div>
		{/if}
	</div>
{/if}

<style>
	.state-metrics {
		background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
		border: 2px solid var(--civic-blue);
		border-radius: 16px;
		padding: 2rem;
		margin: 2rem 0;
		box-shadow: 0 4px 16px rgba(79, 70, 229, 0.15);
	}

	.state-metrics.loading,
	.state-metrics.error {
		text-align: center;
		padding: 3rem;
	}

	.loading-text,
	.error-text {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
		color: var(--civic-gray);
	}

	.error-text {
		color: var(--civic-red);
	}

	.metrics-header {
		margin-bottom: 2rem;
		border-bottom: 2px solid var(--border-primary);
		padding-bottom: 1.5rem;
	}

	.metrics-title {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.5rem;
		font-weight: 700;
		color: var(--civic-blue);
		margin: 0 0 1rem 0;
		letter-spacing: -0.5px;
	}

	.metrics-stats {
		display: flex;
		gap: 2rem;
		flex-wrap: wrap;
	}

	.stat {
		display: flex;
		align-items: baseline;
		gap: 0.5rem;
	}

	.stat-value {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 2rem;
		font-weight: 700;
		color: var(--civic-blue);
		line-height: 1;
	}

	.stat-label {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
		color: var(--civic-gray);
		font-weight: 500;
	}

	.no-matters-message {
		margin-top: 2rem;
		padding: 2rem;
		background: var(--surface-secondary);
		border: 1px solid var(--border-primary);
		border-radius: 8px;
		text-align: center;
	}

	.no-matters-message p {
		margin: 0 0 0.5rem 0;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
		color: var(--text-primary);
	}

	.no-matters-message .explanation {
		font-size: 0.8rem;
		color: var(--civic-gray);
	}

	.topics-section,
	.recent-section {
		margin-top: 2rem;
	}

	.section-title {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
		font-weight: 600;
		color: var(--civic-gray);
		text-transform: uppercase;
		letter-spacing: 0.5px;
		margin: 0 0 1rem 0;
	}

	.topic-pills {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
	}

	.topic-pill {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.5rem 1rem;
		background: white;
		border: 2px solid var(--border-primary);
		border-radius: 24px;
		cursor: pointer;
		transition: all 0.2s ease;
		font-family: 'IBM Plex Mono', monospace;
	}

	.topic-pill:hover {
		border-color: var(--civic-blue);
		transform: translateY(-2px);
		box-shadow: 0 4px 12px rgba(79, 70, 229, 0.2);
	}

	.topic-pill.selected {
		background: var(--civic-blue);
		border-color: var(--civic-blue);
	}

	.pill-label {
		font-size: 0.85rem;
		font-weight: 600;
		color: var(--text-primary);
	}

	.topic-pill.selected .pill-label {
		color: white;
	}

	.pill-count {
		font-size: 0.75rem;
		font-weight: 700;
		color: var(--civic-blue);
		background: #eff6ff;
		padding: 0.15rem 0.5rem;
		border-radius: 12px;
		min-width: 24px;
		text-align: center;
	}

	.topic-pill.selected .pill-count {
		color: var(--civic-blue);
		background: white;
	}

	.filter-indicator {
		margin-top: 1rem;
		padding: 0.75rem 1rem;
		background: #eff6ff;
		border: 1px solid #bfdbfe;
		border-radius: 8px;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
		color: var(--civic-blue);
		display: flex;
		align-items: center;
		gap: 1rem;
		flex-wrap: wrap;
	}

	.clear-filter {
		padding: 0.25rem 0.75rem;
		background: var(--civic-blue);
		color: white;
		border: none;
		border-radius: 6px;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		font-weight: 600;
		cursor: pointer;
		transition: all 0.2s ease;
	}

	.clear-filter:hover {
		background: var(--civic-accent);
	}

	.recent-matters {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.recent-matter {
		background: white;
		border: 1px solid var(--border-primary);
		border-left: 4px solid var(--civic-blue);
		border-radius: 8px;
		padding: 1rem 1.25rem;
		transition: all 0.2s ease;
	}

	.recent-matter:hover {
		border-left-color: var(--civic-accent);
		box-shadow: 0 2px 8px rgba(79, 70, 229, 0.1);
		transform: translateX(2px);
	}

	.matter-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 1rem;
		margin-bottom: 0.5rem;
		flex-wrap: wrap;
	}

	.matter-meta {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		flex-wrap: wrap;
	}

	.matter-badge {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		font-weight: 700;
		color: #1e40af;
		background: #dbeafe;
		padding: 0.25rem 0.6rem;
		border-radius: 6px;
		border: 1px solid #bfdbfe;
	}

	.matter-city {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8rem;
		font-weight: 600;
		color: var(--civic-gray);
	}

	.matter-date {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		color: var(--civic-gray);
	}

	.appearance-badge {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.7rem;
		font-weight: 700;
		color: var(--civic-green);
		background: #d1fae5;
		padding: 0.25rem 0.5rem;
		border-radius: 6px;
		border: 1px solid #86efac;
	}

	.matter-title {
		font-family: Georgia, 'Times New Roman', Times, serif;
		font-size: 0.95rem;
		line-height: 1.4;
		color: var(--text-primary);
		margin-bottom: 0.5rem;
	}

	.matter-topics {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
	}

	.mini-topic {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.65rem;
		padding: 0.2rem 0.5rem;
		background: var(--surface-secondary);
		color: var(--civic-gray);
		border-radius: 4px;
		font-weight: 500;
	}

	@media (max-width: 640px) {
		.state-metrics {
			padding: 1.5rem;
			margin: 1rem 0;
		}

		.metrics-title {
			font-size: 1.2rem;
		}

		.stat-value {
			font-size: 1.5rem;
		}

		.metrics-stats {
			gap: 1.5rem;
		}

		.topic-pill {
			padding: 0.4rem 0.8rem;
		}

		.recent-matter {
			padding: 0.75rem 1rem;
		}

		.matter-header {
			flex-direction: column;
			align-items: flex-start;
		}
	}
</style>
