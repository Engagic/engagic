<script lang="ts">
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import type { Meeting } from '$lib/api/index';
	import MeetingCard from '$lib/components/MeetingCard.svelte';
	import Footer from '$lib/components/Footer.svelte';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	let city_banana = $page.params.city_url;
	let showPastMeetings = $state(false);
	let isInitialLoad = $state(true);

	// Data comes from load function - already available
	let searchResults = $state(data.searchResults);
	let upcomingMeetings: Meeting[] = $state(data.upcomingMeetings || []);
	let pastMeetings: Meeting[] = $state(data.pastMeetings || []);


	// Snapshot: Preserve UI state and data during navigation
	// When user expands past meetings and navigates to a meeting detail,
	// this ensures the toggle, data, and scroll position are restored on back navigation
	export const snapshot = {
		capture: () => ({
			showPastMeetings,
			scrollY: typeof window !== 'undefined' ? window.scrollY : 0
		}),
		restore: (values: {
			showPastMeetings: boolean;
			scrollY: number;
		}) => {
			showPastMeetings = values.showPastMeetings;
			isInitialLoad = false; // Skip animations when restoring from snapshot
			// Restore scroll position after DOM has updated
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
							>
								{showPastMeetings ? 'Hide' : 'Show'} Past Meetings ({pastMeetings.length})
							</button>
						{/if}
					</div>

					<div class="meeting-list">
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

				{#each upcomingMeetings as meeting, index}
					<MeetingCard
						{meeting}
						cityUrl={city_banana}
						isPast={false}
						animationDuration={isInitialLoad ? 300 : 0}
						animationDelay={isInitialLoad ? index * 50 : 0}
						onIntroEnd={() => { if (index === upcomingMeetings.length - 1 && pastMeetings.length === 0) isInitialLoad = false; }}
					/>
				{/each}
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
	}
</style>