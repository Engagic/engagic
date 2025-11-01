<script lang="ts">
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { searchMeetings, type SearchResult, type Meeting } from '$lib/api/index';
	import { parseCityUrl } from '$lib/utils/utils';
	import MeetingCard from '$lib/components/MeetingCard.svelte';
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

	function toggleTopic(topic: string) {
		if (selectedTopic === topic) {
			// Click again to clear
			goto(`/${city_banana}`);
		} else {
			// Activate filter
			goto(`/${city_banana}?topic=${encodeURIComponent(topic)}`);
		}
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
		<a href="/" class="compact-logo">engagic</a>

	<div class="city-header">
		<a href="/" class="back-link">← Back to search</a>
		{#if searchResults && searchResults.success}
			<h1 class="city-title">{searchResults.city_name}, {searchResults.state}</h1>
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
				<!-- Topic filter pills -->
				{#if allTopics().length > 0}
					<div class="topic-pills-container">
						<span class="pills-label">Filter by topic:</span>
						<div class="topic-pills">
							{#each allTopics() as topic}
								<button
									class="topic-pill {selectedTopic === topic ? 'active' : ''}"
									onclick={() => toggleTopic(topic)}
									type="button"
								>
									{topic}
								</button>
							{/each}
						</div>
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
								<MeetingCard
									{meeting}
									cityUrl={city_banana}
									isPast={true}
									animationDuration={isInitialLoad ? 300 : 0}
									animationDelay={isInitialLoad ? index * 50 : 0}
									onIntroEnd={() => { if (index === filteredPastMeetings.length - 1) isInitialLoad = false; }}
								/>
							{/each}
						{/if}
						
						{#each filteredUpcomingMeetings as meeting, index}
							<MeetingCard
								{meeting}
								cityUrl={city_banana}
								isPast={false}
								animationDuration={isInitialLoad ? 300 : 0}
								animationDelay={isInitialLoad ? index * 50 : 0}
								onIntroEnd={() => { if (index === filteredUpcomingMeetings.length - 1 && filteredPastMeetings.length === 0) isInitialLoad = false; }}
							/>
						{/each}
					</div>
				{:else}
					<div class="no-meetings">
						{#if selectedTopic}
							No meetings found with the topic "{selectedTopic}". Click the pill again to clear filter.
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
		position: relative;
	}

	.compact-logo {
		position: absolute;
		top: 0;
		right: 0;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.1rem;
		font-weight: 700;
		color: var(--civic-blue);
		text-decoration: none;
		z-index: 10;
	}

	.compact-logo:hover {
		opacity: 0.8;
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

	.topic-pills-container {
		margin-bottom: 1.5rem;
	}

	.pills-label {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
		color: var(--civic-gray);
		font-weight: 500;
		display: block;
		margin-bottom: 0.75rem;
	}

	.topic-pills {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.topic-pill {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8rem;
		padding: 0.5rem 0.85rem;
		background: var(--civic-light);
		color: var(--civic-blue);
		border: 1px solid var(--civic-border);
		border-radius: 20px;
		cursor: pointer;
		font-weight: 500;
		transition: all 0.2s ease;
	}

	.topic-pill:hover {
		background: white;
		border-color: var(--civic-blue);
		transform: translateY(-1px);
		box-shadow: 0 2px 4px rgba(79, 70, 229, 0.2);
	}

	.topic-pill.active {
		background: var(--civic-blue);
		color: white;
		border-color: var(--civic-blue);
	}

	.topic-pill.active:hover {
		background: var(--civic-blue);
		opacity: 0.9;
	}

	@media (max-width: 640px) {
		.container {
			width: 100%;
		}

		.compact-logo {
			font-size: 0.95rem;
		}

		.city-title {
			font-size: 1.5rem;
		}

		.pills-label {
			font-size: 0.75rem;
		}

		.topic-pill {
			font-size: 0.75rem;
			padding: 0.4rem 0.7rem;
		}
	}
</style>