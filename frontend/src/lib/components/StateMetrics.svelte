<script lang="ts">
	import { getStateMatters, getStateMeetings } from '$lib/api/index';
	import type { GetStateMattersResponse, GetStateMeetingsResponse, StateMatterSummary, StateMeeting } from '$lib/api/types';
	import { generateMeetingSlug } from '$lib/utils/utils';
	import { onMount } from 'svelte';

	interface Props {
		stateCode: string;
		stateName?: string;
		initialMetrics?: GetStateMattersResponse;
		initialMeetings?: GetStateMeetingsResponse;
	}

	let { stateCode, stateName, initialMetrics, initialMeetings }: Props = $props();

	let metrics = $state<GetStateMattersResponse | null>(initialMetrics || null);
	let meetings = $state<GetStateMeetingsResponse | null>(initialMeetings || null);
	let loading = $state(!initialMetrics);
	let meetingsLoading = $state(!initialMeetings);
	let error = $state('');
	let selectedTopic = $state<string | null>(null);
	let citiesExpanded = $state(false);

	onMount(async () => {
		const promises: Promise<void>[] = [];

		if (!initialMetrics) {
			promises.push(
				(async () => {
					try {
						const result = await getStateMatters(stateCode);
						metrics = result;
					} catch (err) {
						error = err instanceof Error ? err.message : 'Failed to load state metrics';
					} finally {
						loading = false;
					}
				})()
			);
		}

		if (!initialMeetings) {
			promises.push(
				(async () => {
					try {
						const result = await getStateMeetings(stateCode);
						meetings = result;
					} catch (err) {
						// Meetings are non-critical, just log
						console.error('Failed to load state meetings:', err);
					} finally {
						meetingsLoading = false;
					}
				})()
			);
		}

		await Promise.all(promises);
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
			.filter((m: StateMatterSummary) => m.last_seen)
			.sort((a: StateMatterSummary, b: StateMatterSummary) => new Date(b.last_seen).getTime() - new Date(a.last_seen).getTime())
			.slice(0, 5);
	});

	const longestTrackedMatters = $derived.by(() => {
		if (!metrics?.matters) return [];
		return metrics.matters
			.filter((m: StateMatterSummary) => m.appearance_count > 1)
			.sort((a: StateMatterSummary, b: StateMatterSummary) => b.appearance_count - a.appearance_count)
			.slice(0, 5);
	});

	const mostActiveCities = $derived.by(() => {
		if (!metrics?.matters) return [];
		const cityCounts: Record<string, { name: string; banana: string; count: number }> = {};
		metrics.matters.forEach((m: StateMatterSummary) => {
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
		metrics.matters.forEach((m: StateMatterSummary) => {
			const type = m.matter_type || 'Unknown';
			typeCounts[type] = (typeCounts[type] || 0) + 1;
		});
		return Object.entries(typeCounts)
			.sort(([, a], [, b]) => b - a)
			.slice(0, 6);
	});

	const avgAppearances = $derived.by(() => {
		if (!metrics?.matters || metrics.matters.length === 0) return 0;
		const total = metrics.matters.reduce((sum: number, m: StateMatterSummary) => sum + (m.appearance_count || 0), 0);
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

	function formatMeetingDate(dateStr: string | null): string {
		if (!dateStr) return 'TBD';
		const date = new Date(dateStr);
		const now = new Date();
		const diffDays = Math.floor((date.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));

		if (diffDays === 0) return 'Today';
		if (diffDays === 1) return 'Tomorrow';
		if (diffDays < 7 && diffDays > 0) {
			return date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
		}
		return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
	}

	function formatMeetingTime(dateStr: string | null): string {
		if (!dateStr) return '';
		const date = new Date(dateStr);
		const hours = date.getHours();
		const minutes = date.getMinutes();
		if (hours === 0 && minutes === 0) return '';
		return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
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

		<!-- Upcoming Meetings Section -->
		{#if meetings && meetings.meetings.length > 0}
			<div class="upcoming-meetings-section">
				<h4 class="section-title">Upcoming Meetings Across {stateName || metrics.state}</h4>
				<div class="meetings-list">
					{#each meetings.meetings.slice(0, 8) as meeting (meeting.id)}
						{@const meetingSlug = generateMeetingSlug(meeting)}
						<a href="/{meeting.city_banana}/{meetingSlug}" class="meeting-item">
							<div class="meeting-item-header">
								<span class="city-badge">{meeting.city_name}</span>
								<span class="meeting-date-badge">
									{formatMeetingDate(meeting.date)}
									{#if formatMeetingTime(meeting.date)}
										<span class="meeting-time">• {formatMeetingTime(meeting.date)}</span>
									{/if}
								</span>
							</div>
							<div class="meeting-item-title">{meeting.title}</div>
							<div class="meeting-item-footer">
								{#if meeting.has_items || meeting.summary}
									<span class="status-badge status-ai">AI Summary</span>
								{:else if meeting.agenda_url}
									<span class="status-badge status-agenda">Agenda</span>
								{:else if meeting.packet_url}
									<span class="status-badge status-packet">Packet</span>
								{/if}
								{#if meeting.topics && meeting.topics.length > 0}
									<div class="meeting-topics-mini">
										{#each meeting.topics.slice(0, 2) as topic}
											<span class="mini-topic">{topic}</span>
										{/each}
									</div>
								{/if}
							</div>
						</a>
					{/each}
				</div>
				{#if meetings.total > 8}
					<div class="more-meetings-note">
						and {meetings.total - 8} more upcoming meetings
					</div>
				{/if}
			</div>
		{:else if meetingsLoading}
			<div class="upcoming-meetings-section loading-section">
				<div class="loading-text">Loading upcoming meetings...</div>
			</div>
		{/if}

		<!-- Metrics Grid -->
		{#if metrics.meeting_stats}
			<div class="metrics-grid">
				<div class="metric-card">
					<div class="metric-label">Total Meetings</div>
					<div class="metric-value">{metrics.meeting_stats.total_meetings}</div>
					<div class="metric-change">tracked in database</div>
				</div>

				<div class="metric-card">
					<div class="metric-label">With Agendas</div>
					<div class="metric-value">{metrics.meeting_stats.with_agendas}</div>
					<div class="metric-change">packets available</div>
				</div>

				<div class="metric-card">
					<div class="metric-label">With Summaries</div>
					<div class="metric-value">{metrics.meeting_stats.with_summaries}</div>
					<div class="metric-change">AI analyzed</div>
				</div>

				<div class="metric-card">
					<div class="metric-label">Recurring Matters</div>
					<div class="metric-value">{metrics.total_matters}</div>
					<div class="metric-change">tracked across meetings</div>
				</div>
			</div>
		{/if}

		<!-- Cities List (Collapsible) -->
		{#if metrics.cities && metrics.cities.length > 0}
			<div class="cities-section">
				<button class="cities-header" onclick={() => citiesExpanded = !citiesExpanded}>
					<h4 class="section-title">Cities in {stateName || metrics.state} ({metrics.cities_count})</h4>
					<span class="expand-icon" class:expanded={citiesExpanded}>
						<svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
							<path d="M5 7.5L10 12.5L15 7.5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
						</svg>
					</span>
				</button>
				{#if citiesExpanded}
					<div class="cities-grid-container">
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
			</div>
		{/if}

		{#if metrics.total_matters === 0}
			<div class="no-matters-message">
				<p>No recurring legislative matters found for this state.</p>
				<p class="explanation">We only track matters that appear in multiple meetings (2+ appearances).</p>
			</div>
		{:else}

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
						<button class="clear-filter" onclick={() => selectedTopic && filterByTopic(selectedTopic)}>Clear</button>
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
								{#if matter.canonical_topics && matter.canonical_topics.length > 0}
									<div class="matter-topics">
										{#each matter.canonical_topics.slice(0, 3) as topic}
											<span class="mini-topic">{topic}</span>
										{/each}
									</div>
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

	/* Upcoming Meetings Section */
	.upcoming-meetings-section {
		margin: 2rem 0;
		padding: 1.5rem;
		background: var(--surface-secondary);
		border: 1px solid var(--border-primary);
		border-radius: 12px;
	}

	.upcoming-meetings-section.loading-section {
		text-align: center;
		padding: 2rem;
	}

	.meetings-list {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
		gap: 1rem;
		margin-top: 1rem;
	}

	.meeting-item {
		display: block;
		background: var(--surface-primary);
		border: 1px solid var(--border-primary);
		border-left: 4px solid var(--civic-blue);
		border-radius: 8px;
		padding: 1rem 1.25rem;
		text-decoration: none;
		transition: all 0.2s ease;
		cursor: pointer;
	}

	.meeting-item:hover {
		border-left-color: var(--civic-accent);
		box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
		transform: translateY(-2px);
	}

	.meeting-item-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 0.75rem;
		margin-bottom: 0.5rem;
		flex-wrap: wrap;
	}

	.city-badge {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		font-weight: 700;
		color: var(--badge-purple-text, var(--civic-blue));
		background: var(--badge-purple-bg, rgba(139, 92, 246, 0.1));
		padding: 0.25rem 0.6rem;
		border-radius: 6px;
		border: 1px solid var(--badge-purple-border, rgba(139, 92, 246, 0.3));
	}

	.meeting-date-badge {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--civic-gray);
	}

	.meeting-time {
		color: var(--civic-gray);
		opacity: 0.8;
	}

	.meeting-item-title {
		font-family: Georgia, 'Times New Roman', Times, serif;
		font-size: 0.95rem;
		line-height: 1.4;
		color: var(--text-primary);
		margin-bottom: 0.5rem;
	}

	.meeting-item-footer {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		flex-wrap: wrap;
	}

	.status-badge {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.65rem;
		font-weight: 600;
		padding: 0.2rem 0.5rem;
		border-radius: 4px;
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}

	.status-badge.status-ai {
		background: var(--badge-green-bg);
		color: var(--badge-green-text);
		border: 1px solid var(--badge-green-border);
	}

	.status-badge.status-agenda {
		background: var(--badge-yellow-bg, rgba(234, 179, 8, 0.1));
		color: var(--badge-yellow-text, #a16207);
		border: 1px solid var(--badge-yellow-border, rgba(234, 179, 8, 0.3));
	}

	.status-badge.status-packet {
		background: var(--badge-orange-bg, rgba(249, 115, 22, 0.1));
		color: var(--badge-orange-text, #c2410c);
		border: 1px solid var(--badge-orange-border, rgba(249, 115, 22, 0.3));
	}

	.meeting-topics-mini {
		display: flex;
		gap: 0.3rem;
		flex-wrap: wrap;
	}

	.more-meetings-note {
		margin-top: 1rem;
		padding-top: 1rem;
		border-top: 1px solid var(--border-primary);
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8rem;
		color: var(--civic-gray);
		text-align: center;
	}

	/* Cities Section (Collapsible) */
	.cities-section {
		margin: 2rem 0;
		background: var(--surface-secondary);
		border: 1px solid var(--border-primary);
		border-radius: 12px;
		overflow: hidden;
	}

	.cities-header {
		width: 100%;
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 1.25rem 1.5rem;
		background: transparent;
		border: none;
		cursor: pointer;
		transition: background 0.2s ease;
	}

	.cities-header:hover {
		background: var(--surface-hover);
	}

	.cities-header .section-title {
		margin: 0;
	}

	.expand-icon {
		color: var(--civic-gray);
		transition: transform 0.2s ease;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.expand-icon.expanded {
		transform: rotate(180deg);
	}

	.cities-grid-container {
		max-height: 400px;
		overflow-y: auto;
		padding: 0 1.5rem 1.5rem 1.5rem;
		border-top: 1px solid var(--border-primary);
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
		gap: 1rem;
		margin-top: 1.5rem;
	}

	.intel-panel {
		background: var(--surface-primary);
		border: 1px solid var(--border-primary);
		border-radius: 12px;
		padding: 1.25rem;
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

	@media (max-width: 768px) {
		.metrics-grid {
			grid-template-columns: repeat(2, 1fr);
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

		.upcoming-meetings-section {
			padding: 1rem;
		}

		.meetings-list {
			grid-template-columns: 1fr;
		}

		.meeting-item {
			padding: 0.875rem 1rem;
		}

		.meeting-item-header {
			flex-direction: column;
			align-items: flex-start;
			gap: 0.5rem;
		}

		.cities-header {
			padding: 1rem 1.25rem;
		}

		.cities-grid-container {
			padding: 0 1.25rem 1.25rem 1.25rem;
			max-height: 300px;
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
			padding: 1rem;
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
