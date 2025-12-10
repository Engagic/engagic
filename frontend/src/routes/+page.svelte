<script lang="ts">
	import { goto } from '$app/navigation';
	import { apiClient } from '$lib/api/api-client';
	import type { SearchResult, CityOption, Meeting } from '$lib/api/types';
	import { isSearchSuccess, isSearchAmbiguous } from '$lib/api/types';
	import { generateCityUrl, generateMeetingSlug } from '$lib/utils/utils';
	import { validateSearchQuery } from '$lib/utils/sanitize';
	import { logger } from '$lib/services/logger';
	import Footer from '$lib/components/Footer.svelte';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	let searchQuery = $state('');
	let searchResults: SearchResult | null = $state(null);
	let loading = $state(false);
	let loadingRandom = $state(false);
	let loadingRandomPolicy = $state(false);
	let error = $state('');

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

		// Check for state search first - redirect immediately without API call
		const stateDetection = detectStateSearch(searchQuery);
		if (stateDetection.isState && stateDetection.stateCode) {
			logger.trackEvent('state_search', { query: searchQuery, state: stateDetection.stateCode });
			goto(`/state/${stateDetection.stateCode}`);
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
			}
			// If not found, the message from API will be shown via searchResults
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
						item_count: result.meeting.item_count
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

	// States where the name is also a major city - only match 2-letter codes for these
	const AMBIGUOUS_STATES = new Set(['New York']);

	function detectStateSearch(query: string): { isState: boolean; stateCode?: string; stateName?: string } {
		const trimmed = query.trim();
		const upper = trimmed.toUpperCase();

		// Check if it's a 2-letter state code (always redirect to state)
		if (upper.length === 2 && STATE_CODES[upper]) {
			return { isState: true, stateCode: upper, stateName: STATE_CODES[upper] };
		}

		// Check if it's a full state name (but not ambiguous ones like "New York")
		const stateEntry = Object.entries(STATE_CODES).find(([, name]) =>
			name.toLowerCase() === trimmed.toLowerCase()
		);

		if (stateEntry && !AMBIGUOUS_STATES.has(stateEntry[1])) {
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
				<img src="/icon-64.png" alt="engagic" class="logo-icon" width="64" height="64" />
				<a href="/" class="logo">engagic</a>
			</div>
			<p class="tagline">civic engagement made simple</p>
		</header>

		<section class="value-prop">
			<p class="value-headline">AI summaries of local government meetings</p>
			<p class="value-subtext">
				Your city council decides zoning, taxes, and public safety<br />
				We read the 100-page PDFs so you don't have to
			</p>
			<div class="value-links">
				<a href="/about/general" class="learn-more">How it works</a>
				<span class="link-separator">|</span>
				<a href="/country" class="learn-more">View coverage map</a>
			</div>
		</section>

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

		<a href="/country" class="country-outline" aria-label="View coverage map">
			<svg viewBox="-126 -50 62 28" xmlns="http://www.w3.org/2000/svg">
				<g transform="scale(1,-1)">
					<path d="M-94.818,49.389 L-94.64,48.84 L-93.631,48.671 L-92.61,48.45 L-90.83,48.27 L-89.6,48.01 L-88.378,48.303 L-87.44,47.94 L-86.462,47.553 L-85.652,47.22 L-84.876,46.9 L-84.779,46.637 L-84.544,46.539 L-83.617,46.117 L-83.47,45.995 L-82.551,45.348 L-82.338,44.44 L-81.278,42.209 L-80.247,42.366 L-78.939,42.864 L-78.72,43.625 L-77.738,43.629 L-76.82,43.629 L-76.5,44.018 L-75.318,44.817 L-74.867,45 L-71.405,45.255 L-70.66,45.46 L-70.305,45.915 L-69.237,47.448 L-68.234,47.355 L-67.791,47.066 L-67.791,45.703 L-66.965,44.81 L-68.033,44.325 L-69.06,43.98 L-70.646,43.09 L-70.815,42.865 L-70.495,41.805 L-70.08,41.78 L-71.86,41.32 L-72.876,41.221 L-73.71,40.931 L-74.257,40.474 L-74.906,38.94 L-75.528,39.499 L-75.32,38.96 L-75.948,37.217 L-76.256,36.966 L-76.255,35.551 L-77.398,34.512 L-78.055,33.925 L-79.061,33.494 L-80.301,32.509 L-80.865,32.033 L-81.336,31.44 L-81.491,30.73 L-81.314,30.036 L-80.98,29.18 L-80.056,26.88 L-80.132,25.817 L-80.381,25.206 L-80.68,25.08 L-81.712,25.201 L-82.245,26.73 L-82.705,27.495 L-82.655,28.55 L-83.71,29.937 L-85.109,29.636 L-85.288,29.686 L-85.773,30.153 L-86.4,30.4 L-87.53,30.274 L-88.418,30.385 L-89.181,30.316 L-89.594,30.16 L-89.414,29.894 L-89.778,29.307 L-90.155,29.117 L-90.88,29.149 L-91.627,29.677 L-92.499,29.552 L-93.226,29.784 L-93.848,29.714 L-94.69,29.48 L-95.6,28.739 L-96.594,28.307 L-97.14,27.83 L-97.38,26.69 L-97.33,26.21 L-97.14,25.87 L-97.53,25.84 L-98.24,26.06 L-99.02,26.37 L-99.3,26.84 L-99.52,27.54 L-100.456,28.696 L-100.958,29.381 L-101.662,29.779 L-102.48,29.76 L-103.11,28.97 L-103.94,29.27 L-104.457,29.572 L-104.706,30.122 L-105.037,30.644 L-105.632,31.084 L-106.143,31.4 L-106.508,31.755 L-108.242,31.755 L-108.242,31.342 L-109.035,31.342 L-111.024,31.335 L-113.305,32.039 L-114.815,32.525 L-114.721,32.721 L-115.991,32.612 L-117.128,32.535 L-117.296,33.046 L-117.944,33.621 L-118.411,33.741 L-118.52,34.028 L-119.081,34.078 L-119.439,34.348 L-120.368,34.447 L-120.623,34.609 L-120.744,35.157 L-121.715,36.162 L-122.547,37.552 L-122.512,37.783 L-122.953,38.114 L-123.727,38.952 L-123.865,39.767 L-124.398,40.313 L-124.179,41.142 L-124.214,41.999 L-124.533,42.766 L-124.142,43.708 L-124.021,44.616 L-123.899,45.523 L-124.08,46.865 L-124.396,47.72 L-124.687,48.184 L-123.12,48.04 L-122.587,47.096 L-122.34,47.36 L-122.5,48.18 L-122.84,49 L-120,49 L-117.031,49 L-113,49 L-110.05,49 L-107.05,49 L-104.048,48.999 L-100.65,49 L-97.229,49.001 L-95.159,49 L-94.818,49.389 Z"
						stroke="currentColor"
						stroke-width="0.4"
						fill="currentColor"
						fill-opacity="0.08"
						stroke-linejoin="round"
						stroke-linecap="round"
					/>
				</g>
			</svg>
		</a>
	</div>

	{#if error}
		<div class="error-message" id="search-error" role="alert">
			{error}
		</div>
	{/if}

	{#if searchResults}
		<div class="results-section">
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
				<div class="request-city-cta">
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

	<Footer />
</div>

<style>
	.value-prop {
		text-align: center;
		margin-bottom: 2rem;
	}

	.value-headline {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.25rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0 0 0.5rem 0;
	}

	.value-subtext {
		font-family: system-ui, -apple-system, sans-serif;
		font-size: 1rem;
		color: var(--text-secondary);
		margin: 0 0 0.75rem 0;
		line-height: 1.5;
		max-width: 480px;
		margin-left: auto;
		margin-right: auto;
	}

	.value-links {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
	}

	.learn-more {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
		color: var(--civic-blue);
		text-decoration: none;
	}

	.learn-more:hover {
		text-decoration: underline;
	}

	.link-separator {
		color: var(--text-tertiary);
		font-size: 0.85rem;
	}

	.country-outline {
		display: block;
		width: 100%;
		max-width: 280px;
		margin: 3rem auto 0.5rem;
		color: var(--text-tertiary);
		opacity: 0.6;
		transition: opacity 0.2s ease, transform 0.2s ease;
	}

	.country-outline:hover {
		opacity: 1;
		transform: scale(1.03);
	}

	.country-outline svg {
		width: 100%;
		height: auto;
	}

	@media (max-width: 640px) {
		.country-outline {
			max-width: 240px;
			margin-top: 1rem;
		}
	}

	@media (max-width: 640px) {
		.value-headline {
			font-size: 1.1rem;
		}

		.value-subtext {
			font-size: 0.95rem;
		}
	}

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

	.request-city-cta {
		margin-top: 1.5rem;
		padding: 1.5rem;
		background: var(--surface-secondary);
		border: 2px solid var(--civic-blue);
		border-radius: 11px;
		text-align: center;
	}

	.cta-text {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0 0 0.5rem 0;
	}

	.cta-link {
		display: inline-block;
		color: var(--civic-blue);
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.95rem;
		font-weight: 500;
		text-decoration: underline;
		text-underline-offset: 3px;
	}

	.cta-link:hover {
		opacity: 0.8;
	}

	.cta-subtext {
		font-family: system-ui, -apple-system, sans-serif;
		font-size: 0.85rem;
		color: var(--text-tertiary);
		margin: 0.75rem 0 0 0;
	}
</style>