<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { fly, fade } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';
	import { apiClient } from '$lib/api/api-client';
	import type { SearchResult, CityOption, Meeting, AnalyticsData, UpcomingMeeting, TrendingTopic } from '$lib/api/types';
	import { isSearchSuccess, isSearchAmbiguous } from '$lib/api/types';
	import { generateCityUrl, generateMeetingSlug } from '$lib/utils/utils';
	import { validateSearchQuery } from '$lib/utils/sanitize';
	import { logger } from '$lib/services/logger';
	import { getAnalytics } from '$lib/api/index';
	import Footer from '$lib/components/Footer.svelte';
	import MeetingCard from '$lib/components/MeetingCard.svelte';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	let searchQuery = $state('');
	let searchResults: SearchResult | null = $state(null);
	let loading = $state(false);
	let loadingRandom = $state(false);
	let loadingRandomPolicy = $state(false);
	let error = $state('');
	let currentStatIndex = $state(0);

	// Analytics fetched client-side (not blocking SSR)
	let analytics: AnalyticsData | null = $state(null);

	// Happening This Week - upcoming meetings across all cities
	let upcomingMeetings: UpcomingMeeting[] = $state([]);
	let loadingUpcoming = $state(true);

	// Trending topics
	let trendingTopics: TrendingTopic[] = $state([]);

	const stats = $derived.by(() => {
		if (!analytics) return [];
		return [
			{ label: 'cities tracked', value: analytics.real_metrics.cities_covered.toLocaleString() },
			{ label: 'meetings summarized', value: analytics.real_metrics.agendas_summarized.toLocaleString() },
			{ label: 'total meetings', value: analytics.real_metrics.meetings_tracked.toLocaleString() }
		];
	});

	onMount(() => {
		// Fetch analytics client-side (non-blocking)
		getAnalytics().then((data) => {
			analytics = data;
		}).catch((err) => {
			logger.error('Analytics fetch failed', err as Error);
		});

		// Fetch upcoming meetings for "Happening This Week"
		apiClient.getUpcomingMeetings(168, 8).then((data) => {
			upcomingMeetings = data.meetings;
			loadingUpcoming = false;
		}).catch((err) => {
			logger.error('Upcoming meetings fetch failed', err as Error);
			loadingUpcoming = false;
		});

		// Fetch trending topics
		apiClient.getTrendingTopics('week', 6).then((data) => {
			trendingTopics = data.topics;
		}).catch((err) => {
			logger.error('Trending topics fetch failed', err as Error);
		});

		// Rotate stats every 3 seconds
		const interval = setInterval(() => {
			if (stats.length > 0) {
				currentStatIndex = (currentStatIndex + 1) % stats.length;
			}
		}, 3000);

		return () => clearInterval(interval);
	});

	// Snapshot: Preserve search state during navigation
	// When user searches for a city, gets ambiguous results, clicks one, and navigates back,
	// this ensures the search query and results list are restored
	export const snapshot = {
		capture: () => ({
			searchQuery,
			searchResults,
			error,
			scrollY: typeof window !== 'undefined' ? window.scrollY : 0
		}),
		restore: (values: {
			searchQuery: string;
			searchResults: SearchResult | null;
			error: string;
			scrollY: number;
		}) => {
			searchQuery = values.searchQuery;
			searchResults = values.searchResults;
			error = values.error;
			// Restore scroll position after DOM has updated
			if (typeof window !== 'undefined' && typeof values.scrollY === 'number') {
				setTimeout(() => window.scrollTo(0, values.scrollY), 0);
			}
		}
	};

	async function handleSearch() {
		const validationError = validateSearchQuery(searchQuery);
		if (validationError) {
			error = validationError;
			return;
		}

		loading = true;
		error = '';
		searchResults = null;

		try {
			const result = await apiClient.searchMeetings(searchQuery.trim());
			searchResults = result;

			// If successful and has city info, navigate to city page with cached data
			if (isSearchSuccess(result)) {
				const cityUrl = generateCityUrl(result.city_name, result.state);
				logger.trackEvent('search_success', { query: searchQuery, city: result.city_name });
				// Pass search results through navigation state to avoid duplicate API call
				goto(`/${cityUrl}`, { state: { cachedSearchResults: result } });
			} else if (isSearchAmbiguous(result)) {
				logger.trackEvent('search_ambiguous', { query: searchQuery });
			} else {
				// API returned not found - check if it's a state search as fallback
				const stateDetection = detectStateSearch(searchQuery);
				if (stateDetection.isState && stateDetection.stateCode) {
					logger.trackEvent('state_search', { query: searchQuery, state: stateDetection.stateCode });
					goto(`/state/${stateDetection.stateCode}`);
				}
				// Otherwise the "not found" message from API will be shown via searchResults
			}
		} catch (err) {
			logger.error('Search failed', err as Error, { query: searchQuery });
			error = err instanceof Error ? err.message : 'Search failed. Please try again.';
		} finally {
			loading = false;
		}
	}

	async function handleCityOptionClick(cityOption: CityOption) {
		const cityUrl = generateCityUrl(cityOption.city_name, cityOption.state);

		// Fetch city data once and pass through navigation state
		loading = true;
		try {
			const result = await apiClient.searchMeetings(`${cityOption.city_name}, ${cityOption.state}`);
			goto(`/${cityUrl}`, { state: { cachedSearchResults: result } });
		} catch (err) {
			// Fallback: navigate without cache, let city page handle fetch
			goto(`/${cityUrl}`);
		} finally {
			loading = false;
		}
	}
	
	async function handleRandomMeeting() {
		loadingRandom = true;
		error = '';

		try {
			const result = await apiClient.getRandomMeetingWithItems();
			if (result.meeting) {
				// Extract city name and state from banana
				// banana format is like "planoTX" - city name + state code
				const banana = result.meeting.banana;
				const stateMatch = banana.match(/([A-Z]{2})$/);

				if (stateMatch) {
					// Navigate directly to the meeting detail page
					const cityUrl = banana; // banana is already in the right format

					// Create a Meeting object for slug generation
					const meeting: Meeting = {
						id: result.meeting.id,
						banana: result.meeting.banana,
						title: result.meeting.title,
						date: result.meeting.date,
						packet_url: result.meeting.packet_url
					};

					const meetingSlug = generateMeetingSlug(meeting);
					logger.trackEvent('random_meeting_click', {
						city: banana,
						quality_score: result.meeting.quality_score
					});

					goto(`/${cityUrl}/${meetingSlug}`);
				} else {
					error = 'Invalid meeting data received';
				}
			}
		} catch (err) {
			logger.error('Random meeting failed', err as Error);
			error = 'Failed to load random meeting. Please try again.';
		} finally {
			loadingRandom = false;
		}
	}

	async function handleRandomPolicy() {
		loadingRandomPolicy = true;
		error = '';

		try {
			const result = await apiClient.getRandomMatter();
			if (result.matter) {
				logger.trackEvent('random_policy_click', {
					matter_id: result.matter.id,
					city: result.matter.banana,
					appearance_count: result.matter.appearance_count
				});

				goto(`/matter/${result.matter.id}`);
			}
		} catch (err) {
			logger.error('Random policy failed', err as Error);
			error = 'Failed to load random policy. Please try again.';
		} finally {
			loadingRandomPolicy = false;
		}
	}

	function handleKeydown(event: KeyboardEvent) {
		if (event.key === 'Enter') {
			handleSearch();
		}
	}

	// Detect if search is for a state
	const STATE_CODES: Record<string, string> = {
		AL: 'Alabama', AK: 'Alaska', AZ: 'Arizona', AR: 'Arkansas', CA: 'California',
		CO: 'Colorado', CT: 'Connecticut', DE: 'Delaware', FL: 'Florida', GA: 'Georgia',
		HI: 'Hawaii', ID: 'Idaho', IL: 'Illinois', IN: 'Indiana', IA: 'Iowa',
		KS: 'Kansas', KY: 'Kentucky', LA: 'Louisiana', ME: 'Maine', MD: 'Maryland',
		MA: 'Massachusetts', MI: 'Michigan', MN: 'Minnesota', MS: 'Mississippi', MO: 'Missouri',
		MT: 'Montana', NE: 'Nebraska', NV: 'Nevada', NH: 'New Hampshire', NJ: 'New Jersey',
		NM: 'New Mexico', NY: 'New York', NC: 'North Carolina', ND: 'North Dakota', OH: 'Ohio',
		OK: 'Oklahoma', OR: 'Oregon', PA: 'Pennsylvania', RI: 'Rhode Island', SC: 'South Carolina',
		SD: 'South Dakota', TN: 'Tennessee', TX: 'Texas', UT: 'Utah', VT: 'Vermont',
		VA: 'Virginia', WA: 'Washington', WV: 'West Virginia', WI: 'Wisconsin', WY: 'Wyoming'
	};

	function detectStateSearch(query: string): { isState: boolean; stateCode?: string; stateName?: string } {
		const trimmed = query.trim();
		const upper = trimmed.toUpperCase();

		// Check if it's a 2-letter state code
		if (upper.length === 2 && STATE_CODES[upper]) {
			return { isState: true, stateCode: upper, stateName: STATE_CODES[upper] };
		}

		// Check if it's a full state name
		const stateEntry = Object.entries(STATE_CODES).find(([, name]) =>
			name.toLowerCase() === trimmed.toLowerCase()
		);

		if (stateEntry) {
			return { isState: true, stateCode: stateEntry[0], stateName: stateEntry[1] };
		}

		return { isState: false };
	}

</script>

<svelte:head>
	<title>engagic - civic engagement made simple</title>
	<meta name="description" content="Find your local government meetings and agendas" />
</svelte:head>

<div class="container">
	<header class="header">
			<div class="logo-container">
				<img src="/icon-192.png" alt="" class="logo-icon" />
				<a href="/" class="logo">engagic</a>
			</div>
			<p class="tagline">civic engagement made simple</p>
			{#if stats.length > 0}
				{#key currentStatIndex}
					<p class="hero-stat">
						<span class="stat-value">{stats[currentStatIndex].value}</span>
						<span class="stat-label">{stats[currentStatIndex].label}</span>
					</p>
				{/key}
			{/if}
		</header>

		<div class="search-section">
		<input 
			type="text" 
			class="search-input"
			bind:value={searchQuery}
			onkeydown={handleKeydown}
			placeholder="Enter zipcode, city, or state"
			disabled={loading || loadingRandom || loadingRandomPolicy}
			aria-label="Search for local government meetings"
			aria-invalid={!!error}
			aria-describedby={error ? "search-error" : undefined}
		/>
		<button
			class="search-button"
			onclick={handleSearch}
			disabled={loading || loadingRandom || loadingRandomPolicy || !searchQuery.trim()}
		>
			{loading ? 'Searching...' : 'Search'}
		</button>

		<div class="button-divider">
			<span>or</span>
		</div>

		<div class="random-buttons">
			<button
				class="random-button random-meeting"
				onclick={handleRandomMeeting}
				disabled={loading || loadingRandom || loadingRandomPolicy}
			>
				{loadingRandom ? 'Loading...' : 'Discover a Meeting'}
			</button>

			<button
				class="random-button random-policy"
				onclick={handleRandomPolicy}
				disabled={loading || loadingRandom || loadingRandomPolicy}
			>
				{loadingRandomPolicy ? 'Loading...' : 'Discover a Policy'}
			</button>
		</div>
	</div>

	{#if error}
		<div class="error-message" id="search-error" role="alert">
			{error}
		</div>
	{/if}

	{#if searchResults}
		<div class="results-section" in:fly={{ y: 20, duration: 300, easing: cubicOut }}>
			{#if searchResults.success === false && searchResults.ambiguous && searchResults.city_options}
				<div class="ambiguous-cities">
					<div class="ambiguous-message" in:fade={{ duration: 200 }}>
						{@html searchResults.message}
					</div>
					<div class="city-options">
						{#each searchResults.city_options as cityOption, index}
							<div
								class="city-option-row"
								in:fly={{ y: 15, duration: 250, delay: 100 + index * 50, easing: cubicOut }}
							>
								<button
									class="city-option"
									onclick={() => handleCityOptionClick(cityOption)}
								>
									{cityOption.display_name}
								</button>
								<div class="city-stats">
									<span class="stat-total">{cityOption.total_meetings}</span>
									<span class="stat-separator">|</span>
									<span class="stat-packets">{cityOption.meetings_with_packet}</span>
									<span class="stat-separator">|</span>
									<span class="stat-summaries">{cityOption.summarized_meetings}</span>
								</div>
							</div>
						{/each}
					</div>
				</div>
			{:else if !searchResults.success}
				<div class="error-message" in:fly={{ y: 10, duration: 250, easing: cubicOut }}>
					{searchResults.message || 'Search failed'}
				</div>
				<div class="request-city-cta" in:fly={{ y: 15, duration: 300, delay: 150, easing: cubicOut }}>
					<p class="cta-text">Looking for a city we don't track yet?</p>
					<a href="/dashboard" class="cta-link">Create an account and request it</a>
					<p class="cta-subtext">Cities with active watchers get priority coverage.</p>
				</div>
			{/if}
		</div>
	{:else if loading}
		<div class="loading">
			Searching for meetings...
		</div>
	{/if}

	<!-- Happening This Week Section -->
	{#if !searchResults}
		<section class="happening-section" in:fade={{ duration: 300, delay: 100 }}>
			{#if trendingTopics.length > 0}
				<div class="trending-topics">
					<h2 class="section-title">What America is Discussing</h2>
					<div class="topic-chips">
						{#each trendingTopics as topic, index}
							<span
								class="topic-chip"
								class:trending-up={topic.trend === 'up'}
								class:trending-new={topic.trend === 'new'}
								in:fly={{ y: 10, duration: 200, delay: 150 + index * 30, easing: cubicOut }}
							>
								{topic.display_name}
								{#if topic.trend === 'up'}
									<span class="trend-indicator">+</span>
								{:else if topic.trend === 'new'}
									<span class="trend-indicator">new</span>
								{/if}
							</span>
						{/each}
					</div>
				</div>
			{/if}

			<div class="upcoming-feed">
				<h2 class="section-title">Happening This Week</h2>
				{#if loadingUpcoming}
					<div class="loading-upcoming">
						<p>Loading upcoming meetings...</p>
					</div>
				{:else if upcomingMeetings.length > 0}
					<div class="meetings-grid">
						{#each upcomingMeetings as upcoming, index}
							{@const meeting = {
								id: upcoming.id,
								banana: upcoming.banana,
								title: upcoming.title,
								date: upcoming.date,
								topics: upcoming.topics,
								participation: upcoming.participation
							}}
							<MeetingCard
								{meeting}
								cityUrl={upcoming.banana}
								showCity={true}
								cityName={`${upcoming.city_name}, ${upcoming.state}`}
								animationDelay={index * 75}
								animationDuration={300}
							/>
						{/each}
					</div>
				{:else}
					<p class="no-upcoming">No meetings scheduled this week. Check back soon!</p>
				{/if}
			</div>
		</section>
	{/if}

	<Footer />
</div>

<style>
<<<<<<< Updated upstream
=======
	.value-prop {
		text-align: center;
		margin-bottom: var(--space-xl);
	}

	.value-headline {
		font-size: var(--text-xl);
		font-weight: var(--font-semibold);
		color: var(--text);
		margin: 0 0 var(--space-sm) 0;
	}

	.value-subtext {
		font-size: var(--text-base);
		color: var(--text-secondary);
		margin: 0 0 var(--space-md) 0;
		line-height: var(--leading-relaxed);
		max-width: 480px;
		margin-left: auto;
		margin-right: auto;
	}

	.learn-more {
		font-size: var(--text-sm);
		color: var(--color-action);
		text-decoration: none;
		transition: color var(--transition-fast);
	}

	.learn-more:hover {
		color: var(--color-action-hover);
		text-decoration: underline;
	}

	@media (max-width: 640px) {
		.value-headline {
			font-size: var(--text-lg);
		}

		.value-subtext {
			font-size: var(--text-sm);
		}
	}

>>>>>>> Stashed changes
	.logo-container {
		display: flex;
		align-items: center;
		justify-content: center;
<<<<<<< Updated upstream
		gap: 1rem;
=======
		gap: var(--space-md);
>>>>>>> Stashed changes
		margin-bottom: var(--space-sm);
	}

	.logo-icon {
		width: 64px;
		height: 64px;
		border-radius: var(--radius-lg);
<<<<<<< Updated upstream
		box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
=======
		box-shadow: var(--shadow-md);
>>>>>>> Stashed changes
	}

	@media (max-width: 640px) {
		.logo-icon {
			width: 48px;
			height: 48px;
<<<<<<< Updated upstream
			border-radius: var(--radius-md);
=======
			border-radius: var(--radius-lg);
>>>>>>> Stashed changes
		}
	}

	.request-city-cta {
		margin-top: var(--space-lg);
		padding: var(--space-lg);
<<<<<<< Updated upstream
		background: var(--surface-warm);
		border: 1px solid var(--border-primary);
=======
		background: var(--bg-warm);
		border: 1px solid var(--border);
>>>>>>> Stashed changes
		border-radius: var(--radius-lg);
		text-align: center;
	}

	.cta-text {
<<<<<<< Updated upstream
		font-family: var(--font-body);
=======
>>>>>>> Stashed changes
		font-size: var(--text-base);
		font-weight: var(--font-semibold);
		color: var(--text);
		margin: 0 0 var(--space-sm) 0;
	}

	.cta-link {
		display: inline-block;
<<<<<<< Updated upstream
		color: var(--action-coral);
		font-family: var(--font-body);
=======
		color: var(--color-action);
>>>>>>> Stashed changes
		font-size: var(--text-sm);
		font-weight: var(--font-medium);
		text-decoration: underline;
		text-underline-offset: 3px;
<<<<<<< Updated upstream
		transition: opacity var(--transition-fast);
=======
		transition: color var(--transition-fast);
>>>>>>> Stashed changes
	}

	.cta-link:hover {
		color: var(--color-action-hover);
	}

	.cta-subtext {
<<<<<<< Updated upstream
		font-family: var(--font-body);
		font-size: var(--text-xs);
		color: var(--text-muted);
		margin: var(--space-sm) 0 0 0;
	}

	/* Happening This Week Section */
	.happening-section {
		margin-top: var(--space-3xl);
		padding-top: var(--space-xl);
		border-top: 1px solid var(--border-primary);
	}

	.section-title {
		font-family: var(--font-body);
		font-size: var(--text-xl);
		font-weight: var(--font-bold);
		color: var(--text);
		margin: 0 0 var(--space-lg) 0;
		letter-spacing: -0.01em;
	}

	/* Trending Topics */
	.trending-topics {
		margin-bottom: var(--space-2xl);
	}

	.topic-chips {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-sm);
	}

	.topic-chip {
		font-family: var(--font-body);
		font-size: var(--text-sm);
		font-weight: var(--font-medium);
		color: var(--text-subtle);
		background: var(--surface-warm);
		padding: 0.375rem 0.75rem;
		border-radius: var(--radius-full);
		transition: all var(--transition-fast);
		cursor: default;
	}

	.topic-chip.trending-up {
		background: rgba(249, 115, 22, 0.1);
		color: var(--action-coral);
	}

	.topic-chip.trending-new {
		background: rgba(34, 197, 94, 0.1);
		color: #16a34a;
	}

	.trend-indicator {
		font-size: var(--text-xs);
		font-weight: var(--font-bold);
		margin-left: 0.25rem;
	}

	/* Upcoming Feed */
	.upcoming-feed {
		margin-top: var(--space-xl);
	}

	.meetings-grid {
		display: grid;
		gap: var(--space-md);
	}

	.loading-upcoming {
		text-align: center;
		padding: var(--space-2xl);
		color: var(--text-muted);
		font-family: var(--font-body);
	}

	.no-upcoming {
		text-align: center;
		padding: var(--space-xl);
		color: var(--text-muted);
		font-family: var(--font-body);
		font-size: var(--text-base);
	}

	@media (min-width: 768px) {
		.meetings-grid {
			grid-template-columns: repeat(2, 1fr);
		}
=======
		font-size: var(--text-sm);
		color: var(--text-muted);
		margin: var(--space-sm) 0 0 0;
>>>>>>> Stashed changes
	}
</style>