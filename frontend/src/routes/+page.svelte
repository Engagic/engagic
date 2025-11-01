<script lang="ts">
	import { goto } from '$app/navigation';
	import { apiClient } from '$lib/api/api-client';
	import type { SearchResult, CityOption, Meeting } from '$lib/api/types';
	import { isSearchSuccess, isSearchAmbiguous } from '$lib/api/types';
	import { generateCityUrl, generateMeetingSlug } from '$lib/utils/utils';
	import { validateSearchQuery } from '$lib/utils/sanitize';
	import { logger } from '$lib/services/logger';
	import Footer from '$lib/components/Footer.svelte';
	import { getAnalytics, type AnalyticsData } from '$lib/api/index';
	import { onMount } from 'svelte';

	let searchQuery = $state('');
	let searchResults: SearchResult | null = $state(null);
	let loading = $state(false);
	let loadingRandom = $state(false);
	let loadingRandomItems = $state(false);
	let error = $state('');
	let analytics: AnalyticsData | null = $state(null);
	let currentStatIndex = $state(0);
	let tickerItems: Array<{city: string, date: string, excerpt: string, url: string}> = $state([]);

	const stats = $derived(analytics ? [
		{ label: 'cities tracked', value: analytics.real_metrics.cities_covered.toLocaleString() },
		{ label: 'meetings summarized', value: analytics.real_metrics.agendas_summarized.toLocaleString() },
		{ label: 'total meetings', value: analytics.real_metrics.meetings_tracked.toLocaleString() }
	] : []);

	function extractExcerpt(summary: string, preferMiddle: boolean = true): string {
		if (!summary) return '';

		// Remove markdown headers, bold, and common boilerplate
		let cleaned = summary
			.replace(/#{1,6}\s+/g, '')
			.replace(/\*\*/g, '')
			.replace(/\*/g, '')
			.replace(/Here's a summary[^:]*:/gi, '')
			.replace(/Here is a summary[^:]*:/gi, '')
			.replace(/This summary[^:]*:/gi, '')
			.replace(/This is a summary[^:]*:/gi, '')
			.replace(/Summary of[^:]*:/gi, '')
			.replace(/Key Agenda Items/gi, '')
			.replace(/Date:[^Time]*/gi, '')
			.replace(/Time:[^Location]*/gi, '')
			.replace(/Location:[^\n]*/gi, '')
			.replace(/Meeting Summary[^-]*-[^-]*-[^T]*/gi, '')
			.trim();

		// Split into sentences
		const sentences = cleaned.split(/[.!?]+/).filter(s => s.trim().length > 30);

		if (sentences.length === 0) {
			return cleaned.substring(0, 150);
		}

		// Score sentences to find the juiciest one
		const scoredSentences = sentences.map((sentence, idx) => {
			let score = 0;

			// Prefer middle sentences (skip intro, skip outro)
			if (idx > 0 && idx < sentences.length - 1) score += 10;

			// Look for dollar amounts
			if (/\$[\d,]+/.test(sentence)) score += 15;

			// Look for action words
			if (/(proposed|approved|amendment|ordinance|agreement|contract|budget|allocate|establish|require)/i.test(sentence)) score += 10;

			// Look for numbers (percentages, counts)
			if (/\d+%|\d+ (units|homes|acres|projects)/.test(sentence)) score += 8;

			// Penalize very short sentences
			if (sentence.length < 50) score -= 5;

			// Prefer longer, detailed sentences
			if (sentence.length > 100) score += 5;

			return { sentence, score, idx };
		});

		// Get highest scoring sentence
		scoredSentences.sort((a, b) => b.score - a.score);
		const excerpt = scoredSentences[0].sentence.trim();

		// Truncate if too long
		return excerpt.length > 200 ? excerpt.substring(0, 197) + '...' : excerpt;
	}

	function formatCityName(banana: string): string {
		// Remove state code (last 2 chars)
		const cityPart = banana.substring(0, banana.length - 2);

		// Insert spaces before capital letters and capitalize first letter of each word
		return cityPart
			.replace(/([A-Z])/g, ' $1')
			.trim()
			.split(' ')
			.map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
			.join(' ');
	}

	onMount(async () => {
		try {
			analytics = await getAnalytics();
		} catch (err) {
			console.error('Failed to load analytics:', err);
		}

		// Fetch random meetings for ticker - mix both types for variety
		try {
			const items = [];
			for (let i = 0; i < 15; i++) {
				// Alternate between item-based and general meetings
				const useItems = i % 2 === 0;
				const result = useItems
					? await apiClient.getRandomMeetingWithItems()
					: await apiClient.getRandomBestMeeting();

				if (result.meeting) {
					const banana = result.meeting.banana;
					const stateMatch = banana.match(/([A-Z]{2})$/);
					if (stateMatch) {
						const state = stateMatch[1];
						const cityName = formatCityName(banana);

						const date = new Date(result.meeting.date).toLocaleDateString('en-US', {
							month: 'short',
							day: 'numeric',
							year: 'numeric'
						});

						let excerpt = '';

						// Prefer item summaries (they're more specific and juicy)
						if (result.meeting.items && result.meeting.items.length > 0) {
							const itemsWithSummaries = result.meeting.items.filter(item => item.summary);
							if (itemsWithSummaries.length > 0) {
								// Pick a random item from this meeting
								const randomItem = itemsWithSummaries[Math.floor(Math.random() * itemsWithSummaries.length)];
								excerpt = extractExcerpt(randomItem.summary);
							}
						}

						// Fall back to meeting summary if no items
						if (!excerpt && result.meeting.summary) {
							excerpt = extractExcerpt(result.meeting.summary);
						}

						// Generate meeting slug
						const meetingSlug = generateMeetingSlug(result.meeting);
						const url = `/${banana}/${meetingSlug}`;

						if (excerpt && excerpt.length > 20) {
							items.push({
								city: `${cityName}, ${state}`,
								date: date,
								excerpt: excerpt,
								url: url
							});
						}
					}
				}
			}
			tickerItems = items;
		} catch (err) {
			console.error('Failed to load ticker items:', err);
		}

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
			<a href="/" class="logo">engagic</a>
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