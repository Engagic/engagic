<script lang="ts">
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { fly } from 'svelte/transition';
	import { searchMeetings, type SearchResult, type Meeting } from '$lib/api/index';
	import { generateMeetingSlug, parseCityUrl } from '$lib/utils/utils';
	import { formatMeetingDate, extractTime } from '$lib/utils/date-utils';
	import Footer from '$lib/components/Footer.svelte';

	let city_banana = $page.params.city_url;
	let searchResults: SearchResult | null = $state(null);
	let loading = $state(true);
	let error = $state('');
	let showPastMeetings = $state(false);
	let upcomingMeetings: Meeting[] = $state([]);
	let pastMeetings: Meeting[] = $state([]);
	let isInitialLoad = $state(true);

	// Topic filtering
	let selectedTopic = $derived($page.url.searchParams.get('topic'));

	// Filter meetings by selected topic
	let filteredUpcomingMeetings = $derived(
		selectedTopic
			? upcomingMeetings.filter(m => m.topics?.includes(selectedTopic))
			: upcomingMeetings
	);
	let filteredPastMeetings = $derived(
		selectedTopic
			? pastMeetings.filter(m => m.topics?.includes(selectedTopic))
			: pastMeetings
	);

	// Get all unique topics from all meetings
	let allTopics = $derived(() => {
		const topics = new Set<string>();
		[...upcomingMeetings, ...pastMeetings].forEach(m => {
			m.topics?.forEach(t => topics.add(t));
		});
		return Array.from(topics).sort();
	});

	function clearTopicFilter() {
		goto(`/${city_banana}`);
	}

	// Snapshot: Preserve UI state and data during navigation
	// When user expands past meetings and navigates to a meeting detail,
	// this ensures the toggle, data, and scroll position are restored on back navigation
	export const snapshot = {
		capture: () => ({
			showPastMeetings,
			searchResults,
			upcomingMeetings,
			pastMeetings,
			loading,
			error,
			scrollY: typeof window !== 'undefined' ? window.scrollY : 0
		}),
		restore: (values: {
			showPastMeetings: boolean;
			searchResults: SearchResult | null;
			upcomingMeetings: Meeting[];
			pastMeetings: Meeting[];
			loading: boolean;
			error: string;
			scrollY: number;
		}) => {
			showPastMeetings = values.showPastMeetings;
			searchResults = values.searchResults;
			upcomingMeetings = values.upcomingMeetings;
			pastMeetings = values.pastMeetings;
			loading = values.loading;
			error = values.error;
			isInitialLoad = false; // Skip animations when restoring from snapshot
			// Restore scroll position after DOM has updated
			if (typeof window !== 'undefined' && typeof values.scrollY === 'number') {
				setTimeout(() => window.scrollTo(0, values.scrollY), 0);
			}
		}
	};

	onMount(async () => {
		// Only fetch if we don't already have data from snapshot
		if (!searchResults) {
			await loadCityMeetings();
		}
	});

	async function loadCityMeetings() {
		loading = true;
		error = '';
		
		try {
			// Check if this is a static route that should not be handled as a city
			if (city_banana === 'about') {
				goto('/about');
				return;
			}

			// Parse the city URL to get city name and state
			const parsed = parseCityUrl(city_banana);
			if (!parsed) {
				throw new Error('Invalid city URL format');
			}
			
			// Search by city name and state
			const searchQuery = `${parsed.cityName}, ${parsed.state}`;
			const result = await searchMeetings(searchQuery);
			
			// Sort meetings by date (soonest first) using standardized dates
			if (result.success && result.meetings) {
				result.meetings.sort((a: Meeting, b: Meeting) => {
					// Handle null dates by treating them as far future
					const dateA = a.date ? new Date(a.date) : new Date(9999, 11, 31);
					const dateB = b.date ? new Date(b.date) : new Date(9999, 11, 31);

					// Return comparison (ascending order - soonest first)
					return dateA.getTime() - dateB.getTime();
				});

				// Split meetings into upcoming and past using standardized dates
				const now = new Date();
				upcomingMeetings = [];
				pastMeetings = [];

				for (const meeting of result.meetings) {
					if (!meeting.date || meeting.date === 'null' || meeting.date === '') {
						// Meetings with no date go to upcoming
						upcomingMeetings.push(meeting);
						continue;
					}

					const meetingDate = new Date(meeting.date);

					// Skip invalid dates (epoch 0)
					if (isNaN(meetingDate.getTime()) || meetingDate.getTime() === 0) {
						upcomingMeetings.push(meeting);
						continue;
					}

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

	{#if searchResults}
		<!-- Show data immediately if available (from snapshot or fresh load) -->
		{#if searchResults.success}
			{#if searchResults.meetings && searchResults.meetings.length > 0}
				<!-- Topic filter display -->
				{#if selectedTopic}
					<div class="topic-filter-active">
						<span class="filter-label">Filtering by topic:</span>
						<span class="filter-topic">{selectedTopic}</span>
						<button class="clear-filter-btn" onclick={clearTopicFilter} type="button">
							Clear filter
						</button>
					</div>
				{/if}

				{#if filteredUpcomingMeetings.length > 0 || filteredPastMeetings.length > 0}
					<div class="meetings-filter">
						{#if filteredUpcomingMeetings.length > 0}
							<h2 class="meetings-section-title">Upcoming Meetings</h2>
						{/if}
						{#if filteredPastMeetings.length > 0 && filteredUpcomingMeetings.length === 0}
							<h2 class="meetings-section-title">No Upcoming Meetings</h2>
						{/if}
						{#if filteredPastMeetings.length > 0}
							<button
								class="toggle-past-btn"
								onclick={() => showPastMeetings = !showPastMeetings}
							>
								{showPastMeetings ? 'Hide' : 'Show'} Past Meetings ({filteredPastMeetings.length})
							</button>
						{/if}
					</div>
					
					<div class="meeting-list">
						{#if showPastMeetings}
							{#if filteredPastMeetings.length > 0}
								<h3 class="past-meetings-divider">Past Meetings</h3>
							{/if}
							{#each filteredPastMeetings as meeting, index}
								{@const date = meeting.date ? new Date(meeting.date) : null}
								{@const isValidDate = date && !isNaN(date.getTime()) && date.getTime() !== 0}
								{@const dayOfWeek = isValidDate ? date.toLocaleDateString('en-US', { weekday: 'short' }) : null}
								{@const monthDay = isValidDate ? date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : null}
								{@const timeStr = extractTime(meeting.date)}
								<a
									href="/{city_banana}/{generateMeetingSlug(meeting)}"
									class="meeting-card past-meeting"
									in:fly|global={{ y: 20, duration: isInitialLoad ? 300 : 0, delay: isInitialLoad ? index * 50 : 0 }}
									onintroend={() => { if (index === filteredPastMeetings.length - 1) isInitialLoad = false; }}
								>
									<div class="meeting-card-header">
										<div class="meeting-title">
											{meeting.title}
										</div>
										{#if isValidDate}
											<div class="meeting-date-time">
												{dayOfWeek}, {monthDay}{#if timeStr} • {timeStr}{/if}
											</div>
										{/if}
									</div>

									{#if meeting.summary}
										<div class="meeting-status status-ready">
											✓ Summary Ready
										</div>
									{:else if meeting.packet_url}
										<div class="meeting-status status-packet">
											Packet Available
										</div>
									{:else}
										<div class="meeting-status status-none">
											No agenda posted
										</div>
									{/if}
								</a>
							{/each}
						{/if}
						
						{#each filteredUpcomingMeetings as meeting, index}
							{@const date = meeting.date ? new Date(meeting.date) : null}
							{@const isValidDate = date && !isNaN(date.getTime()) && date.getTime() !== 0}
							{@const dayOfWeek = isValidDate ? date.toLocaleDateString('en-US', { weekday: 'short' }) : null}
							{@const monthDay = isValidDate ? date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : null}
							{@const timeStr = extractTime(meeting.date)}
							<a
								href="/{city_banana}/{generateMeetingSlug(meeting)}"
								class="meeting-card upcoming-meeting"
								in:fly|global={{ y: 20, duration: isInitialLoad ? 300 : 0, delay: isInitialLoad ? index * 50 : 0 }}
								onintroend={() => { if (index === filteredUpcomingMeetings.length - 1 && filteredPastMeetings.length === 0) isInitialLoad = false; }}
							>
								<div class="meeting-card-header">
									<div class="meeting-title">
										{meeting.title}
									</div>
									{#if isValidDate}
										<div class="meeting-date-time">
											{dayOfWeek}, {monthDay}{#if timeStr} • {timeStr}{/if}
										</div>
									{/if}
								</div>

								{#if meeting.items?.length > 0 && meeting.items.some(item => item.summary)}
									<div class="meeting-status status-items">
										✓ Item Summaries
									</div>
								{:else if meeting.summary}
									<div class="meeting-status status-summary">
										✓ Summary Ready
									</div>
								{:else if meeting.agenda_url}
									<div class="meeting-status status-agenda">
										Agenda Posted
									</div>
								{:else if meeting.packet_url}
									<div class="meeting-status status-packet">
										Packet Posted
									</div>
								{:else}
									<div class="meeting-status status-none">
										No Agenda Posted
									</div>
								{/if}

								{#if meeting.topics && meeting.topics.length > 0}
									<div class="meeting-topics">
										{#each meeting.topics as topic}
											<span class="topic-tag">{topic}</span>
										{/each}
									</div>
								{/if}
							</a>
						{/each}
					</div>
				{:else}
					<div class="no-meetings">
						{#if selectedTopic}
							No meetings found with the topic "{selectedTopic}". <button class="clear-filter-btn" onclick={clearTopicFilter} type="button">Clear filter</button>
						{:else}
							No meetings found for this city
						{/if}
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
	{:else if error}
		<div class="error-message">
			{error}
		</div>
	{:else if loading}
		<div class="loading">
			Loading meetings...
		</div>
	{/if}
	</div>

	<Footer />
</div>

<style>
	.container {
		width: var(--width-meetings);
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

	.topic-filter-active {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 1rem;
		background: var(--civic-light);
		border: 1px solid var(--civic-border);
		border-radius: 8px;
		margin-bottom: 1.5rem;
		flex-wrap: wrap;
	}

	.filter-label {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
		color: var(--civic-gray);
		font-weight: 500;
	}

	.filter-topic {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
		padding: 0.4rem 0.75rem;
		background: var(--civic-blue);
		color: white;
		border-radius: 6px;
		font-weight: 600;
	}

	.clear-filter-btn {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
		padding: 0.4rem 0.75rem;
		background: white;
		color: var(--civic-blue);
		border: 1px solid var(--civic-blue);
		border-radius: 6px;
		cursor: pointer;
		font-weight: 500;
		transition: all 0.2s ease;
	}

	.clear-filter-btn:hover {
		background: var(--civic-blue);
		color: white;
	}

	@media (max-width: 640px) {
		.container {
			width: 100%;
		}

		.header {
			margin-bottom: 1rem;
		}

		.tagline {
			display: none;
		}

		.logo {
			margin-bottom: 0;
		}

		.city-title {
			font-size: 1.5rem;
		}

		.topic-filter-active {
			padding: 0.75rem;
			gap: 0.5rem;
		}

		.filter-label {
			font-size: 0.75rem;
		}

		.filter-topic {
			font-size: 0.8rem;
			padding: 0.3rem 0.6rem;
		}

		.clear-filter-btn {
			font-size: 0.75rem;
			padding: 0.3rem 0.6rem;
		}
	}
</style>