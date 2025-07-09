<script lang="ts">
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import { searchMeetings, processAgenda, type SearchResult, type Meeting, type ProcessResult } from '$lib/api';
	import { parseCityUrl } from '$lib/utils';

	let city_url = $page.params.city_url;
	let meeting_slug = $page.params.meeting_slug;
	let searchResults: SearchResult | null = $state(null);
	let selectedMeeting: Meeting | null = $state(null);
	let processingResult: ProcessResult | null = $state(null);
	let loading = $state(true);
	let processingMeeting = $state(false);
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
					await processSelectedMeeting(meeting);
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

	async function processSelectedMeeting(meeting: Meeting) {
		if (!searchResults?.city_slug) return;
		
		processingMeeting = true;
		processingResult = null;

		try {
			const result = await processAgenda(meeting, searchResults.city_slug);
			processingResult = result;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Processing failed';
		} finally {
			processingMeeting = false;
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
			
			{#if processingMeeting}
				<div class="processing-status">Processing agenda packet...</div>
			{/if}
			
			{#if processingResult}
				<div class="meeting-summary">
					{processingResult.summary}
				</div>
				<div class="processing-status">
					{processingResult.cached ? 'Cached result' : `Processed in ${processingResult.processing_time_seconds}s`}
				</div>
			{/if}
		</div>
	{/if}
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

	@media (max-width: 640px) {
		.meeting-title {
			font-size: 1.4rem;
		}
		
		.meeting-detail {
			padding: 1rem;
		}
	}
</style>