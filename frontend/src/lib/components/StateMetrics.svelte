<script lang="ts">
	import { getStateMatters } from '$lib/api/index';
	import { onMount } from 'svelte';

	interface Props {
		stateCode: string;
		stateName?: string;
		initialMetrics?: any;
	}

	let { stateCode, stateName, initialMetrics }: Props = $props();

	let metrics = $state<any>(initialMetrics || null);
	let loading = $state(!initialMetrics);
	let error = $state('');
	let selectedTopic = $state<string | null>(null);

	onMount(async () => {
		if (!initialMetrics) {
			try {
				const result = await getStateMatters(stateCode);
				metrics = result;
				loading = false;
			} catch (err) {
				error = err instanceof Error ? err.message : 'Failed to load state metrics';
				loading = false;
			}
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

	const topTopics = $derived.by(() => {
		if (!metrics?.topic_distribution) return [];
		return Object.entries(metrics.topic_distribution)
			.sort(([, a], [, b]) => (b as number) - (a as number))
			.slice(0, 8);
	});

	const recentMatters = $derived.by(() => {
		if (!metrics?.matters) return [];
		return metrics.matters
			.filter((m: any) => m.last_seen)
			.sort((a: any, b: any) => new Date(b.last_seen).getTime() - new Date(a.last_seen).getTime())
			.slice(0, 5);
	});

	const longestTrackedMatters = $derived.by(() => {
		if (!metrics?.matters) return [];
		return metrics.matters
			.filter((m: any) => m.appearance_count > 1)
			.sort((a: any, b: any) => b.appearance_count - a.appearance_count)
			.slice(0, 5);
	});

	const mostActiveCities = $derived.by(() => {
		if (!metrics?.matters) return [];
		const cityCounts: Record<string, { name: string; banana: string; count: number }> = {};
		metrics.matters.forEach((m: any) => {
			if (!cityCounts[m.city_name]) {
				cityCounts[m.city_name] = { name: m.city_name, banana: m.banana, count: 0 };
			}
			cityCounts[m.city_name].count++;
		});
		return Object.values(cityCounts)
			.sort((a, b) => b.count - a.count)
			.slice(0, 5);
	});

	const matterTypeBreakdown = $derived.by(() => {
		if (!metrics?.matters) return [];
		const typeCounts: Record<string, number> = {};
		metrics.matters.forEach((m: any) => {
			const type = m.matter_type || 'Unknown';
			typeCounts[type] = (typeCounts[type] || 0) + 1;
		});
		return Object.entries(typeCounts)
			.sort(([, a], [, b]) => b - a)
			.slice(0, 6);
	});

	const avgAppearances = $derived.by(() => {
		if (!metrics?.matters || metrics.matters.length === 0) return 0;
		const total = metrics.matters.reduce((sum: number, m: any) => sum + (m.appearance_count || 0), 0);
		return (total / metrics.matters.length).toFixed(1);
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
		<div class="dashboard-header">
			<h3 class="dashboard-title">
				{stateName || metrics.state} Legislative Intelligence
			</h3>
			<div class="dashboard-subtitle">
				State-wide matter tracking and analysis
			</div>
		</div>

		<!-- Cities List - Always show -->
		{#if metrics.cities && metrics.cities.length > 0}
			<div class="cities-section">
				<h4 class="section-title">Cities in {stateName || metrics.state} ({metrics.cities_count})</h4>
				<div class="cities-grid">
					{#each metrics.cities as city (city.banana)}
						<a href="/{city.banana}" class="city-card">
							<div class="city-name">{city.name}</div>
							<div class="city-vendor">{city.vendor}</div>
						</a>
					{/each}
				</div>
			</div>
		{/if}

		{#if metrics.total_matters === 0}
			<div class="no-matters-message">
				<p>No recurring legislative matters found for this state.</p>
				<p class="explanation">We only track matters that appear in multiple meetings (2+ appearances).</p>
			</div>
		{:else}

		<!-- Metrics Grid -->
		<div class="metrics-grid">
			<div class="metric-card">
				<div class="metric-label">Total Matters</div>
				<div class="metric-value">{metrics.total_matters}</div>
				<div class="metric-change">being tracked</div>
			</div>

			<div class="metric-card">
				<div class="metric-label">Cities Active</div>
				<div class="metric-value">{metrics.cities_count}</div>
				<div class="metric-change">with legislative activity</div>
			</div>

			<div class="metric-card">
				<div class="metric-label">Avg Appearances</div>
				<div class="metric-value">{avgAppearances}</div>
				<div class="metric-change">per matter</div>
			</div>

			<div class="metric-card">
				<div class="metric-label">Active Topics</div>
				<div class="metric-value">{Object.keys(metrics.topic_distribution || {}).length}</div>
				<div class="metric-change">categories identified</div>
			</div>
		</div>

		{#if topTopics.length > 0}
			<div class="topics-section">
				<h4 class="section-title">Hot Topics Across State</h4>
				<div class="topic-pills">
					{#each topTopics as [topic, count]}
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

		<!-- Intelligence Panels Grid -->
		<div class="intelligence-grid">
			<!-- Longest Tracked Matters -->
			{#if longestTrackedMatters.length > 0}
				<div class="intel-panel">
					<h4 class="panel-title">Longest Tracked</h4>
					<div class="intel-list">
						{#each longestTrackedMatters as matter}
							<a href="/matter/{matter.id}" class="intel-item">
								<div class="intel-item-header">
									{#if matter.matter_file}
										<span class="intel-badge">{matter.matter_file}</span>
									{/if}
									<span class="intel-appearances">{matter.appearance_count}x</span>
								</div>
								<div class="intel-title">{matter.title}</div>
								<div class="intel-meta">{matter.city_name}</div>
							</a>
						{/each}
					</div>
				</div>
			{/if}

			<!-- Most Active Cities -->
			{#if mostActiveCities.length > 0}
				<div class="intel-panel">
					<h4 class="panel-title">Most Active Cities</h4>
					<div class="city-ranking">
						{#each mostActiveCities as city, index}
							<a href="/{city.banana}" class="city-rank-item">
								<div class="rank-number">{index + 1}</div>
								<div class="rank-content">
									<div class="rank-city">{city.name}</div>
									<div class="rank-count">{city.count} matters</div>
								</div>
							</a>
						{/each}
					</div>
				</div>
			{/if}

			<!-- Matter Type Breakdown -->
			{#if matterTypeBreakdown.length > 0}
				<div class="intel-panel">
					<h4 class="panel-title">Matter Types</h4>
					<div class="type-breakdown">
						{#each matterTypeBreakdown as [type, count]}
							<div class="type-item">
								<div class="type-label">{type}</div>
								<div class="type-bar-container">
									<div class="type-bar" style="width: {(count / metrics.total_matters) * 100}%"></div>
								</div>
								<div class="type-count">{count}</div>
							</div>
						{/each}
					</div>
				</div>
			{/if}

			<!-- Recent Activity -->
			{#if recentMatters.length > 0}
				<div class="intel-panel activity-panel">
					<h4 class="panel-title">Recent Activity</h4>
					<div class="recent-matters">
						{#each recentMatters as matter}
							<a href="/matter/{matter.id}" class="recent-matter">
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
							</a>
						{/each}
					</div>
				</div>
			{/if}
		</div>

		{/if}
	</div>
{/if}

<style>
	.state-metrics {
		background: var(--surface-primary);
		border: 2px solid var(--border-primary);
		border-radius: 16px;
		padding: 2rem;
		margin: 2rem 0;
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
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

	/* Dashboard Header */
	.dashboard-header {
		margin-bottom: 2rem;
		padding-bottom: 1.5rem;
		border-bottom: 1px solid var(--border-primary);
	}

	.dashboard-title {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.75rem;
		font-weight: 700;
		color: var(--text-primary);
		margin: 0 0 0.5rem 0;
		letter-spacing: -0.5px;
	}

	.dashboard-subtitle {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8rem;
		text-transform: uppercase;
		letter-spacing: 0.5px;
		color: var(--civic-gray);
		font-weight: 500;
	}

	/* Metrics Grid (4 cards) */
	.metrics-grid {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 1.25rem;
		margin-bottom: 2rem;
	}

	.metric-card {
		background: var(--surface-primary);
		border: 1px solid var(--border-primary);
		border-radius: 12px;
		padding: 1.25rem;
		transition: all 0.2s ease;
		box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
	}

	.metric-card:hover {
		border-color: var(--civic-blue);
		box-shadow: 0 4px 12px rgba(79, 70, 229, 0.1);
		transform: translateY(-2px);
	}

	.metric-label {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.7rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--civic-gray);
		font-weight: 600;
		margin-bottom: 0.75rem;
	}

	.metric-value {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 2.5rem;
		font-weight: 700;
		color: var(--text-primary);
		margin-bottom: 0.25rem;
		line-height: 1;
	}

	.metric-change {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		color: var(--civic-gray);
	}

	/* Cities Section */
	.cities-section {
		margin: 2rem 0;
		padding: 1.5rem;
		background: var(--surface-secondary);
		border: 1px solid var(--border-primary);
		border-radius: 12px;
	}

	.cities-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
		gap: 1rem;
		margin-top: 1rem;
	}

	.city-card {
		display: block;
		padding: 1rem;
		background: var(--surface-primary);
		border: 1px solid var(--border-primary);
		border-radius: 8px;
		text-decoration: none;
		transition: all 0.2s ease;
		cursor: pointer;
	}

	.city-card:hover {
		border-color: var(--civic-blue);
		box-shadow: 0 2px 8px rgba(79, 70, 229, 0.15);
		transform: translateY(-2px);
	}

	.city-name {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
		font-weight: 600;
		color: var(--text-primary);
		margin-bottom: 0.25rem;
	}

	.city-vendor {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.7rem;
		color: var(--civic-gray);
		text-transform: uppercase;
		letter-spacing: 0.05em;
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

	.topics-section {
		margin-top: 2rem;
	}

	.section-title {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
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
		background: var(--surface-primary);
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
		color: var(--civic-white);
	}

	.pill-count {
		font-size: 0.75rem;
		font-weight: 700;
		color: var(--civic-blue);
		background: var(--surface-hover);
		padding: 0.15rem 0.5rem;
		border-radius: 12px;
		min-width: 24px;
		text-align: center;
	}

	.topic-pill.selected .pill-count {
		color: var(--civic-blue);
		background: var(--surface-primary);
	}

	.filter-indicator {
		margin-top: 1rem;
		padding: 0.75rem 1rem;
		background: var(--badge-info-bg);
		border: 1px solid var(--badge-info-border);
		border-radius: 8px;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
		color: var(--badge-info-text);
		display: flex;
		align-items: center;
		gap: 1rem;
		flex-wrap: wrap;
	}

	.clear-filter {
		padding: 0.25rem 0.75rem;
		background: var(--civic-blue);
		color: var(--civic-white);
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
		display: block;
		background: var(--surface-primary);
		border: 1px solid var(--border-primary);
		border-left: 4px solid var(--civic-blue);
		border-radius: 8px;
		padding: 1rem 1.25rem;
		transition: all 0.2s ease;
		text-decoration: none;
		cursor: pointer;
	}

	.recent-matter:hover {
		border-left-color: var(--civic-accent);
		box-shadow: 0 2px 8px var(--shadow-md);
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
		color: var(--badge-blue-text);
		background: var(--badge-blue-bg);
		padding: 0.25rem 0.6rem;
		border-radius: 6px;
		border: 1px solid var(--badge-blue-border);
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
		color: var(--badge-green-text);
		background: var(--badge-green-bg);
		padding: 0.25rem 0.5rem;
		border-radius: 6px;
		border: 1px solid var(--badge-green-border);
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

	/* Intelligence Grid */
	.intelligence-grid {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 1.5rem;
		margin-top: 2rem;
	}

	.intel-panel {
		background: var(--surface-primary);
		border: 1px solid var(--border-primary);
		border-radius: 12px;
		padding: 1.5rem;
		box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
		transition: all 0.2s ease;
	}

	.intel-panel:hover {
		box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
	}

	.activity-panel {
		grid-column: 1 / -1;
	}

	.panel-title {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
		font-weight: 600;
		color: var(--civic-gray);
		text-transform: uppercase;
		letter-spacing: 0.5px;
		margin: 0 0 1.25rem 0;
	}

	/* Intelligence List Items */
	.intel-list {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.intel-item {
		display: block;
		padding-bottom: 1rem;
		border-bottom: 1px solid var(--border-primary);
		text-decoration: none;
		cursor: pointer;
		transition: all 0.2s ease;
	}

	.intel-item:hover {
		background: var(--surface-hover);
		padding-left: 0.5rem;
		margin-left: -0.5rem;
		border-radius: 4px;
	}

	.intel-item:last-child {
		border-bottom: none;
		padding-bottom: 0;
	}

	.intel-item-header {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-bottom: 0.5rem;
	}

	.intel-badge {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.7rem;
		font-weight: 700;
		color: var(--badge-blue-text);
		background: var(--badge-blue-bg);
		padding: 0.2rem 0.5rem;
		border-radius: 4px;
		border: 1px solid var(--badge-blue-border);
	}

	.intel-appearances {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.7rem;
		font-weight: 700;
		color: var(--badge-green-text);
		background: var(--badge-green-bg);
		padding: 0.2rem 0.5rem;
		border-radius: 4px;
	}

	.intel-title {
		font-family: Georgia, 'Times New Roman', Times, serif;
		font-size: 0.9rem;
		line-height: 1.4;
		color: var(--text-primary);
		margin-bottom: 0.25rem;
	}

	.intel-meta {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		color: var(--civic-gray);
	}

	/* City Ranking */
	.city-ranking {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.city-rank-item {
		display: flex;
		align-items: center;
		gap: 1rem;
		padding: 0.75rem;
		background: var(--surface-secondary);
		border-radius: 8px;
		transition: all 0.2s ease;
		text-decoration: none;
		cursor: pointer;
	}

	.city-rank-item:hover {
		background: var(--surface-hover);
		box-shadow: 0 2px 6px var(--shadow-md);
		transform: translateY(-1px);
	}

	.rank-number {
		flex-shrink: 0;
		width: 32px;
		height: 32px;
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--civic-blue);
		color: var(--civic-white);
		font-family: 'IBM Plex Mono', monospace;
		font-weight: 700;
		font-size: 0.9rem;
		border-radius: 50%;
	}

	.rank-content {
		flex: 1;
	}

	.rank-city {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
		font-weight: 600;
		color: var(--text-primary);
	}

	.rank-count {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		color: var(--civic-gray);
	}

	/* Type Breakdown */
	.type-breakdown {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.type-item {
		display: flex;
		align-items: center;
		gap: 1rem;
	}

	.type-label {
		flex-shrink: 0;
		width: 120px;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8rem;
		font-weight: 600;
		color: var(--text-primary);
	}

	.type-bar-container {
		flex: 1;
		height: 24px;
		background: var(--surface-secondary);
		border-radius: 4px;
		overflow: hidden;
	}

	.type-bar {
		height: 100%;
		background: linear-gradient(90deg, var(--civic-blue) 0%, var(--civic-accent) 100%);
		transition: width 0.3s ease;
		border-radius: 4px;
	}

	.type-count {
		flex-shrink: 0;
		width: 40px;
		text-align: right;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
		font-weight: 700;
		color: var(--text-primary);
	}

	@media (max-width: 1024px) {
		.metrics-grid {
			grid-template-columns: repeat(2, 1fr);
		}

		.intelligence-grid {
			grid-template-columns: 1fr;
		}
	}

	@media (max-width: 640px) {
		.state-metrics {
			padding: 1.5rem;
			margin: 1rem 0;
		}

		.dashboard-title {
			font-size: 1.3rem;
		}

		.cities-section {
			padding: 1rem;
		}

		.cities-grid {
			grid-template-columns: 1fr;
		}

		.metrics-grid {
			grid-template-columns: 1fr;
			gap: 1rem;
		}

		.metric-value {
			font-size: 2rem;
		}

		.topic-pill {
			padding: 0.4rem 0.8rem;
		}

		.intel-panel {
			padding: 1.25rem;
		}

		.recent-matter {
			padding: 0.75rem 1rem;
		}

		.matter-header {
			flex-direction: column;
			align-items: flex-start;
		}

		.type-label {
			width: 80px;
			font-size: 0.7rem;
		}
	}
</style>
