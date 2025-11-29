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
	let cityMatters = $state<any>(null);
	let mattersLoading = $state(false);
	let mattersChecked = $state(false);
	let showWatchModal = $state(false);
	let showAllMatters = $state(false);

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
	});

	// Auto-load matters on mount (for preview section)
	$effect(() => {
		if (!mattersChecked && city_banana) {
			loadCityMatters();
		}
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
		} catch (err) {
			console.error('Failed to load city matters:', err);
			mattersChecked = true;
		} finally {
			mattersLoading = false;
		}
	}

	// Derived: preview matters (first 4) vs all
	const previewMatters = $derived(
		cityMatters?.matters?.slice(0, showAllMatters ? undefined : 4) || []
	);
	const hasMoreMatters = $derived(
		cityMatters?.matters?.length > 4
	);

	// Snapshot: Preserve UI state and data during navigation
	export const snapshot = {
		capture: () => ({
			showPastMeetings,
			showAllMatters,
			scrollY: typeof window !== 'undefined' ? window.scrollY : 0
		}),
		restore: (values: {
			showPastMeetings: boolean;
			showAllMatters: boolean;
			scrollY: number;
		}) => {
			showPastMeetings = values.showPastMeetings;
			showAllMatters = values.showAllMatters ?? false;
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
				<div class="city-actions">
					<button class="watch-city-btn" onclick={() => showWatchModal = true}>
						Get weekly updates
					</button>
					<button class="priority-hint" onclick={() => showWatchModal = true}>
						Watching this city will give it sync priority
					</button>
				</div>
			</div>
			{#if searchResults.source_url && searchResults.vendor_display_name}
				<div class="source-row">
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
				</div>
			{/if}
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
		<!-- Meetings Section -->
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

		<!-- Active Matters Section (always visible) -->
		{#if previewMatters.length > 0}
			<section class="matters-section">
				<div class="matters-section-header">
					<div class="matters-section-title-row">
						<h2 class="matters-section-title">Active Matters</h2>
						<span class="matters-count">{cityMatters?.total_count || previewMatters.length} tracked</span>
					</div>
					<p class="matters-section-subtitle">Legislative items moving through this city's government</p>
				</div>

				<div class="matters-list">
					{#each previewMatters as matter}
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
								{#if hasMultipleAppearances && matter.timeline}
									<div class="matter-timeline-container">
										<MatterTimeline
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

				{#if hasMoreMatters && !showAllMatters}
					<button class="show-more-matters" onclick={() => showAllMatters = true}>
						Show all {cityMatters?.total_count} matters
					</button>
				{/if}
			</section>
		{:else if mattersLoading}
			<section class="matters-section">
				<div class="matters-section-header">
					<h2 class="matters-section-title">Active Matters</h2>
				</div>
				<div class="loading-matters">
					<p>Loading matters...</p>
				</div>
			</section>
		{/if}
	{/if}
	</div>

	<Footer />
</div>

<style>
	.container {
		width: var(--width-meetings);
		max-width: 100%;
		margin: 0 auto;
		padding: var(--space-xl) var(--space-md);
		min-height: 100vh;
		display: flex;
		flex-direction: column;
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
<<<<<<< Updated upstream
		color: var(--text-muted);
		text-decoration: none;
		font-family: var(--font-body);
		font-size: var(--text-sm);
=======
		color: var(--color-action);
		text-decoration: none;
		font-family: var(--font-mono);
>>>>>>> Stashed changes
		font-weight: var(--font-medium);
		transition: color var(--transition-fast);
	}

	.back-link:hover {
<<<<<<< Updated upstream
		color: var(--action-coral);
=======
		color: var(--color-action-hover);
		text-decoration: underline;
>>>>>>> Stashed changes
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
<<<<<<< Updated upstream
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
=======
		font-family: var(--font-mono);
		font-size: var(--text-3xl);
		color: var(--text);
		margin: 0;
		font-weight: var(--font-semibold);
	}

	.city-actions {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: 0.5rem;
	}

	.watch-city-btn {
		padding: 0.75rem 1.5rem;
		font-size: 0.9375rem;
		font-weight: 600;
		background: var(--color-action);
>>>>>>> Stashed changes
		color: white;
		border: none;
		border-radius: var(--radius-md);
		cursor: pointer;
<<<<<<< Updated upstream
		transition: all var(--transition-fast);
		white-space: nowrap;
		font-family: var(--font-body);
	}

	.watch-city-btn:hover {
		background: var(--action-coral-hover);
		transform: translateY(-1px);
=======
		transition: all var(--transition-normal);
		white-space: nowrap;
		font-family: var(--font-body);
		box-shadow: var(--shadow-action);
	}

	.watch-city-btn:hover {
		background: var(--color-action-hover);
		transform: translateY(-2px);
		box-shadow: 0 6px 16px rgba(249, 115, 22, 0.35);
>>>>>>> Stashed changes
	}

	.watch-city-btn:active {
		transform: translateY(0);
	}

	.source-row {
		margin-top: 0.75rem;
	}

	.source-attribution {
<<<<<<< Updated upstream
		font-family: var(--font-body);
		font-size: var(--text-xs);
=======
		font-family: var(--font-mono);
		font-size: var(--text-sm);
>>>>>>> Stashed changes
		color: var(--text-muted);
		display: flex;
		align-items: center;
		gap: 0.4rem;
	}

	.attribution-text {
		opacity: 0.7;
	}

	.source-link {
		color: var(--color-action);
		text-decoration: none;
		font-weight: var(--font-medium);
		transition: all var(--transition-fast);
		border-bottom: 1px solid transparent;
	}

	.source-link:hover {
		color: var(--color-action-hover);
		border-bottom-color: var(--color-action-hover);
	}

<<<<<<< Updated upstream
	.priority-hint {
		font-family: var(--font-body);
		font-size: var(--text-xs);
=======
	.view-toggle {
		display: flex;
		gap: 0.5rem;
		margin-bottom: 2rem;
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
		font-family: var(--font-mono);
		font-size: var(--text-sm);
		font-weight: var(--font-semibold);
		color: var(--text-muted);
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.toggle-btn:hover {
		color: var(--color-action);
		background: var(--color-action-soft);
	}

	.toggle-btn.active {
		background: var(--color-action);
		color: white;
		box-shadow: 0 2px 6px rgba(249, 115, 22, 0.3);
	}

	.toggle-past-btn {
		font-family: var(--font-mono);
		font-size: 0.9rem;
		font-weight: 600;
		color: var(--color-action);
		background: var(--surface);
		border: 2px solid var(--color-action);
		border-radius: var(--radius-md);
		padding: 0.5rem 1rem;
		cursor: pointer;
		transition: all var(--transition-normal);
	}

	.toggle-past-btn:hover {
		background: var(--color-action);
		color: white;
	}

	.controls-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 1rem;
		margin-bottom: 2rem;
		flex-wrap: wrap;
	}

	.controls-row .view-toggle {
		margin-bottom: 0;
	}

	.search-container {
		position: relative;
		display: flex;
		align-items: center;
	}

	.city-search {
		font-family: var(--font-mono);
		font-size: var(--text-sm);
		padding: 0.6rem 2rem 0.6rem 1rem;
		border: 1px solid var(--border);
		border-radius: var(--radius-md);
		background: var(--surface-secondary);
		color: var(--text);
		width: 200px;
		transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
	}

	.city-search:focus {
		outline: none;
		border-color: var(--color-action);
		box-shadow: 0 0 0 3px var(--color-action-soft);
	}

	.city-search::placeholder {
		color: var(--text-muted);
	}

	.clear-search {
		position: absolute;
		right: 0.5rem;
		background: none;
		border: none;
		color: var(--text-muted);
		cursor: pointer;
		font-family: var(--font-mono);
		font-size: var(--text-base);
		padding: 0.25rem;
		line-height: 1;
	}

	.clear-search:hover {
		color: var(--text);
	}

	.search-results-header {
		margin-bottom: 1rem;
	}

	.search-results-count {
		font-family: var(--font-mono);
		font-size: var(--text-sm);
		color: var(--text-muted);
	}

	.search-results-list {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.priority-hint {
		font-family: var(--font-mono);
		font-size: var(--text-sm);
>>>>>>> Stashed changes
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
<<<<<<< Updated upstream
		color: var(--action-coral);
=======
		color: var(--color-action);
>>>>>>> Stashed changes
	}

	.loading-matters {
		text-align: center;
<<<<<<< Updated upstream
		padding: var(--space-xl) var(--space-lg);
		color: var(--text-muted);
		font-family: var(--font-body);
		font-size: var(--text-sm);
=======
		padding: 4rem 2rem;
		color: var(--text-muted);
		font-family: var(--font-mono);
>>>>>>> Stashed changes
	}

	/* Matters Section (always visible) */
	.matters-section {
		margin-top: var(--space-3xl);
		padding-top: var(--space-xl);
		border-top: 1px solid var(--border-primary);
	}

<<<<<<< Updated upstream
	.matters-section-header {
		margin-bottom: var(--space-xl);
	}

	.matters-section-title-row {
		display: flex;
		align-items: center;
		gap: var(--space-md);
		margin-bottom: var(--space-xs);
	}

	.matters-section-title {
		font-family: var(--font-body);
		font-size: var(--text-xl);
		font-weight: var(--font-bold);
		color: var(--text);
		margin: 0;
		letter-spacing: -0.01em;
	}

	.matters-count {
		font-family: var(--font-body);
		font-size: var(--text-xs);
		font-weight: var(--font-medium);
		color: var(--text-muted);
		background: var(--surface-secondary);
		padding: 0.2rem 0.5rem;
		border-radius: var(--radius-sm);
	}

	.matters-section-subtitle {
		font-family: var(--font-body);
		font-size: var(--text-sm);
		color: var(--text-muted);
		margin: 0;
=======
	.matters-header {
		margin-bottom: 2rem;
		border-bottom: 2px solid var(--border);
		padding-bottom: 1rem;
	}

	.matters-title {
		font-family: var(--font-mono);
		font-size: var(--text-2xl);
		font-weight: var(--font-semibold);
		color: var(--text);
		margin: 0 0 0.5rem 0;
	}

	.matters-stats {
		font-family: var(--font-mono);
		font-size: var(--text-sm);
		color: var(--text-muted);
>>>>>>> Stashed changes
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
<<<<<<< Updated upstream
		background: var(--surface-card);
		border: 1px solid var(--border-primary);
		border-left: 3px solid var(--action-coral);
		border-radius: var(--radius-lg);
		padding: var(--space-lg);
=======
		background: var(--surface);
		border: 2px solid var(--border);
		border-left: 4px solid var(--color-action);
		border-radius: var(--radius-lg);
		padding: 1.5rem;
>>>>>>> Stashed changes
		transition: all var(--transition-normal);
		cursor: pointer;
	}

	.matter-card-link:hover .matter-card {
<<<<<<< Updated upstream
		border-color: var(--border-hover);
		background: var(--surface-card-hover);
=======
		border-left-color: var(--color-action-hover);
		box-shadow: 0 4px 12px rgba(249, 115, 22, 0.15);
>>>>>>> Stashed changes
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
<<<<<<< Updated upstream
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
=======
		font-size: var(--text-sm);
		font-weight: var(--font-bold);
		color: var(--badge-matter-text);
		background: var(--badge-matter-bg);
		border: 1.5px solid var(--badge-matter-border);
		padding: 0.35rem 0.75rem;
		border-radius: var(--radius-md);
	}

	.matter-type-label {
		font-family: var(--font-mono);
		font-size: var(--text-xs);
		font-weight: var(--font-semibold);
		color: var(--text-muted);
		background: var(--surface-secondary);
		padding: 0.3rem 0.65rem;
>>>>>>> Stashed changes
		border-radius: var(--radius-sm);
		text-transform: capitalize;
	}

	.appearances-badge {
<<<<<<< Updated upstream
		font-family: var(--font-body);
		font-size: var(--text-xs);
		font-weight: var(--font-semibold);
		color: var(--civic-green);
		background: #d1fae5;
		border: 1px solid #86efac;
		padding: 0.25rem 0.5rem;
=======
		font-family: var(--font-mono);
		font-size: var(--text-xs);
		font-weight: var(--font-bold);
		color: var(--badge-green-text);
		background: var(--badge-green-bg);
		border: 1px solid var(--badge-green-border);
		padding: 0.3rem 0.65rem;
>>>>>>> Stashed changes
		border-radius: var(--radius-sm);
	}

	.matter-card-title {
		font-family: var(--font-body);
		font-size: var(--text-base);
		font-weight: var(--font-semibold);
		color: var(--text);
		line-height: var(--leading-snug);
<<<<<<< Updated upstream
		margin: 0 0 var(--space-md) 0;
=======
		margin: 0 0 1rem 0;
>>>>>>> Stashed changes
	}

	.matter-card-topics {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-xs);
		margin-bottom: var(--space-md);
	}

	.matter-topic-tag {
<<<<<<< Updated upstream
		font-family: var(--font-body);
		font-size: var(--text-xs);
		padding: 0.2rem 0.5rem;
		background: var(--surface-warm);
		color: var(--text-subtle);
=======
		font-family: var(--font-mono);
		font-size: var(--text-xs);
		padding: 0.25rem 0.6rem;
		background: var(--surface-secondary);
		color: var(--color-action);
		border: 1px solid var(--border);
>>>>>>> Stashed changes
		border-radius: var(--radius-sm);
		font-weight: var(--font-medium);
	}

	.matter-card-summary {
		font-family: var(--font-body);
		font-size: var(--text-sm);
		line-height: var(--leading-relaxed);
<<<<<<< Updated upstream
		color: var(--text-muted);
		margin-bottom: var(--space-md);
=======
		color: var(--text-secondary);
		margin-bottom: 1rem;
>>>>>>> Stashed changes
	}

	.matter-timeline-container {
		margin-top: 1rem;
	}

	.show-more-matters {
		display: block;
		width: 100%;
		margin-top: var(--space-lg);
		padding: var(--space-md) var(--space-lg);
		background: transparent;
		border: 2px dashed var(--border-primary);
		border-radius: var(--radius-lg);
		font-family: var(--font-body);
		font-size: var(--text-sm);
		font-weight: var(--font-semibold);
		color: var(--text-muted);
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.show-more-matters:hover {
		border-color: var(--action-coral);
		color: var(--action-coral);
		background: var(--surface-warm);
	}

	.request-city-cta {
<<<<<<< Updated upstream
		margin-top: var(--space-xl);
		padding: var(--space-lg);
		background: var(--surface-warm);
		border: 1px solid var(--border-primary);
=======
		margin-top: 2rem;
		padding: 1.5rem;
		background: var(--bg-warm);
		border: 2px solid var(--color-action);
>>>>>>> Stashed changes
		border-radius: var(--radius-lg);
		text-align: center;
	}

	.cta-text {
<<<<<<< Updated upstream
		font-family: var(--font-body);
		font-size: var(--text-base);
		font-weight: var(--font-semibold);
		color: var(--text);
		margin: 0 0 var(--space-md) 0;
=======
		font-family: var(--font-mono);
		font-size: var(--text-base);
		font-weight: var(--font-semibold);
		color: var(--text);
		margin: 0 0 0.75rem 0;
>>>>>>> Stashed changes
	}

	.cta-button {
		display: inline-block;
		padding: 0.75rem 1.5rem;
<<<<<<< Updated upstream
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
=======
		background: var(--color-action);
		color: white;
		border: none;
		border-radius: var(--radius-md);
		font-family: var(--font-mono);
		font-size: var(--text-sm);
		font-weight: var(--font-medium);
		cursor: pointer;
		transition: background var(--transition-fast);
	}

	.cta-button:hover {
		background: var(--color-action-hover);
>>>>>>> Stashed changes
	}

	.cta-subtext {
		font-family: var(--font-body);
<<<<<<< Updated upstream
		font-size: var(--text-xs);
		color: var(--text-muted);
		margin: var(--space-md) 0 0 0;
=======
		font-size: var(--text-sm);
		color: var(--text-tertiary);
		margin: 0.75rem 0 0 0;
>>>>>>> Stashed changes
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
			border-radius: var(--radius-md);
		}

		.city-title {
<<<<<<< Updated upstream
			font-size: 1.5rem;
=======
			font-size: var(--text-2xl);
		}

		.city-title-row {
			flex-direction: column;
			align-items: flex-start;
			gap: 1rem;
		}

		.city-actions {
			width: 100%;
		}

		.watch-city-btn {
			width: 100%;
			text-align: center;
		}

		.controls-row {
			flex-direction: column;
			align-items: stretch;
>>>>>>> Stashed changes
		}

		.view-toggle {
			width: 100%;
			justify-content: center;
		}

		.toggle-btn {
			flex: 1;
			padding: 0.6rem 1rem;
			font-size: var(--text-sm);
		}

		.matter-card {
			padding: var(--space-md);
		}

		.matter-card-title {
			font-size: var(--text-base);
		}
	}
</style>
