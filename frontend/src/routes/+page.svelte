<script lang="ts">
	import { goto } from '$app/navigation';
	import { apiClient } from '$lib/api/api-client';
	import SeoHead from '$lib/components/SeoHead.svelte';
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
			} else {
				// City not found
				logger.trackEvent('search_not_found', { query: searchQuery });
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

<SeoHead
	title="engagic - Help shape your city"
	description="Stay informed. Make your voice heard. AI summaries of local government meetings and civic participation information."
	url="https://engagic.org"
/>

<div class="container">
	<header class="header">
		<p class="tagline">Know what your city council is deciding — before they decide it.</p>
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

		{#if searchResults && !searchResults.success && !searchResults.ambiguous}
			<div class="not-found-inline">
				<p class="not-found-message">{searchResults.message}</p>
				<p class="not-found-cta">
					We don't cover this city yet — but we're growing.
					<a href="/signup">Create an account</a> and request it, and we'll prioritize cities with active watchers.
				</p>
			</div>
		{/if}

		{#if searchResults && isSearchAmbiguous(searchResults)}
			<div class="ambiguous-inline">
				<div class="ambiguous-message">
					{@html searchResults.message}
				</div>
				<div class="city-options">
					{#each searchResults.city_options as cityOption}
						<button
							class="city-option"
							onclick={() => handleCityOptionClick(cityOption)}
						>
							{cityOption.display_name}
						</button>
					{/each}
				</div>
			</div>
		{/if}

		{#if loading}
			<div class="loading-inline">Searching...</div>
		{/if}

		{#if error}
			<div class="error-inline" id="search-error" role="alert">{error}</div>
		{/if}

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

	<section class="preview-section">
		<p class="preview-label">What you'll see</p>
		<div class="preview-item-expanded">
			<div class="preview-item-header">
				<div class="preview-item-title-row">
					<span class="preview-item-number">5.</span>
					<h3 class="preview-item-title">Affordable Housing Overlay District</h3>
				</div>
				<div class="preview-item-badges">
					<span class="preview-badge preview-badge-matter">ORD-2025-0142</span>
					<span class="preview-tag">Housing</span>
					<span class="preview-tag">Zoning</span>
				</div>
			</div>
			<div class="preview-summary">
				<p>This ordinance creates a new Affordable Housing Overlay District that would allow <strong>increased building density</strong> for residential projects that include at least 20% affordable units.</p>
				<p>The overlay would apply to three neighborhoods currently zoned single-family: Westbrook, Cedar Hills, and Riverside Commons. Developers opting in could build up to <strong>4 stories</strong> instead of the current 2-story limit.</p>
				<p><strong>Key provisions:</strong></p>
				<ul>
					<li>Affordable units must remain price-controlled for a minimum of <strong>30 years</strong></li>
					<li>Projects must include at least 10% units accessible to households earning below 50% of area median income</li>
					<li>Developers receive expedited permitting and reduced impact fees in exchange for affordability commitments</li>
				</ul>
				<p>The Planning Commission voted 5-2 to recommend approval. Two commissioners dissented, citing concerns about <strong>infrastructure capacity</strong> in the affected neighborhoods. Public comment period closes February 28.</p>
			</div>
		</div>
	</section>

	<section class="bottom-links">
		<div class="bottom-links-row">
			<a href="/about/general" class="bottom-link">How it works</a>
			<span class="link-separator">|</span>
			<a href="/country" class="bottom-link">Coverage map</a>
			<span class="link-separator">|</span>
			<a href="/about/donate" class="bottom-link">Support Engagic</a>
		</div>
		<p class="bottom-note">Open-source and community-driven</p>
	</section>

	<Footer />
</div>

<style>
	/* Extracted from app.css - homepage-specific styles */
	.header {
		text-align: center;
		margin-bottom: 2rem;
	}

	.tagline {
		font-family: 'IBM Plex Sans', sans-serif;
		color: var(--text-secondary);
		font-size: 0.95rem;
		line-height: 1.5;
		margin-bottom: 1rem;
		max-width: 400px;
		margin-left: auto;
		margin-right: auto;
	}

	.search-section {
		margin-bottom: 3rem;
	}

	.search-input {
		width: 100%;
		padding: 1.4rem;
		font-size: 1.1rem;
		border: 2px solid var(--border-primary);
		border-radius: var(--radius-lg);
		background: var(--surface-primary);
		color: var(--text-primary);
		transition: all var(--transition-slow);
		box-shadow: 0 2px 8px var(--shadow-sm);
	}

	.search-input:focus {
		outline: none;
		border-color: var(--civic-blue);
		box-shadow: 0 4px 16px var(--shadow-lg);
		transform: translateY(-1px);
	}

	.search-button {
		margin-top: 1rem;
		width: 100%;
		padding: 1rem;
		font-size: 1rem;
		font-family: 'IBM Plex Mono', monospace;
		background: var(--civic-blue);
		color: var(--civic-white);
		border: none;
		border-radius: var(--radius-md);
		cursor: pointer;
		transition: all var(--transition-fast);
		box-shadow: 0 4px 12px var(--shadow-lg);
	}

	.search-button:hover {
		background: var(--civic-accent);
		transform: translateY(-2px);
		box-shadow: 0 6px 20px var(--shadow-lg);
	}

	.search-button:active {
		transform: translateY(0);
		box-shadow: inset 0 2px 4px var(--shadow-md);
	}

	.search-button:disabled {
		background: var(--civic-gray);
		cursor: not-allowed;
		transform: none;
		box-shadow: 0 2px 8px var(--shadow-sm);
		opacity: 0.6;
	}

	.random-buttons {
		display: flex;
		gap: 1rem;
		width: 100%;
		margin-top: 1.5rem;
	}

	.random-button {
		flex: 1;
		padding: 1rem;
		font-size: 1rem;
		font-family: 'IBM Plex Mono', monospace;
		color: var(--civic-white);
		border: none;
		border-radius: var(--radius-lg);
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.random-meeting {
		background: var(--random-meeting-bg);
		box-shadow: 0 4px 12px var(--shadow-sm);
	}

	.random-meeting:hover {
		background: var(--random-meeting-hover);
		transform: translateY(-2px);
		box-shadow: 0 6px 20px var(--shadow-md);
	}

	.random-policy {
		background: var(--random-policy-bg);
		box-shadow: 0 4px 12px var(--shadow-sm);
	}

	.random-policy:hover {
		background: var(--random-policy-hover);
		transform: translateY(-2px);
		box-shadow: 0 6px 20px var(--shadow-md);
	}

	.random-button:disabled {
		opacity: 0.7;
		cursor: not-allowed;
		transform: none;
		box-shadow: 0 2px 8px var(--shadow-sm);
	}

	.link-separator {
		color: var(--civic-gray);
		font-size: 0.85rem;
		opacity: 0.5;
	}

	/* Preview section */
	.preview-section {
		margin-top: 2rem;
		margin-bottom: 2rem;
	}

	.preview-label {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--civic-gray);
		text-transform: uppercase;
		letter-spacing: 0.5px;
		margin: 0 0 0.75rem 0;
		text-align: center;
		opacity: 0.7;
	}

	.preview-item-expanded {
		background: var(--surface-primary);
		border: 1px solid var(--border-primary);
		border-left: 4px solid var(--item-summary-border);
		border-radius: var(--radius-lg);
		padding: 1.25rem 1.5rem;
		box-shadow: 0 2px 8px var(--shadow-sm);
	}

	.preview-item-header {
		margin-bottom: 1rem;
	}

	.preview-item-title-row {
		display: flex;
		align-items: baseline;
		gap: 0.5rem;
		margin-bottom: 0.5rem;
	}

	.preview-item-number {
		color: var(--civic-gray);
		font-size: 1rem;
		font-weight: 500;
		flex-shrink: 0;
	}

	.preview-item-title {
		font-family: 'IBM Plex Sans', sans-serif;
		font-size: 1.05rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
		line-height: 1.4;
	}

	.preview-item-badges {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		flex-wrap: wrap;
	}

	.preview-badge {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.7rem;
		font-weight: 700;
		padding: 0.2rem 0.6rem;
		border-radius: var(--radius-lg);
		letter-spacing: 0.3px;
	}

	.preview-badge-matter {
		background: var(--badge-matter-bg);
		color: var(--badge-matter-text);
		border: 1.5px solid var(--badge-matter-border);
	}

	.preview-tag {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.7rem;
		padding: 0.25rem 0.55rem;
		background: var(--topic-tag-bg);
		color: var(--topic-tag-text);
		border: 1px solid var(--topic-tag-border);
		border-radius: var(--radius-xs);
		font-weight: 500;
	}

	.preview-summary {
		font-family: 'IBM Plex Sans', sans-serif;
		font-size: 0.95rem;
		line-height: 1.7;
		color: var(--text-primary);
		border-top: 1px solid var(--border-primary);
		padding-top: 1rem;
	}

	.preview-summary p {
		margin: 0.75rem 0;
	}

	.preview-summary p:first-child {
		margin-top: 0;
	}

	.preview-summary p:last-child {
		margin-bottom: 0;
	}

	.preview-summary strong {
		font-weight: 700;
		color: var(--text-primary);
	}

	.preview-summary ul {
		margin: 0.75rem 0;
		padding-left: 1.25rem;
	}

	.preview-summary li {
		margin: 0.35rem 0;
	}

	/* Bottom links */
	.bottom-links {
		text-align: center;
		padding: 1.5rem 0 2rem;
		margin-top: 1rem;
		border-top: 1px solid var(--border-primary);
	}

	.bottom-links-row {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		margin-bottom: 0.5rem;
	}

	.bottom-link {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
		color: var(--civic-blue);
		text-decoration: none;
	}

	.bottom-link:hover {
		text-decoration: underline;
	}

	.bottom-note {
		font-size: 0.85rem;
		color: var(--civic-gray);
		margin: 0;
		opacity: 0.7;
	}

	.not-found-inline {
		margin-top: 1.25rem;
		padding: 1.25rem;
		background: var(--surface-secondary);
		border-left: 3px solid var(--civic-blue);
		border-radius: var(--radius-md);
		text-align: left;
	}

	.not-found-message {
		font-family: 'IBM Plex Sans', sans-serif;
		font-size: 1rem;
		color: var(--text-primary);
		margin: 0 0 0.5rem 0;
	}

	.not-found-cta {
		font-family: 'IBM Plex Sans', sans-serif;
		font-size: 0.95rem;
		color: var(--text-secondary);
		margin: 0;
	}

	.not-found-cta a {
		color: var(--civic-blue);
		text-decoration: underline;
		text-underline-offset: 2px;
	}

	.not-found-cta a:hover {
		color: var(--civic-accent);
	}

	.ambiguous-inline {
		margin-top: 1.25rem;
		padding: 1.25rem;
		background: var(--surface-secondary);
		border-left: 3px solid var(--civic-blue);
		border-radius: var(--radius-md);
		text-align: left;
	}

	.ambiguous-inline .ambiguous-message {
		font-family: 'IBM Plex Sans', sans-serif;
		font-size: 1rem;
		color: var(--text-primary);
		margin: 0 0 1rem 0;
		line-height: 1.5;
	}

	.ambiguous-inline .city-options {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.ambiguous-inline .city-option {
		padding: 0.5rem 1rem;
		background: var(--surface-primary);
		border: 1px solid var(--border-primary);
		border-radius: var(--radius-sm);
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
		font-weight: 500;
		color: var(--civic-blue);
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.ambiguous-inline .city-option:hover {
		background: var(--civic-blue);
		color: white;
		border-color: var(--civic-blue);
	}

	.loading-inline {
		margin-top: 1rem;
		padding: 0.75rem 1rem;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
		color: var(--text-secondary);
		text-align: center;
	}

	.error-inline {
		margin-top: 1rem;
		padding: 0.75rem 1rem;
		background: var(--alert-bg);
		border-left: 3px solid var(--alert-icon);
		border-radius: var(--radius-sm);
		font-size: 0.9rem;
		color: var(--alert-text);
	}

	@media (max-width: 640px) {
		.header {
			margin-bottom: 1.5rem;
		}

		.tagline {
			font-size: 0.85rem;
		}

		.search-input {
			padding: 1rem;
			font-size: 1rem;
		}

		.search-button {
			padding: 0.85rem;
			font-size: 0.95rem;
		}

		.random-buttons {
			flex-direction: column;
		}

		.random-button {
			padding: 0.85rem;
			font-size: 0.95rem;
		}

		.preview-item-expanded {
			padding: 1rem 1.25rem;
		}

		.preview-item-title {
			font-size: 0.95rem;
		}

		.preview-summary {
			font-size: 0.9rem;
		}

		.bottom-links-row {
			flex-wrap: wrap;
		}
	}
</style>