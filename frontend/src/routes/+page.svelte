<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { apiClient } from '$lib/api/api-client';
	import type { SearchResult, CityOption, Meeting } from '$lib/api/types';
	import { isSearchSuccess, isSearchAmbiguous } from '$lib/api/types';
	import { generateCityUrl, generateMeetingSlug } from '$lib/utils/utils';
	import { validateSearchQuery } from '$lib/utils/sanitize';
	import { logger } from '$lib/services/logger';
	import Footer from '$lib/components/Footer.svelte';
	import StateMetrics from '$lib/components/StateMetrics.svelte';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	let searchQuery = $state('');
	let searchResults: SearchResult | null = $state(null);
	let loading = $state(false);
	let loadingRandom = $state(false);
	let loadingRandomItems = $state(false);
	let error = $state('');
	let currentStatIndex = $state(0);

	// Data now comes from load function - already available on mount
	let analytics = $state(data.analytics);
	let tickerItems = $state(data.tickerItems || []);

	const stats = $derived(analytics ? [
		{ label: 'cities tracked', value: analytics.real_metrics.cities_covered.toLocaleString() },
		{ label: 'meetings summarized', value: analytics.real_metrics.agendas_summarized.toLocaleString() },
		{ label: 'total meetings', value: analytics.real_metrics.meetings_tracked.toLocaleString() }
	] : []);

	onMount(() => {
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

			// If successful and has city info, navigate to city page
			if (isSearchSuccess(result)) {
				const cityUrl = generateCityUrl(result.city_name, result.state);
				logger.trackEvent('search_success', { query: searchQuery, city: result.city_name });
				goto(`/${cityUrl}`);
			} else if (isSearchAmbiguous(result)) {
				logger.trackEvent('search_ambiguous', { query: searchQuery });
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
		goto(`/${cityUrl}`);
	}
	
	async function handleRandomMeeting() {
		loadingRandom = true;
		error = '';

		try {
			const result = await apiClient.getRandomBestMeeting();
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

	async function handleRandomMeetingWithItems() {
		loadingRandomItems = true;
		error = '';

		try {
			const result = await apiClient.getRandomMeetingWithItems();
			if (result.meeting) {
				const banana = result.meeting.banana;

				const meeting: Meeting = {
					id: result.meeting.id,
					banana: banana,
					title: result.meeting.title,
					date: result.meeting.date,
					packet_url: result.meeting.packet_url
				};

				const meetingSlug = generateMeetingSlug(meeting);
				logger.trackEvent('random_meeting_with_items_click', {
					city: banana,
					item_count: result.meeting.item_count
				});

				goto(`/${banana}/${meetingSlug}`);
			}
		} catch (err) {
			logger.error('Random meeting with items failed', err as Error);
			error = 'Failed to load random meeting. Please try again.';
		} finally {
			loadingRandomItems = false;
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

	const stateSearch = $derived(() => {
		if (!searchQuery) return { isState: false };
		return detectStateSearch(searchQuery);
	});
</script>

<svelte:head>
	<title>engagic - civic engagement made simple</title>
	<meta name="description" content="Find your local government meetings and agendas" />
</svelte:head>

{#if tickerItems.length > 0}
	<div class="news-ticker">
		<div class="ticker-content">
			{#each [...tickerItems, ...tickerItems] as item}
				<a href={item.url} class="ticker-item">
					<span class="ticker-city">{item.city}</span>
					<span class="ticker-separator">•</span>
					<span class="ticker-date">{item.date}</span>
					<span class="ticker-separator">•</span>
					<span class="ticker-excerpt">{item.excerpt}</span>
				</a>
			{/each}
		</div>
	</div>
{/if}

<div class="container">
	<div class="main-content">
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
			disabled={loading || loadingRandom}
			aria-label="Search for local government meetings"
			aria-invalid={!!error}
			aria-describedby={error ? "search-error" : undefined}
		/>
		<button
			class="search-button"
			onclick={handleSearch}
			disabled={loading || loadingRandom || loadingRandomItems || !searchQuery.trim()}
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
				disabled={loading || loadingRandom || loadingRandomItems}
			>
				{loadingRandom ? 'Loading...' : '🎲 Random Meeting'}
			</button>

			<button
				class="random-button random-items"
				onclick={handleRandomMeetingWithItems}
				disabled={loading || loadingRandom || loadingRandomItems}
			>
				{loadingRandomItems ? 'Loading...' : '🛸 Meeting with Items'}
			</button>
		</div>
	</div>

	{#if error}
		<div class="error-message" id="search-error" role="alert">
			{error}
		</div>
	{/if}

	{#if searchResults}
		<div class="results-section">
			{#if stateSearch().isState && searchResults.success === false && searchResults.ambiguous}
				<StateMetrics stateCode={stateSearch().stateCode!} stateName={stateSearch().stateName} />
			{/if}

			{#if searchResults.success === false && searchResults.ambiguous && searchResults.city_options}
				<div class="ambiguous-cities">
					<div class="ambiguous-message">
						{@html searchResults.message}
					</div>
					<div class="city-options">
						{#each searchResults.city_options as cityOption}
							<div class="city-option-row">
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
				<div class="error-message">
					{searchResults.message || 'Search failed'}
				</div>
			{/if}
		</div>
	{:else if loading}
		<div class="loading">
			Searching for meetings...
		</div>
	{/if}
	</div>

	<Footer />
</div>

<style>
	.logo-container {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 1rem;
		margin-bottom: 0.5rem;
	}

	.logo-icon {
		width: 64px;
		height: 64px;
		border-radius: 16px;
		box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
	}

	@media (max-width: 640px) {
		.logo-icon {
			width: 48px;
			height: 48px;
			border-radius: 12px;
		}
	}
</style>