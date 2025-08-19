<script lang="ts">
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { searchMeetings, type SearchResult, type Meeting } from '$lib/api';
	import { generateMeetingSlug, parseCityUrl } from '$lib/utils';

	let city_url = $page.params.city_url;
	let searchResults: SearchResult | null = $state(null);
	let loading = $state(true);
	let error = $state('');
	let showPastMeetings = $state(false);
	let upcomingMeetings: Meeting[] = $state([]);
	let pastMeetings: Meeting[] = $state([]);

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
				result.meetings.sort((a, b) => {
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

	function handleMeetingClick(meeting: Meeting) {
		const meetingSlug = generateMeetingSlug(meeting);
		goto(`/${city_url}/${meetingSlug}`);
	}

	function formatMeetingDate(dateString: string): string {
		// Parse the standardized date format (YYYY-MM-DD HH:MM:SS)
		const date = new Date(dateString);
		
		if (isNaN(date.getTime())) {
			// Fallback for unparseable dates
			return dateString;
		}
		
		const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
		const monthName = months[date.getMonth()];
		const day = date.getDate();
		const year = date.getFullYear();
		
		return `${monthName} ${day}, ${year}`;
	}

	function extractTime(dateString: string): string {
		// Parse the standardized date format and extract time
		const date = new Date(dateString);
		
		if (isNaN(date.getTime())) {
			return '';
		}
		
		// Format time as "H:MM AM/PM"
		return date.toLocaleTimeString('en-US', { 
			hour: 'numeric', 
			minute: '2-digit',
			hour12: true 
		});
	}
</script>

<svelte:head>
	<title>{searchResults?.city_name ? `${searchResults.city_name}, ${searchResults.state}` : 'City'} - engagic</title>
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
		{#if searchResults?.city_name}
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
					</div>
				{:else}
					<div class="no-meetings">
						No meetings found for this city
					</div>
				{/if}
			{:else}
				<div class="no-meetings">
					{searchResults.message || 'No meetings found for this city'}
				</div>
			{/if}
		{:else}
			<div class="error-message">
				{searchResults.message || 'Failed to load city meetings'}
			</div>
		{/if}
	{/if}
	</div>

	<footer class="footer">
		<div class="footer-links">
			<a href="/about" class="about-link">About</a>
			<span class="divider">•</span>
			<a href="https://github.com/Engagic/engagic" class="github-link" target="_blank" rel="noopener">
				<svg class="github-icon" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
					<path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.30 3.297-1.30.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
				</svg>
				Source
			</a>
		</div>
		<p class="footer-text">All your code is open source and readily auditable. made with love and rizz</p>
	</footer>
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