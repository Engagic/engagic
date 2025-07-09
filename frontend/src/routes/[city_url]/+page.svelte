<script lang="ts">
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import { searchMeetings, type SearchResult, type Meeting } from '$lib/api';
	import { generateMeetingSlug, parseCityUrl } from '$lib/utils';

	let city_url = $page.params.city_url;
	let searchResults: SearchResult | null = $state(null);
	let loading = $state(true);
	let error = $state('');

	onMount(async () => {
		await loadCityMeetings();
	});

	async function loadCityMeetings() {
		loading = true;
		error = '';
		
		try {
			// Parse the city URL to get city name and state
			const parsed = parseCityUrl(city_url);
			if (!parsed) {
				throw new Error('Invalid city URL format');
			}
			
			// Search by city name and state
			const searchQuery = `${parsed.cityName}, ${parsed.state}`;
			const result = await searchMeetings(searchQuery);
			searchResults = result;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load meetings';
		} finally {
			loading = false;
		}
	}

	function handleMeetingClick(meeting: Meeting) {
		const meetingSlug = generateMeetingSlug(meeting);
		window.location.href = `/${city_url}/${meetingSlug}`;
	}
</script>

<svelte:head>
	<title>{searchResults?.city_name ? `${searchResults.city_name}, ${searchResults.state}` : 'City'} - engagic</title>
	<meta name="description" content="Local government meetings and agendas" />
</svelte:head>

<div class="container">
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
				<div class="meeting-list">
					{#each searchResults.meetings as meeting}
						<div class="meeting-card" onclick={() => handleMeetingClick(meeting)}>
							<div class="meeting-title">{meeting.title || meeting.meeting_name}</div>
							<div class="meeting-date">{meeting.start || meeting.meeting_date}</div>
							<div class="meeting-status">Click to view agenda summary</div>
						</div>
					{/each}
				</div>
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