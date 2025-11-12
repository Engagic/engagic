<script lang="ts">
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import type { Meeting } from '$lib/api/index';
	import { getCityMatters } from '$lib/api/index';
	import MeetingCard from '$lib/components/MeetingCard.svelte';
	import MatterTimeline from '$lib/components/MatterTimeline.svelte';
	import Footer from '$lib/components/Footer.svelte';
	import type { PageData } from './$types';
	import { onMount } from 'svelte';

	let { data }: { data: PageData } = $props();

	let city_banana = $page.params.city_url;
	let showPastMeetings = $state(false);
	let isInitialLoad = $state(true);
	let viewMode = $state<'meetings' | 'matters'>('meetings');
	let cityMatters = $state<any>(null);
	let mattersLoading = $state(false);
	let mattersChecked = $state(false);

	// Data comes from load function - already available
	let searchResults = $state(data.searchResults);
	let upcomingMeetings: Meeting[] = $state(data.upcomingMeetings || []);
	let pastMeetings: Meeting[] = $state(data.pastMeetings || []);

	// Derived: Check if city has qualifying matters (2+ appearances)
	const hasQualifyingMatters = $derived(() => {
		if (!mattersChecked) return true; // Assume matters exist until checked
		return cityMatters && cityMatters.total_count > 0;
	});

	async function loadCityMatters() {
		if (cityMatters) return; // Already loaded
		mattersLoading = true;
		try {
			const result = await getCityMatters(city_banana, 50, 0);
			cityMatters = result;
			mattersChecked = true;

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
			<h1 class="city-title">{searchResults.city_name}, {searchResults.state}</h1>
		{:else}
			<h1 class="city-title">Loading...</h1>
		{/if}
	</div>

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
					</div>
				{/if}
			{:else}
				<div class="no-meetings">
					<p class="empty-state-title">No meetings found</p>
					<p class="empty-state-message">{'message' in searchResults ? searchResults.message : 'We could not find any meetings for this city. Agendas are typically posted 48 hours before meetings.'}</p>
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
								{#if matter.canonical_topics}
									{@const topics = JSON.parse(matter.canonical_topics)}
									{#if topics.length > 0}
										<div class="matter-card-topics">
											{#each topics.slice(0, 4) as topic}
												<span class="matter-topic-tag">{topic}</span>
											{/each}
										</div>
									{/if}
								{/if}
								{#if matter.canonical_summary}
									<div class="matter-card-summary">
										{matter.canonical_summary.substring(0, 200)}{matter.canonical_summary.length > 200 ? '...' : ''}
									</div>
								{/if}
								{#if hasMultipleAppearances}
									<div class="matter-timeline-container">
										<MatterTimeline matterId={matter.id} matterFile={matter.matter_file} />
									</div>
								{/if}
							</div>
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
		color: var(--civic-blue);
		text-decoration: none;
		font-family: 'IBM Plex Mono', monospace;
		font-weight: 500;
	}

	.back-link:hover {
		text-decoration: underline;
	}

	.city-title {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 2rem;
		color: var(--civic-dark);
		margin: 0;
		font-weight: 600;
	}

	.view-toggle {
		display: flex;
		gap: 0.5rem;
		margin-bottom: 2rem;
		background: var(--surface-secondary);
		padding: 0.35rem;
		border-radius: 12px;
		width: fit-content;
	}

	.toggle-btn {
		padding: 0.65rem 1.5rem;
		background: transparent;
		border: none;
		border-radius: 8px;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
		font-weight: 600;
		color: var(--civic-gray);
		cursor: pointer;
		transition: all 0.2s ease;
	}

	.toggle-btn:hover {
		color: var(--civic-blue);
		background: rgba(79, 70, 229, 0.1);
	}

	.toggle-btn.active {
		background: var(--civic-blue);
		color: white;
		box-shadow: 0 2px 6px rgba(79, 70, 229, 0.3);
	}

	.loading-matters {
		text-align: center;
		padding: 4rem 2rem;
		color: var(--civic-gray);
		font-family: 'IBM Plex Mono', monospace;
	}

	.matters-view {
		margin-top: 1rem;
	}

	.matters-header {
		margin-bottom: 2rem;
		border-bottom: 2px solid var(--border-primary);
		padding-bottom: 1rem;
	}

	.matters-title {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.5rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0 0 0.5rem 0;
	}

	.matters-stats {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
		color: var(--civic-gray);
	}

	.matters-list {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
	}

	.matter-card {
		background: var(--surface-primary);
		border: 2px solid var(--border-primary);
		border-left: 4px solid var(--civic-blue);
		border-radius: 12px;
		padding: 1.5rem;
		transition: all 0.2s ease;
	}

	.matter-card:hover {
		border-left-color: var(--civic-accent);
		box-shadow: 0 4px 12px rgba(79, 70, 229, 0.1);
	}

	.matter-card-header {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-bottom: 1rem;
		flex-wrap: wrap;
	}

	.matter-file-badge {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
		font-weight: 700;
		color: #1e40af;
		background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
		border: 1.5px solid #3b82f6;
		padding: 0.35rem 0.75rem;
		border-radius: 8px;
	}

	.matter-type-label {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--civic-gray);
		background: var(--surface-secondary);
		padding: 0.3rem 0.65rem;
		border-radius: 6px;
		text-transform: capitalize;
	}

	.appearances-badge {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		font-weight: 700;
		color: var(--civic-green);
		background: #d1fae5;
		border: 1px solid #86efac;
		padding: 0.3rem 0.65rem;
		border-radius: 6px;
	}

	.matter-card-title {
		font-family: Georgia, 'Times New Roman', Times, serif;
		font-size: 1.15rem;
		font-weight: 600;
		color: var(--text-primary);
		line-height: 1.4;
		margin: 0 0 1rem 0;
	}

	.matter-card-topics {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin-bottom: 1rem;
	}

	.matter-topic-tag {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.7rem;
		padding: 0.25rem 0.6rem;
		background: var(--surface-secondary);
		color: var(--civic-blue);
		border: 1px solid var(--border-primary);
		border-radius: 4px;
		font-weight: 500;
	}

	.matter-card-summary {
		font-family: Georgia, 'Times New Roman', Times, serif;
		font-size: 0.95rem;
		line-height: 1.6;
		color: var(--text-secondary);
		margin-bottom: 1rem;
	}

	.matter-timeline-container {
		margin-top: 1rem;
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