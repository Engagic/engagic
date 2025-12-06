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
			<a href="/about/general" class="learn-more">How it works</a>
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

	.learn-more {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
		color: var(--civic-blue);
		text-decoration: none;
	}

	.learn-more:hover {
		text-decoration: underline;
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