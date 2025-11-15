<script lang="ts">
	import { onMount } from 'svelte';
	import type { PageData } from './$types';
	import AnimatedCounter from '$lib/components/AnimatedCounter.svelte';
	import TrendIndicator from '$lib/components/TrendIndicator.svelte';
	import TimeRangeSelector, { type TimeRange } from '$lib/components/TimeRangeSelector.svelte';
	import Footer from '$lib/components/Footer.svelte';

	let { data }: { data: PageData } = $props();

	let selectedRange = $state<TimeRange>('all');
	let expandedSection = $state<string | null>(null);
	let mounted = $state(false);

	onMount(() => {
		mounted = true;
	});

	function toggleSection(section: string) {
		expandedSection = expandedSection === section ? null : section;
	}

	const heroMetrics = $derived([
		{
			id: 'cities',
			label: 'Cities Tracked',
			value: data.overview?.totals.cities || 0,
			sublabel: `across ${data.overview?.totals.states || 0} states`,
			gradient: 'from-emerald-500 to-teal-600',
			icon: '🏛️'
		},
		{
			id: 'meetings',
			label: 'Meetings Processed',
			value: data.overview?.totals.meetings || 0,
			sublabel: 'total analyzed',
			gradient: 'from-blue-500 to-indigo-600',
			icon: '📋',
			trend: data.overview?.growth.meetings_30d?.change_percent || 0
		},
		{
			id: 'items',
			label: 'Agenda Items',
			value: data.overview?.totals.items || 0,
			sublabel: `${data.overview?.totals.unique_topics || 0} unique topics`,
			gradient: 'from-violet-500 to-purple-600',
			icon: '📄'
		},
		{
			id: 'matters',
			label: 'Legislative Matters',
			value: data.overview?.totals.matters || 0,
			sublabel: `${data.overview?.totals.cross_state_matters || 0} cross-state`,
			gradient: 'from-amber-500 to-orange-600',
			icon: '⚖️'
		}
	]);

	const topTopics = $derived(
		data.topicTrends?.frequency?.slice(0, 8) || []
	);

	const topStates = $derived(
		data.geographic?.states?.slice(0, 10) || []
	);

	const trendingMatters = $derived(
		data.matterTrends?.top_matters?.slice(0, 5) || []
	);
</script>

<svelte:head>
	<title>Dashboard - Engagic Intelligence</title>
	<meta name="description" content="Comprehensive civic data intelligence dashboard" />
</svelte:head>

<div class="dashboard-container" class:mounted>
	<header class="dashboard-header">
		<div class="header-content">
			<div class="title-section">
				<h1 class="dashboard-title">Civic Data Observatory</h1>
				<p class="dashboard-subtitle">Real-time intelligence from {data.overview?.totals.cities || 0} cities across America</p>
			</div>

			<TimeRangeSelector bind:selected={selectedRange} onchange={(range) => {
				console.log('Time range changed:', range);
			}} />
		</div>
	</header>

	<section class="hero-metrics">
		{#each heroMetrics as metric, i}
			<button
				class="metric-card"
				style="--delay: {i * 0.1}s; animation-delay: {i * 0.1}s"
				onclick={() => toggleSection(metric.id)}
			>
				<div class="metric-icon">{metric.icon}</div>
				<div class="metric-content">
					<div class="metric-value">
						{#if mounted}
							<AnimatedCounter value={metric.value} />
						{:else}
							{metric.value.toLocaleString()}
						{/if}
					</div>
					<div class="metric-label">{metric.label}</div>
					<div class="metric-sublabel">{metric.sublabel}</div>
					{#if metric.trend !== undefined}
						<div class="metric-trend">
							<TrendIndicator value={metric.trend} />
						</div>
					{/if}
				</div>
				<div class="card-gradient bg-gradient-to-br {metric.gradient}"></div>
			</button>
		{/each}
	</section>

	{#if expandedSection === 'cities'}
		<section class="expanded-section" style="animation-delay: 0s">
			<div class="section-header">
				<h2>Geographic Distribution</h2>
				<button class="close-btn" onclick={() => toggleSection('cities')}>✕</button>
			</div>
			<div class="states-grid">
				{#each topStates as state}
					<div class="state-card">
						<div class="state-code">{state.state}</div>
						<div class="state-stats">
							<div class="stat">
								<span class="stat-value">{state.city_count}</span>
								<span class="stat-label">cities</span>
							</div>
							<div class="stat">
								<span class="stat-value">{state.meeting_count}</span>
								<span class="stat-label">meetings</span>
							</div>
						</div>
					</div>
				{/each}
			</div>

			<div class="vendor-section">
				<h3>Platform Distribution</h3>
				<div class="vendor-chips">
					{#each (data.geographic?.vendors || []) as vendor}
						<div class="vendor-chip">
							<span class="vendor-name">{vendor.vendor}</span>
							<span class="vendor-count">{vendor.count}</span>
						</div>
					{/each}
				</div>
			</div>
		</section>
	{/if}

	{#if expandedSection === 'meetings'}
		<section class="expanded-section" style="animation-delay: 0s">
			<div class="section-header">
				<h2>Topic Landscape</h2>
				<button class="close-btn" onclick={() => toggleSection('meetings')}>✕</button>
			</div>
			<div class="topics-grid">
				{#each topTopics as topic}
					<div class="topic-card">
						<div class="topic-name">{topic.topic}</div>
						<div class="topic-count">{topic.count.toLocaleString()} meetings</div>
						<div class="topic-bar">
							<div
								class="topic-bar-fill"
								style="width: {(topic.count / topTopics[0].count) * 100}%"
							></div>
						</div>
					</div>
				{/each}
			</div>

			{#if data.topicTrends?.trending && data.topicTrends.trending.length > 0}
				<div class="trending-section">
					<h3>Trending Topics (Last 30 Days)</h3>
					<div class="trending-list">
						{#each data.topicTrends.trending.slice(0, 5) as trend}
							<div class="trending-item">
								<span class="trending-name">{trend.topic}</span>
								<span class="trending-change">
									<TrendIndicator value={trend.change_percent} />
								</span>
							</div>
						{/each}
					</div>
				</div>
			{/if}
		</section>
	{/if}

	{#if expandedSection === 'matters'}
		<section class="expanded-section" style="animation-delay: 0s">
			<div class="section-header">
				<h2>Legislative Pulse</h2>
				<button class="close-btn" onclick={() => toggleSection('matters')}>✕</button>
			</div>
			<div class="matters-list">
				{#each trendingMatters as matter, i}
					<div class="matter-card" style="animation-delay: {i * 0.05}s">
						<div class="matter-rank">#{i + 1}</div>
						<div class="matter-content">
							<div class="matter-title">{matter.title}</div>
							<div class="matter-meta">
								<span class="matter-stat">{matter.appearance_count} appearances</span>
								{#if matter.state_count > 1}
									<span class="matter-badge cross-state">{matter.state_count} states</span>
								{/if}
							</div>
						</div>
					</div>
				{/each}
			</div>

			{#if data.matterTrends?.cross_state && data.matterTrends.cross_state.length > 0}
				<div class="cross-state-section">
					<h3>Cross-State Matters</h3>
					<p class="section-desc">Legislative issues appearing in multiple states</p>
					<div class="cross-state-list">
						{#each data.matterTrends.cross_state.slice(0, 3) as matter}
							<div class="cross-state-card">
								<div class="cross-state-title">{matter.title}</div>
								<div class="cross-state-stats">
									<span>{matter.state_count} states</span>
									<span>{matter.city_count} cities</span>
									<span>{matter.meeting_count} meetings</span>
								</div>
							</div>
						{/each}
					</div>
				</div>
			{/if}
		</section>
	{/if}

	{#if expandedSection === 'items'}
		<section class="expanded-section" style="animation-delay: 0s">
			<div class="section-header">
				<h2>System Health</h2>
				<button class="close-btn" onclick={() => toggleSection('items')}>✕</button>
			</div>
			<div class="health-grid">
				<div class="health-card">
					<div class="health-label">Queue Depth</div>
					<div class="health-value">{data.overview?.processing.queue_depth || 0}</div>
					<div class="health-sublabel">pending jobs</div>
				</div>
				<div class="health-card">
					<div class="health-label">Success Rate</div>
					<div class="health-value">{data.overview?.processing.success_rate || 0}%</div>
					<div class="health-sublabel">completed successfully</div>
				</div>
				<div class="health-card">
					<div class="health-label">Total Processed</div>
					<div class="health-value">{(data.overview?.processing.total_processed || 0).toLocaleString()}</div>
					<div class="health-sublabel">all time</div>
				</div>
				<div class="health-card">
					<div class="health-label">Cache Hits</div>
					<div class="health-value">{(data.processing?.cache.total_hits || 0).toLocaleString()}</div>
					<div class="health-sublabel">requests served from cache</div>
				</div>
			</div>

			{#if data.processing?.vendor_success && data.processing.vendor_success.length > 0}
				<div class="vendor-performance">
					<h3>Vendor Performance</h3>
					<div class="vendor-bars">
						{#each data.processing.vendor_success as vendor}
							<div class="vendor-bar-item">
								<div class="vendor-bar-label">{vendor.vendor}</div>
								<div class="vendor-bar-container">
									<div
										class="vendor-bar-fill"
										style="width: {vendor.success_rate}%"
									></div>
									<span class="vendor-bar-text">{vendor.success_rate}%</span>
								</div>
							</div>
						{/each}
					</div>
				</div>
			{/if}
		</section>
	{/if}

	{#if data.funding && data.funding.total_funding_meetings > 0}
		<section class="funding-banner">
			<div class="funding-content">
				<div class="funding-icon">💰</div>
				<div class="funding-text">
					<div class="funding-title">Funding Insights</div>
					<div class="funding-desc">
						Tracking budget discussions across {data.funding.total_funding_meetings} meetings
					</div>
				</div>
				<button class="funding-cta">Explore Funding Data →</button>
			</div>
		</section>
	{/if}

	<Footer />
</div>

<style>
	@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

	:global(:root) {
		--green: #10b981;
		--red: #ef4444;
		--border: rgba(0, 0, 0, 0.1);
		--bg-secondary: rgba(0, 0, 0, 0.02);
		--bg-tertiary: rgba(0, 0, 0, 0.05);
		--bg-primary: white;
		--text-primary: #1a1a1a;
		--text-secondary: #666;
	}

	:global(html.dark) {
		--border: rgba(255, 255, 255, 0.1);
		--bg-secondary: rgba(255, 255, 255, 0.05);
		--bg-tertiary: rgba(255, 255, 255, 0.08);
		--bg-primary: #1a1a1a;
		--text-primary: #ffffff;
		--text-secondary: #a0a0a0;
	}

	.dashboard-container {
		min-height: 100vh;
		background: linear-gradient(135deg, #f5f7fa 0%, #e8eef5 100%);
		padding: 2rem;
		font-family: 'DM Sans', sans-serif;
		opacity: 0;
		animation: fadeIn 0.6s ease forwards;
	}

	:global(html.dark) .dashboard-container {
		background: linear-gradient(135deg, #0a0a0a 0%, #1a1a1a 100%);
	}

	@keyframes fadeIn {
		to {
			opacity: 1;
		}
	}

	.dashboard-header {
		max-width: 1400px;
		margin: 0 auto 3rem;
	}

	.header-content {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 2rem;
		flex-wrap: wrap;
	}

	.title-section {
		flex: 1;
		min-width: 300px;
	}

	.dashboard-title {
		font-size: 3.5rem;
		font-weight: 700;
		margin: 0;
		background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
		-webkit-background-clip: text;
		-webkit-text-fill-color: transparent;
		background-clip: text;
		letter-spacing: -0.02em;
		line-height: 1.1;
	}

	.dashboard-subtitle {
		font-size: 1.125rem;
		color: var(--text-secondary);
		margin: 0.75rem 0 0 0;
		font-weight: 500;
	}

	.hero-metrics {
		max-width: 1400px;
		margin: 0 auto 3rem;
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
		gap: 1.5rem;
	}

	.metric-card {
		position: relative;
		background: white;
		border-radius: 1.5rem;
		padding: 2rem;
		overflow: hidden;
		border: none;
		cursor: pointer;
		text-align: left;
		box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
		transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
		opacity: 0;
		transform: translateY(20px);
		animation: slideUp 0.6s ease forwards;
	}

	:global(html.dark) .metric-card {
		background: rgba(255, 255, 255, 0.05);
		box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
	}

	@keyframes slideUp {
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	.metric-card:hover {
		transform: translateY(-8px) scale(1.02);
		box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
	}

	.metric-icon {
		font-size: 3rem;
		margin-bottom: 1rem;
		filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.1));
	}

	.metric-content {
		position: relative;
		z-index: 1;
	}

	.metric-value {
		font-size: 3.5rem;
		font-weight: 700;
		font-family: 'IBM Plex Mono', monospace;
		color: var(--text-primary);
		line-height: 1;
		margin-bottom: 0.5rem;
	}

	.metric-label {
		font-size: 1rem;
		font-weight: 600;
		color: var(--text-primary);
		margin-bottom: 0.25rem;
	}

	.metric-sublabel {
		font-size: 0.875rem;
		color: var(--text-secondary);
	}

	.metric-trend {
		margin-top: 0.75rem;
	}

	.card-gradient {
		position: absolute;
		top: 0;
		right: 0;
		width: 100px;
		height: 100px;
		opacity: 0.1;
		border-radius: 50%;
		filter: blur(40px);
		pointer-events: none;
	}

	.bg-gradient-to-br {
		background-image: linear-gradient(to bottom right, var(--tw-gradient-stops));
	}

	.from-emerald-500 {
		--tw-gradient-from: #10b981;
		--tw-gradient-stops: var(--tw-gradient-from), var(--tw-gradient-to, rgba(16, 185, 129, 0));
	}

	.to-teal-600 {
		--tw-gradient-to: #0d9488;
	}

	.from-blue-500 {
		--tw-gradient-from: #3b82f6;
		--tw-gradient-stops: var(--tw-gradient-from), var(--tw-gradient-to, rgba(59, 130, 246, 0));
	}

	.to-indigo-600 {
		--tw-gradient-to: #4f46e5;
	}

	.from-violet-500 {
		--tw-gradient-from: #8b5cf6;
		--tw-gradient-stops: var(--tw-gradient-from), var(--tw-gradient-to, rgba(139, 92, 246, 0));
	}

	.to-purple-600 {
		--tw-gradient-to: #9333ea;
	}

	.from-amber-500 {
		--tw-gradient-from: #f59e0b;
		--tw-gradient-stops: var(--tw-gradient-from), var(--tw-gradient-to, rgba(245, 158, 11, 0));
	}

	.to-orange-600 {
		--tw-gradient-to: #ea580c;
	}

	.expanded-section {
		max-width: 1400px;
		margin: 0 auto 3rem;
		background: white;
		border-radius: 1.5rem;
		padding: 2.5rem;
		box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
		animation: expandIn 0.4s cubic-bezier(0.4, 0, 0.2, 1) forwards;
	}

	:global(html.dark) .expanded-section {
		background: rgba(255, 255, 255, 0.05);
	}

	@keyframes expandIn {
		from {
			opacity: 0;
			transform: scale(0.95);
		}
		to {
			opacity: 1;
			transform: scale(1);
		}
	}

	.section-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 2rem;
		padding-bottom: 1rem;
		border-bottom: 2px solid var(--border);
	}

	.section-header h2 {
		font-size: 2rem;
		font-weight: 700;
		margin: 0;
		color: var(--text-primary);
	}

	.close-btn {
		background: var(--bg-secondary);
		border: none;
		border-radius: 0.5rem;
		width: 2.5rem;
		height: 2.5rem;
		display: flex;
		align-items: center;
		justify-content: center;
		cursor: pointer;
		font-size: 1.25rem;
		color: var(--text-secondary);
		transition: all 0.2s ease;
	}

	.close-btn:hover {
		background: var(--bg-tertiary);
		color: var(--text-primary);
		transform: rotate(90deg);
	}

	.states-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
		gap: 1rem;
		margin-bottom: 2rem;
	}

	.state-card {
		background: var(--bg-secondary);
		border-radius: 1rem;
		padding: 1.5rem;
		border: 1px solid var(--border);
		transition: all 0.2s ease;
	}

	.state-card:hover {
		background: var(--bg-tertiary);
		transform: translateY(-2px);
	}

	.state-code {
		font-size: 1.5rem;
		font-weight: 700;
		font-family: 'IBM Plex Mono', monospace;
		color: var(--text-primary);
		margin-bottom: 0.75rem;
	}

	.state-stats {
		display: flex;
		gap: 1.5rem;
	}

	.stat {
		display: flex;
		flex-direction: column;
	}

	.stat-value {
		font-size: 1.25rem;
		font-weight: 600;
		font-family: 'IBM Plex Mono', monospace;
		color: var(--text-primary);
	}

	.stat-label {
		font-size: 0.75rem;
		color: var(--text-secondary);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.vendor-section {
		margin-top: 2rem;
	}

	.vendor-section h3 {
		font-size: 1.25rem;
		font-weight: 600;
		margin-bottom: 1rem;
		color: var(--text-primary);
	}

	.vendor-chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
	}

	.vendor-chip {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
		color: white;
		padding: 0.5rem 1rem;
		border-radius: 2rem;
		font-size: 0.875rem;
		font-weight: 500;
	}

	.vendor-name {
		text-transform: capitalize;
	}

	.vendor-count {
		background: rgba(255, 255, 255, 0.2);
		padding: 0.125rem 0.5rem;
		border-radius: 1rem;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
	}

	.topics-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
		gap: 1rem;
		margin-bottom: 2rem;
	}

	.topic-card {
		background: var(--bg-secondary);
		border-radius: 1rem;
		padding: 1.25rem;
		border: 1px solid var(--border);
	}

	.topic-name {
		font-size: 1rem;
		font-weight: 600;
		color: var(--text-primary);
		margin-bottom: 0.5rem;
	}

	.topic-count {
		font-size: 0.875rem;
		color: var(--text-secondary);
		margin-bottom: 0.75rem;
	}

	.topic-bar {
		height: 6px;
		background: var(--bg-tertiary);
		border-radius: 3px;
		overflow: hidden;
	}

	.topic-bar-fill {
		height: 100%;
		background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
		border-radius: 3px;
		transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1);
	}

	.trending-section {
		margin-top: 2rem;
		padding-top: 2rem;
		border-top: 2px solid var(--border);
	}

	.trending-section h3 {
		font-size: 1.25rem;
		font-weight: 600;
		margin-bottom: 1rem;
		color: var(--text-primary);
	}

	.trending-list {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.trending-item {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 0.75rem 1rem;
		background: var(--bg-secondary);
		border-radius: 0.5rem;
		border: 1px solid var(--border);
	}

	.trending-name {
		font-weight: 500;
		color: var(--text-primary);
	}

	.matters-list {
		display: flex;
		flex-direction: column;
		gap: 1rem;
		margin-bottom: 2rem;
	}

	.matter-card {
		display: flex;
		gap: 1rem;
		padding: 1.5rem;
		background: var(--bg-secondary);
		border-radius: 1rem;
		border: 1px solid var(--border);
		transition: all 0.2s ease;
		opacity: 0;
		animation: slideUp 0.4s ease forwards;
	}

	.matter-card:hover {
		background: var(--bg-tertiary);
		transform: translateX(4px);
	}

	.matter-rank {
		font-size: 1.5rem;
		font-weight: 700;
		font-family: 'IBM Plex Mono', monospace;
		color: var(--text-secondary);
		min-width: 3rem;
	}

	.matter-content {
		flex: 1;
	}

	.matter-title {
		font-size: 1rem;
		font-weight: 600;
		color: var(--text-primary);
		margin-bottom: 0.5rem;
		line-height: 1.4;
	}

	.matter-meta {
		display: flex;
		gap: 1rem;
		align-items: center;
	}

	.matter-stat {
		font-size: 0.875rem;
		color: var(--text-secondary);
		font-family: 'IBM Plex Mono', monospace;
	}

	.matter-badge {
		padding: 0.25rem 0.75rem;
		border-radius: 1rem;
		font-size: 0.75rem;
		font-weight: 600;
		background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
		color: white;
	}

	.cross-state-section {
		margin-top: 2rem;
		padding-top: 2rem;
		border-top: 2px solid var(--border);
	}

	.cross-state-section h3 {
		font-size: 1.25rem;
		font-weight: 600;
		margin-bottom: 0.5rem;
		color: var(--text-primary);
	}

	.section-desc {
		font-size: 0.875rem;
		color: var(--text-secondary);
		margin-bottom: 1rem;
	}

	.cross-state-list {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.cross-state-card {
		padding: 1.25rem;
		background: var(--bg-secondary);
		border-radius: 1rem;
		border: 1px solid var(--border);
	}

	.cross-state-title {
		font-weight: 600;
		color: var(--text-primary);
		margin-bottom: 0.75rem;
	}

	.cross-state-stats {
		display: flex;
		gap: 1.5rem;
		font-size: 0.875rem;
		color: var(--text-secondary);
		font-family: 'IBM Plex Mono', monospace;
	}

	.health-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
		gap: 1.5rem;
		margin-bottom: 2rem;
	}

	.health-card {
		background: var(--bg-secondary);
		border-radius: 1rem;
		padding: 1.5rem;
		text-align: center;
		border: 1px solid var(--border);
	}

	.health-label {
		font-size: 0.875rem;
		color: var(--text-secondary);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin-bottom: 0.5rem;
	}

	.health-value {
		font-size: 2.5rem;
		font-weight: 700;
		font-family: 'IBM Plex Mono', monospace;
		color: var(--text-primary);
		margin-bottom: 0.25rem;
	}

	.health-sublabel {
		font-size: 0.75rem;
		color: var(--text-secondary);
	}

	.vendor-performance {
		margin-top: 2rem;
		padding-top: 2rem;
		border-top: 2px solid var(--border);
	}

	.vendor-performance h3 {
		font-size: 1.25rem;
		font-weight: 600;
		margin-bottom: 1rem;
		color: var(--text-primary);
	}

	.vendor-bars {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.vendor-bar-item {
		display: flex;
		align-items: center;
		gap: 1rem;
	}

	.vendor-bar-label {
		min-width: 120px;
		font-size: 0.875rem;
		font-weight: 500;
		color: var(--text-primary);
		text-transform: capitalize;
	}

	.vendor-bar-container {
		flex: 1;
		height: 2rem;
		background: var(--bg-secondary);
		border-radius: 1rem;
		overflow: hidden;
		position: relative;
		border: 1px solid var(--border);
	}

	.vendor-bar-fill {
		height: 100%;
		background: linear-gradient(90deg, #10b981 0%, #059669 100%);
		transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1);
	}

	.vendor-bar-text {
		position: absolute;
		right: 0.75rem;
		top: 50%;
		transform: translateY(-50%);
		font-size: 0.875rem;
		font-weight: 600;
		font-family: 'IBM Plex Mono', monospace;
		color: var(--text-primary);
	}

	.funding-banner {
		max-width: 1400px;
		margin: 0 auto 3rem;
		background: linear-gradient(135deg, #f59e0b 0%, #ea580c 100%);
		border-radius: 1.5rem;
		padding: 2rem;
		box-shadow: 0 10px 15px -3px rgba(245, 158, 11, 0.3);
	}

	.funding-content {
		display: flex;
		align-items: center;
		gap: 1.5rem;
	}

	.funding-icon {
		font-size: 3rem;
		filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.2));
	}

	.funding-text {
		flex: 1;
	}

	.funding-title {
		font-size: 1.5rem;
		font-weight: 700;
		color: white;
		margin-bottom: 0.25rem;
	}

	.funding-desc {
		font-size: 1rem;
		color: rgba(255, 255, 255, 0.9);
	}

	.funding-cta {
		background: white;
		color: #ea580c;
		border: none;
		padding: 0.75rem 1.5rem;
		border-radius: 0.75rem;
		font-weight: 600;
		cursor: pointer;
		transition: all 0.2s ease;
		white-space: nowrap;
	}

	.funding-cta:hover {
		transform: translateY(-2px);
		box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
	}

	@media (max-width: 768px) {
		.dashboard-container {
			padding: 1rem;
		}

		.dashboard-title {
			font-size: 2rem;
		}

		.dashboard-subtitle {
			font-size: 1rem;
		}

		.metric-value {
			font-size: 2.5rem;
		}

		.funding-content {
			flex-direction: column;
			text-align: center;
		}

		.funding-cta {
			width: 100%;
		}
	}
</style>
