<script lang="ts">
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { searchMeetings, type SearchResult, type Meeting } from '$lib/api/index';
	import { generateMeetingSlug, parseCityUrl } from '$lib/utils/utils';
	import { formatMeetingDate, extractTime } from '$lib/utils/date-utils';
	import Footer from '$lib/components/Footer.svelte';

	let city_url = $page.params.city_url;
	let searchResults: SearchResult | null = $state(null);
	let loading = $state(true);
	let error = $state('');
	let showPastMeetings = $state(false);
	let upcomingMeetings: Meeting[] = $state([]);
	let pastMeetings: Meeting[] = $state([]);

	// Snapshot: Preserve UI state during navigation
	// When user expands past meetings and navigates to a meeting detail,
	// this ensures the toggle and scroll position are restored on back navigation
	export const snapshot = {
		capture: () => ({
			showPastMeetings,
			scrollY: typeof window !== 'undefined' ? window.scrollY : 0
		}),
		restore: (values: { showPastMeetings: boolean; scrollY: number }) => {
			showPastMeetings = values.showPastMeetings;
			// Restore scroll position after DOM has updated
			if (typeof window !== 'undefined' && typeof values.scrollY === 'number') {
				setTimeout(() => window.scrollTo(0, values.scrollY), 0);
			}
		}
	};

	onMount(async () => {
		await loadCityMeetings();
	});

	async function loadCityMeetings() {
		loading = true;
		error = '';
		
		try {
			// Check if this is a static route that should not be handled as a city
			if (city_url === 'about') {
				goto('/about');
				return;
			}
			
			// Parse the city URL to get city name and state
			const parsed = parseCityUrl(city_url);
			if (!parsed) {
				throw new Error('Invalid city URL format');
			}
			
			// Search by city name and state
			const searchQuery = `${parsed.cityName}, ${parsed.state}`;
			const result = await searchMeetings(searchQuery);
			
			// Sort meetings by date (soonest first) using standardized dates
			if (result.success && result.meetings) {
				result.meetings.sort((a: Meeting, b: Meeting) => {
					// Use standardized meeting_date field
					const dateA = new Date(a.meeting_date);
					const dateB = new Date(b.meeting_date);
					
					// Return comparison (ascending order - soonest first)
					return dateA.getTime() - dateB.getTime();
				});
				
				// Split meetings into upcoming and past using standardized dates
				const now = new Date();
				upcomingMeetings = [];
				pastMeetings = [];
				
				for (const meeting of result.meetings) {
					const meetingDate = new Date(meeting.meeting_date);
					
					if (meetingDate >= now) {
						upcomingMeetings.push(meeting);
					} else {
						pastMeetings.push(meeting);
					}
				}
			}
			
			searchResults = result;
		} catch (err) {
			console.error('Failed to load meetings:', err);
			error = err instanceof Error ? err.message : 'No agendas posted yet, please come back later! Packets are typically posted within 48 hours of the meeting date';
		} finally {
			loading = false;
		}
	}
</script>

<svelte:head>
	<title>{searchResults && 'city_name' in searchResults ? `${searchResults.city_name}, ${searchResults.state}` : 'City'} - engagic</title>
	<meta name="description" content="Local government meetings and agendas" />
</svelte:head>

<div class="container">
	<div class="main-content">
		<header class="header">
			<a href="/" class="logo">engagic</a>
			<p class="tagline">civic engagement made simple</p>
		</header>

	<div class="city-header">
		<a href="/" class="back-link">← Back to search</a>
		{#if searchResults && searchResults.success}
			<h1 class="city-title">{searchResults.city_name}, {searchResults.state}</h1>
			{#if searchResults.cached}
				<div class="processing-status">Cached results</div>
			{/if}
		{:else if loading}
			<h1 class="city-title">Loading...</h1>
		{:else}
			<h1 class="city-title">City Not Found</h1>
		{/if}
	</div>

	{#if loading}
		<div class="loading">
			Loading meetings...
		</div>
	{:else if error}
		<div class="error-message">
			{error}
		</div>
	{:else if searchResults}
		{#if searchResults.success}
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
							{#each pastMeetings as meeting}
								<a href="/{city_url}/{generateMeetingSlug(meeting)}" class="meeting-card past-meeting">
									<div class="meeting-title">{(meeting.title || meeting.meeting_name)} on {formatMeetingDate(meeting.meeting_date)}</div>
									<div class="meeting-date">{extractTime(meeting.meeting_date)}</div>
									{#if meeting.processed_summary}
										<div class="meeting-status status-ready">AI Summary Available</div>
									{:else if meeting.packet_url}
										<div class="meeting-status status-packet">Agenda Packet Available</div>
									{:else}
										<div class="meeting-status status-none">No agenda posted yet</div>
									{/if}
								</a>
							{/each}
						{/if}
						
						{#each upcomingMeetings as meeting}
							<a href="/{city_url}/{generateMeetingSlug(meeting)}" class="meeting-card upcoming-meeting">
								<div class="meeting-title">{(meeting.title || meeting.meeting_name)} on {formatMeetingDate(meeting.meeting_date)}</div>
								<div class="meeting-date">{extractTime(meeting.meeting_date)}</div>
								{#if meeting.processed_summary}
									<div class="meeting-status status-ready">AI Summary Available</div>
								{:else if meeting.packet_url}
									<div class="meeting-status status-packet">Agenda Packet Available</div>
								{:else}
									<div class="meeting-status status-none">No agenda posted yet</div>
								{/if}
							</a>
						{/each}
					</div>
				{:else}
					<div class="no-meetings">
						No meetings found for this city
					</div>
				{/if}
			{:else}
				<div class="no-meetings">
					{'message' in searchResults ? searchResults.message : 'No meetings found for this city'}
				</div>
			{/if}
		{:else}
			<div class="error-message">
				{searchResults.message || 'Failed to load city meetings'}
			</div>
		{/if}
	{/if}
	</div>

	<Footer />
</div>

<style>
	.city-header {
		margin-bottom: 2rem;
	}

	.back-link {
		display: inline-block;
		margin-bottom: 1rem;
		color: var(--civic-blue);
		text-decoration: none;
		font-weight: 500;
	}

	.back-link:hover {
		text-decoration: underline;
	}

	.city-title {
		font-size: 2rem;
		color: var(--civic-dark);
		margin: 0;
		font-weight: 600;
	}

	@media (max-width: 640px) {
		.city-title {
			font-size: 1.5rem;
		}
	}
</style>