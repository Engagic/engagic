<script lang="ts" module>
	// Module-level cache - persists across component instances and navigation
	// Cleared only on full page reload
	const MATTERS_CACHE_DURATION = 120000; // 2 minutes
	const mattersCache = new Map<string, { data: any; timestamp: number }>();
</script>

<script lang="ts">
	import { page } from '$app/stores';
	import type { Meeting } from '$lib/api/index';
	import { getCityMatters } from '$lib/api/index';
	import MeetingCard from '$lib/components/MeetingCard.svelte';
	import MatterTimeline from '$lib/components/MatterTimeline.svelte';
	import Footer from '$lib/components/Footer.svelte';
	import WatchCityModal from '$lib/components/WatchCityModal.svelte';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();


	const city_banana = $derived($page.params.city_url);
	let showPastMeetings = $state(false);
	let isInitialLoad = $state(true);
	let viewMode = $state<'meetings' | 'matters'>('meetings');
	let cityMatters = $state<any>(null);
	let mattersLoading = $state(false);
	let mattersChecked = $state(false);
	let showWatchModal = $state(false);

	// Data comes from server-side load function - reactive to navigation
	const searchResults = $derived(data.searchResults);
	const upcomingMeetings = $derived(data.upcomingMeetings || []);
	const pastMeetings = $derived(data.pastMeetings || []);

	// Reset matters state when city changes (client-side navigation)
	$effect(() => {
		// Access city_banana to create dependency
		const currentCity = city_banana;
		// Reset matters when city changes
		cityMatters = null;
		mattersChecked = false;
		viewMode = 'meetings';
	});

	// Derived: Check if city has qualifying matters (2+ appearances)
	const hasQualifyingMatters = $derived(() => {
		if (!mattersChecked) return true; // Assume matters exist until checked
		return cityMatters && cityMatters.total_count > 0;
	});

	async function loadCityMatters() {
		if (mattersLoading) return; // Already fetching - prevent concurrent requests
		if (cityMatters) return; // Already loaded in component state

		// Check cache first (2-minute expiration)
		const cached = mattersCache.get(city_banana);
		const now = Date.now();
		if (cached && (now - cached.timestamp) < MATTERS_CACHE_DURATION) {
			// Use cached data - instant load
			cityMatters = cached.data;
			mattersChecked = true;
			return;
		}

		// Fetch fresh data from API
		mattersLoading = true;
		try {
			const result = await getCityMatters(city_banana, 50, 0);
			cityMatters = result;
			mattersChecked = true;

			// Store in cache with timestamp
			mattersCache.set(city_banana, {
				data: result,
				timestamp: now
			});

			// If no qualifying matters, switch back to meetings view
			if (result.total_count === 0) {
				viewMode = 'meetings';
			}
		} catch (err) {
			console.error('Failed to load city matters:', err);
			mattersChecked = true;
		} finally {
			mattersLoading = false;
		}
	}

	async function switchToMatters() {
		viewMode = 'matters';
		await loadCityMatters();
	}

	// Snapshot: Preserve UI state and data during navigation
	export const snapshot = {
		capture: () => ({
			showPastMeetings,
			viewMode,
			scrollY: typeof window !== 'undefined' ? window.scrollY : 0
		}),
		restore: (values: {
			showPastMeetings: boolean;
			viewMode: 'meetings' | 'matters';
			scrollY: number;
		}) => {
			showPastMeetings = values.showPastMeetings;
			viewMode = values.viewMode;
			if (viewMode === 'matters') {
				loadCityMatters();
			}
			isInitialLoad = false;
			if (typeof window !== 'undefined' && typeof values.scrollY === 'number') {
				setTimeout(() => window.scrollTo(0, values.scrollY), 0);
			}
		}
	};

</script>

<svelte:head>
	<title>{searchResults && 'city_name' in searchResults ? `${searchResults.city_name}, ${searchResults.state}` : 'City'} - engagic</title>
	<meta name="description" content="Local government meetings and agendas" />
</svelte:head>

<div class="container">
	<div class="main-content">
		<a href="/" class="compact-logo" aria-label="Return to engagic homepage">
			<img src="/icon-64.png" alt="engagic" class="logo-icon" />
		</a>

	<div class="city-header">
		<a href="/" class="back-link">← Back to search</a>
		{#if searchResults && 'city_name' in searchResults}
			<div class="city-title-row">
				<h1 class="city-title">{searchResults.city_name}, {searchResults.state}</h1>
				<button class="watch-city-btn" onclick={() => showWatchModal = true}>
					Get weekly updates
				</button>
			</div>
			<div class="source-row">
				{#if searchResults.source_url && searchResults.vendor_display_name}
					<div class="source-attribution">
						<span class="attribution-text">Data sourced from</span>
						<a
							href={searchResults.source_url}
							target="_blank"
							rel="noopener noreferrer"
							class="source-link"
						>
							{searchResults.vendor_display_name}
						</a>
					</div>
				{/if}
				<button class="priority-hint" onclick={() => showWatchModal = true}>
					Watching this city will give it sync priority
				</button>
			</div>
		{/if}
	</div>

	{#if searchResults && 'city_name' in searchResults}
		<WatchCityModal
			cityName={searchResults.city_name}
			cityBanana={city_banana}
			bind:open={showWatchModal}
			onClose={() => showWatchModal = false}
		/>
	{/if}

	{#if searchResults && searchResults.success}
		{#if hasQualifyingMatters()}
			<div class="view-toggle" role="tablist" aria-label="View mode selection">
				<button
					class="toggle-btn"
					class:active={viewMode === 'meetings'}
					onclick={() => viewMode = 'meetings'}
					role="tab"
					aria-selected={viewMode === 'meetings'}
					aria-controls="content-panel"
				>
					Meetings
				</button>
				<button
					class="toggle-btn"
					class:active={viewMode === 'matters'}
					onclick={() => switchToMatters()}
					role="tab"
					aria-selected={viewMode === 'matters'}
					aria-controls="content-panel"
				>
					Matters
				</button>
			</div>
		{/if}

		{#if viewMode === 'meetings'}
			{#if searchResults.meetings && searchResults.meetings.length > 0}
				{#if upcomingMeetings.length > 0 || pastMeetings.length > 0}
					<div class="meetings-filter">
						{#if upcomingMeetings.length > 0}
							<h2 class="meetings-section-title">Upcoming Meetings</h2>
						{/if}
						{#if pastMeetings.length > 0 && upcomingMeetings.length === 0}
							<h2 class="meetings-section-title">No Upcoming Meetings</h2>
						{/if}
						{#if pastMeetings.length > 0}
							<button
								class="toggle-past-btn"
								onclick={() => showPastMeetings = !showPastMeetings}
								aria-label={showPastMeetings ? `Hide ${pastMeetings.length} past meetings` : `Show ${pastMeetings.length} past meetings`}
								aria-expanded={showPastMeetings}
							>
								{showPastMeetings ? 'Hide' : 'Show'} Past Meetings ({pastMeetings.length})
							</button>
						{/if}
					</div>

					<div class="meeting-list">
				{#each upcomingMeetings as meeting, index}
					<MeetingCard
						{meeting}
						cityUrl={city_banana}
						isPast={false}
						animationDuration={isInitialLoad ? 300 : 0}
						animationDelay={isInitialLoad ? index * 50 : 0}
						onIntroEnd={() => { if (index === upcomingMeetings.length - 1 && !showPastMeetings) isInitialLoad = false; }}
					/>
				{/each}

				{#if showPastMeetings}
					{#if pastMeetings.length > 0}
						<h3 class="past-meetings-divider">Past Meetings</h3>
					{/if}
					{#each pastMeetings as meeting, index}
						<MeetingCard
							{meeting}
							cityUrl={city_banana}
							isPast={true}
							animationDuration={isInitialLoad ? 300 : 0}
							animationDelay={isInitialLoad ? index * 50 : 0}
							onIntroEnd={() => { if (index === pastMeetings.length - 1) isInitialLoad = false; }}
						/>
					{/each}
				{/if}
					</div>
				{:else}
					<div class="no-meetings">
						<p class="empty-state-title">No meetings found</p>
						<p class="empty-state-message">This city might not have any upcoming meetings scheduled yet. Check back soon!</p>
						<div class="request-city-cta">
							<p class="cta-text">Want priority updates for this city?</p>
							<button class="cta-button" onclick={() => showWatchModal = true}>Add to your watchlist</button>
							<p class="cta-subtext">Cities with active watchers get synced more frequently.</p>
						</div>
					</div>
				{/if}
			{:else}
				<div class="no-meetings">
					<p class="empty-state-title">No meetings found</p>
					<p class="empty-state-message">{'message' in searchResults ? searchResults.message : 'We could not find any meetings for this city. Agendas are typically posted 48 hours before meetings.'}</p>
					<div class="request-city-cta">
						<p class="cta-text">Want priority updates for this city?</p>
						<button class="cta-button" onclick={() => showWatchModal = true}>Add to your watchlist</button>
						<p class="cta-subtext">Cities with active watchers get synced more frequently.</p>
					</div>
				</div>
			{/if}
		{:else if viewMode === 'matters'}
			{#if mattersLoading}
				<div class="loading-matters">
					<p>Loading matters timeline...</p>
				</div>
			{:else if cityMatters && cityMatters.matters && cityMatters.matters.length > 0}
				<div class="matters-view">
					<div class="matters-header">
						<h2 class="matters-title">Legislative Matters</h2>
						<div class="matters-stats">
							<span class="stat">{cityMatters.total_count} matters tracked</span>
						</div>
					</div>
					<div class="matters-list">
						{#each cityMatters.matters as matter}
							{@const hasMultipleAppearances = matter.appearance_count > 1}
							<a href="/matter/{matter.id}" class="matter-card-link">
								<div class="matter-card">
									<div class="matter-card-header">
										{#if matter.matter_file}
											<span class="matter-file-badge">{matter.matter_file}</span>
										{/if}
										{#if matter.matter_type}
											<span class="matter-type-label">{matter.matter_type}</span>
										{/if}
										{#if hasMultipleAppearances}
											<span class="appearances-badge">{matter.appearance_count} appearances</span>
										{/if}
									</div>
									<h3 class="matter-card-title">{matter.title}</h3>
									{#if matter.canonical_topics && matter.canonical_topics.length > 0}
										<div class="matter-card-topics">
											{#each matter.canonical_topics.slice(0, 4) as topic}
												<span class="matter-topic-tag">{topic}</span>
											{/each}
										</div>
									{/if}
									{#if matter.canonical_summary}
										<div class="matter-card-summary">
											{matter.canonical_summary.substring(0, 200)}{matter.canonical_summary.length > 200 ? '...' : ''}
										</div>
									{/if}
									{#if hasMultipleAppearances && matter.timeline}
										<div class="matter-timeline-container">
											<MatterTimeline
												matterId={matter.id}
												matterFile={matter.matter_file}
												timelineData={{
													success: true,
													matter: {
														id: matter.id,
														banana: matter.banana,
														matter_id: matter.matter_id,
														matter_file: matter.matter_file,
														matter_type: matter.matter_type,
														title: matter.title,
														canonical_summary: matter.canonical_summary,
														canonical_topics: matter.canonical_topics,
														first_seen: matter.first_seen,
														last_seen: matter.last_seen,
														appearance_count: matter.appearance_count
													},
													timeline: matter.timeline,
													appearance_count: matter.appearance_count
												}}
											/>
										</div>
									{/if}
								</div>
							</a>
						{/each}
					</div>
				</div>
			{:else}
				<div class="no-meetings">
					<p class="empty-state-title">No matters found</p>
					<p class="empty-state-message">This city doesn't have any tracked legislative matters yet.</p>
				</div>
			{/if}
		{/if}
	{/if}
	</div>

	<Footer />
</div>

<style>
	.container {
		width: var(--width-meetings);
		position: relative;
	}

	.compact-logo {
		position: absolute;
		top: 0;
		right: 1rem;
		z-index: 10;
		transition: transform 0.2s ease;
	}

	.compact-logo:hover {
		transform: scale(1.05);
	}

	.logo-icon {
		width: 48px;
		height: 48px;
		border-radius: 12px;
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
	}

	.city-header {
		margin-bottom: 2rem;
		min-height: 80px;
	}

	.back-link {
		display: inline-block;
		margin-bottom: 1rem;
		color: var(--text-muted);
		text-decoration: none;
		font-family: var(--font-body);
		font-size: var(--text-sm);
		font-weight: var(--font-medium);
		transition: color var(--transition-fast);
	}

	.back-link:hover {
		color: var(--action-coral);
	}

	.city-title-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 1rem;
		flex-wrap: wrap;
		margin-bottom: 0.75rem;
	}

	.city-title {
		font-family: var(--font-body);
		font-size: var(--text-3xl);
		color: var(--text);
		margin: 0;
		font-weight: var(--font-bold);
		letter-spacing: -0.02em;
	}

	.watch-city-btn {
		padding: 0.625rem 1.25rem;
		font-size: var(--text-sm);
		font-weight: var(--font-semibold);
		background: var(--action-coral);
		color: white;
		border: none;
		border-radius: var(--radius-md);
		cursor: pointer;
		transition: all var(--transition-fast);
		white-space: nowrap;
		font-family: var(--font-body);
	}

	.watch-city-btn:hover {
		background: var(--action-coral-hover);
		transform: translateY(-1px);
	}

	.watch-city-btn:active {
		transform: translateY(0);
	}

	.source-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 1rem;
		margin-top: 0.5rem;
		flex-wrap: wrap;
	}

	.source-attribution {
		font-family: var(--font-body);
		font-size: var(--text-xs);
		color: var(--text-muted);
		display: flex;
		align-items: center;
		gap: 0.4rem;
	}

	.attribution-text {
		opacity: 0.7;
	}

	.source-link {
		color: var(--civic-blue);
		text-decoration: none;
		font-weight: 500;
		transition: all 0.2s ease;
		border-bottom: 1px solid transparent;
	}

	.source-link:hover {
		color: var(--civic-accent);
		border-bottom-color: var(--civic-accent);
	}

	.view-toggle {
		display: flex;
		gap: var(--space-xs);
		margin-bottom: var(--space-xl);
		background: var(--surface-secondary);
		padding: 0.35rem;
		border-radius: var(--radius-lg);
		width: fit-content;
	}

	.toggle-btn {
		padding: 0.65rem 1.5rem;
		background: transparent;
		border: none;
		border-radius: var(--radius-md);
		font-family: var(--font-body);
		font-size: var(--text-sm);
		font-weight: var(--font-semibold);
		color: var(--text-muted);
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.toggle-btn:hover {
		color: var(--action-coral);
		background: rgba(249, 115, 22, 0.08);
	}

	.toggle-btn.active {
		background: var(--action-coral);
		color: white;
		box-shadow: 0 2px 8px rgba(249, 115, 22, 0.25);
	}

	.priority-hint {
		font-family: var(--font-body);
		font-size: var(--text-xs);
		color: var(--text-muted);
		background: none;
		border: none;
		cursor: pointer;
		padding: 0;
		opacity: 0.85;
		transition: all var(--transition-fast);
	}

	.priority-hint:hover {
		opacity: 1;
		color: var(--action-coral);
	}

	.loading-matters {
		text-align: center;
		padding: 4rem 2rem;
		color: var(--text-muted);
		font-family: var(--font-body);
	}

	.matters-view {
		margin-top: 1rem;
	}

	.matters-header {
		margin-bottom: var(--space-xl);
		border-bottom: 1px solid var(--border-primary);
		padding-bottom: var(--space-md);
	}

	.matters-title {
		font-family: var(--font-body);
		font-size: var(--text-xl);
		font-weight: var(--font-bold);
		color: var(--text);
		margin: 0 0 var(--space-xs) 0;
		letter-spacing: -0.01em;
	}

	.matters-stats {
		font-family: var(--font-body);
		font-size: var(--text-sm);
		color: var(--text-muted);
	}

	.matters-list {
		display: flex;
		flex-direction: column;
		gap: var(--space-lg);
	}

	.matter-card-link {
		text-decoration: none;
		color: inherit;
		display: block;
	}

	.matter-card {
		background: var(--surface-card);
		border: 1px solid var(--border-primary);
		border-left: 3px solid var(--action-coral);
		border-radius: var(--radius-lg);
		padding: var(--space-lg);
		transition: all var(--transition-normal);
		cursor: pointer;
	}

	.matter-card-link:hover .matter-card {
		border-color: var(--border-hover);
		background: var(--surface-card-hover);
		transform: translateY(-2px);
	}

	.matter-card-header {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		margin-bottom: var(--space-md);
		flex-wrap: wrap;
	}

	.matter-file-badge {
		font-family: var(--font-mono);
		font-size: var(--text-xs);
		font-weight: var(--font-bold);
		color: var(--action-coral);
		background: var(--surface-warm);
		border: 1px solid var(--action-coral);
		padding: 0.25rem 0.5rem;
		border-radius: var(--radius-sm);
	}

	.matter-type-label {
		font-family: var(--font-body);
		font-size: var(--text-xs);
		font-weight: var(--font-medium);
		color: var(--text-muted);
		background: var(--surface-secondary);
		padding: 0.25rem 0.5rem;
		border-radius: var(--radius-sm);
		text-transform: capitalize;
	}

	.appearances-badge {
		font-family: var(--font-body);
		font-size: var(--text-xs);
		font-weight: var(--font-semibold);
		color: var(--civic-green);
		background: #d1fae5;
		border: 1px solid #86efac;
		padding: 0.25rem 0.5rem;
		border-radius: var(--radius-sm);
	}

	.matter-card-title {
		font-family: var(--font-body);
		font-size: var(--text-base);
		font-weight: var(--font-semibold);
		color: var(--text);
		line-height: var(--leading-snug);
		margin: 0 0 var(--space-md) 0;
	}

	.matter-card-topics {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-xs);
		margin-bottom: var(--space-md);
	}

	.matter-topic-tag {
		font-family: var(--font-body);
		font-size: var(--text-xs);
		padding: 0.2rem 0.5rem;
		background: var(--surface-warm);
		color: var(--text-subtle);
		border-radius: var(--radius-sm);
		font-weight: var(--font-medium);
	}

	.matter-card-summary {
		font-family: var(--font-body);
		font-size: var(--text-sm);
		line-height: var(--leading-relaxed);
		color: var(--text-muted);
		margin-bottom: var(--space-md);
	}

	.matter-timeline-container {
		margin-top: 1rem;
	}

	.request-city-cta {
		margin-top: var(--space-xl);
		padding: var(--space-lg);
		background: var(--surface-warm);
		border: 1px solid var(--border-primary);
		border-radius: var(--radius-lg);
		text-align: center;
	}

	.cta-text {
		font-family: var(--font-body);
		font-size: var(--text-base);
		font-weight: var(--font-semibold);
		color: var(--text);
		margin: 0 0 var(--space-md) 0;
	}

	.cta-button {
		display: inline-block;
		padding: 0.75rem 1.5rem;
		background: var(--action-coral);
		color: white;
		border: none;
		border-radius: var(--radius-md);
		font-family: var(--font-body);
		font-size: var(--text-sm);
		font-weight: var(--font-semibold);
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.cta-button:hover {
		background: var(--action-coral-hover);
		transform: translateY(-1px);
	}

	.cta-subtext {
		font-family: var(--font-body);
		font-size: var(--text-xs);
		color: var(--text-muted);
		margin: var(--space-md) 0 0 0;
	}

	@media (max-width: 640px) {
		.container {
			width: 100%;
		}

		.compact-logo {
			right: 0.75rem;
		}

		.logo-icon {
			width: 40px;
			height: 40px;
			border-radius: 10px;
		}

		.city-title {
			font-size: 1.5rem;
		}

		.view-toggle {
			width: 100%;
			justify-content: center;
		}

		.toggle-btn {
			flex: 1;
			padding: 0.6rem 1rem;
			font-size: 0.85rem;
		}

		.matter-card {
			padding: 1rem;
		}

		.matter-card-title {
			font-size: 1rem;
		}
	}
</style>
