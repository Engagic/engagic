<script lang="ts">
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import { searchMeetings, getCachedSummary, type SearchResult, type Meeting, type CachedSummary } from '$lib/api';
	import { parseCityUrl } from '$lib/utils';

	let city_url = $page.params.city_url;
	let meeting_slug = $page.params.meeting_slug;
	let searchResults: SearchResult | null = $state(null);
	let selectedMeeting: Meeting | null = $state(null);
	let cachedSummary: CachedSummary | null = $state(null);
	let loading = $state(true);
	let loadingSummary = $state(false);
	let error = $state('');

	onMount(async () => {
		await loadMeetingData();
	});

	async function loadMeetingData() {
		loading = true;
		error = '';
		
		try {
			// Parse the city URL
			const parsed = parseCityUrl(city_url);
			if (!parsed) {
				throw new Error('Invalid city URL format');
			}
			
			// Search by city name and state to get meetings
			const searchQuery = `${parsed.cityName}, ${parsed.state}`;
			const result = await searchMeetings(searchQuery);
			searchResults = result;
			
			if (result.success && result.meetings) {
				// Find the meeting that matches our slug
				const meeting = findMeetingBySlug(result.meetings, meeting_slug);
				if (meeting) {
					selectedMeeting = meeting;
					await loadCachedSummary(meeting);
				} else {
					error = 'Meeting not found';
				}
			} else {
				error = result.message || 'Failed to load city meetings';
			}
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load meeting';
		} finally {
			loading = false;
		}
	}

	async function loadCachedSummary(meeting: Meeting) {
		if (!searchResults?.city_slug) return;
		
		loadingSummary = true;
		cachedSummary = null;

		try {
			const result = await getCachedSummary(meeting, searchResults.city_slug);
			if (result.success && result.cached && result.summary) {
				cachedSummary = result;
			} else {
				// No cached summary available
				cachedSummary = null;
			}
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load summary';
		} finally {
			loadingSummary = false;
		}
	}

	function findMeetingBySlug(meetings: Meeting[], slug: string): Meeting | null {
		// Basic slug matching - in a real app you'd want more sophisticated matching
		// For now, just find the first meeting that could plausibly match the slug
		return meetings.find(meeting => {
			const title = (meeting.title || meeting.meeting_name || '').toLowerCase();
			const dateStr = meeting.meeting_date || meeting.start || '';
			
			// Check if slug contains parts of the title or date
			const slugParts = slug.split('_');
			return slugParts.some(part => title.includes(part) || dateStr.includes(part));
		}) || meetings[0] || null; // Fallback to first meeting
	}
</script>

<svelte:head>
	<title>{selectedMeeting?.title || selectedMeeting?.meeting_name || 'Meeting'} - engagic</title>
	<meta name="description" content="City council meeting agenda and summary" />
</svelte:head>

<div class="container">
	<div class="main-content">
		<header class="header">
			<a href="/" class="logo">engagic</a>
			<p class="tagline">civic engagement made simple</p>
		</header>

	<div class="navigation">
		<a href="/" class="nav-link">← Home</a>
		<span class="nav-separator">•</span>
		<a href="/{city_url}" class="nav-link">
			{searchResults?.city_name ? `${searchResults.city_name}, ${searchResults.state}` : 'City'}
		</a>
		<span class="nav-separator">•</span>
		<span class="nav-current">Meeting</span>
	</div>

	{#if loading}
		<div class="loading">
			Loading meeting...
		</div>
	{:else if error}
		<div class="error-message">
			{error}
		</div>
	{:else if selectedMeeting}
		<div class="meeting-detail">
			<div class="meeting-header">
				<h1 class="meeting-title">{selectedMeeting.title || selectedMeeting.meeting_name}</h1>
				<div class="meeting-date">
					{selectedMeeting.start || selectedMeeting.meeting_date}
				</div>
			</div>
			
			{#if loadingSummary}
				<div class="processing-status">Checking for summary...</div>
			{:else if cachedSummary}
				<div class="meeting-summary">
					{cachedSummary.summary}
				</div>
			{:else}
				<div class="no-summary">
					<p>Working on it, please wait!</p>
					<p>We're processing this meeting in the background. Check back in a few minutes.</p>
				</div>
			{/if}
		</div>
	{/if}
	</div>

	<footer class="footer">
		<a href="https://github.com/Engagic/engagic" class="github-link" target="_blank" rel="noopener">
			<svg class="github-icon" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
				<path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
			</svg>
			All your code is open source and readily auditable. made with love and rizz
		</a>
	</footer>
</div>

<style>
	.navigation {
		margin-bottom: 2rem;
		color: var(--civic-gray);
	}

	.nav-link {
		color: var(--civic-blue);
		text-decoration: none;
		font-weight: 500;
	}

	.nav-link:hover {
		text-decoration: underline;
	}

	.nav-separator {
		margin: 0 0.5rem;
	}

	.nav-current {
		font-weight: 500;
	}

	.meeting-detail {
		padding: 2rem;
		background: var(--civic-white);
		border-radius: 8px;
		border: 1px solid var(--civic-border);
	}

	.meeting-header {
		margin-bottom: 2rem;
	}

	.meeting-title {
		font-size: 1.8rem;
		color: var(--civic-dark);
		margin: 0 0 0.5rem 0;
		font-weight: 600;
	}

	.meeting-date {
		color: var(--civic-gray);
		font-size: 1.1rem;
	}

	.meeting-summary {
		line-height: 1.8;
		white-space: pre-wrap;
		font-size: 1rem;
	}

	.no-summary {
		text-align: center;
		padding: 3rem 2rem;
		color: var(--civic-gray);
		background: #f8fafc;
		border-radius: 8px;
		border: 1px solid #e2e8f0;
	}

	.no-summary p:first-child {
		font-size: 1.2rem;
		font-weight: 600;
		color: var(--civic-blue);
		margin-bottom: 0.5rem;
	}

	.no-summary p:last-child {
		font-size: 0.95rem;
		margin: 0;
	}

	@media (max-width: 640px) {
		.meeting-title {
			font-size: 1.4rem;
		}
		
		.meeting-detail {
			padding: 1rem;
		}
	}
</style>