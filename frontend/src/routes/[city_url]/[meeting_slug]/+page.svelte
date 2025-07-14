<script lang="ts">
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import { searchMeetings, type SearchResult, type Meeting } from '$lib/api';
	import { parseCityUrl, generateMeetingSlug } from '$lib/utils';

	let city_url = $page.params.city_url;
	let meeting_slug = $page.params.meeting_slug;
	let searchResults: SearchResult | null = $state(null);
	let selectedMeeting: Meeting | null = $state(null);
	let loading = $state(true);
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
				} else {
					error = 'Meeting not found';
				}
			} else {
				error = result.message || 'Failed to load city meetings';
			}
		} catch (err) {
			console.error('Failed to load meeting:', err);
			error = 'No agendas posted yet, please come back later! Packets are typically posted within 48 hours of the meeting date';
		} finally {
			loading = false;
		}
	}


	function findMeetingBySlug(meetings: Meeting[], slug: string): Meeting | null {
		// Find meeting where generated slug matches the URL slug
		return meetings.find(meeting => {
			const generatedSlug = generateMeetingSlug(meeting);
			return generatedSlug === slug;
		}) || null;
	}

	function formatMeetingDate(dateString: string): string {
		// Handle date strings with time like "2025-09-09 9:30 AM"
		// Extract just the date part
		const datePart = dateString.split(' ')[0];
		
		// Parse the date components manually to avoid timezone issues
		const [year, month, day] = datePart.split('-').map(num => parseInt(num, 10));
		
		if (isNaN(year) || isNaN(month) || isNaN(day)) {
			// Fallback for unparseable dates
			return dateString;
		}
		
		const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
		const monthName = months[month - 1]; // month is 1-based in the date string
		const suffix = day === 1 || day === 21 || day === 31 ? 'st' : 
					  day === 2 || day === 22 ? 'nd' : 
					  day === 3 || day === 23 ? 'rd' : 'th';
		return `${monthName} ${day}${suffix}, ${year}`;
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

	<div class="city-header">
		<a href="/{city_url}" class="back-link">← Back to {searchResults?.city_name || 'city'} meetings</a>
	</div>

	<div class="navigation">
		<a href="/" class="nav-link">← Home</a>
		<span class="nav-separator">•</span>
		<a href="/{city_url}" class="nav-link">
			{searchResults?.city_name ? `${searchResults.city_name}, ${searchResults.state}` : 'City'}
		</a>
		<span class="nav-separator">•</span>
		<span class="nav-current">Meeting</span>
	</div>

	{#if selectedMeeting?.packet_url}
		{@const packetUrl = Array.isArray(selectedMeeting.packet_url) 
			? selectedMeeting.packet_url[0] 
			: selectedMeeting.packet_url}
		<div class="packet-url-box">
			<div class="packet-url-content">
				<span class="packet-url-label">Summarized through the Anthropic API from this meeting-packet URL:</span>
				<a href={packetUrl} target="_blank" rel="noopener noreferrer" class="packet-url-link">
					{packetUrl}
				</a>
			</div>
		</div>
	{/if}

	{#if loading}
		<div class="loading">
			Loading meeting...
		</div>
	{:else if error}
		<div class="{error.includes('Packets not posted yet') ? 'info-message' : 'error-message'}">
			{error}
		</div>
	{:else if selectedMeeting}
		<div class="meeting-detail">
			<div class="meeting-header">
				<h1 class="meeting-title">{selectedMeeting.title || selectedMeeting.meeting_name}</h1>
				<div class="meeting-date">
					{formatMeetingDate(selectedMeeting.start || selectedMeeting.meeting_date)}
				</div>
			</div>
			
			{#if selectedMeeting.processed_summary}
				<div class="meeting-summary">
					{selectedMeeting.processed_summary}
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

	.packet-url-box {
		margin: 1.5rem 0;
		padding: 1rem;
		background: #f0f9ff;
		border: 1px solid #bae6fd;
		border-radius: 8px;
	}

	.packet-url-content {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		flex-wrap: wrap;
	}

	.packet-url-label {
		font-weight: 500;
		color: var(--civic-dark);
		white-space: nowrap;
	}

	.packet-url-link {
		color: var(--civic-blue);
		text-decoration: none;
		word-break: break-all;
		font-size: 0.9rem;
	}

	.packet-url-link:hover {
		text-decoration: underline;
	}

	.city-header {
		margin-bottom: 1rem;
	}

	.back-link {
		display: inline-block;
		color: var(--civic-blue);
		text-decoration: none;
		font-weight: 500;
		font-size: 1.1rem;
		padding: 0.5rem 0;
	}

	.back-link:hover {
		text-decoration: underline;
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
		font-family: Georgia, 'Times New Roman', Times, serif;
		line-height: 1.8;
		font-size: 1.05rem;
		color: #374151;
	}
	
	/* Markdown element styles */
	.meeting-summary :global(h1),
	.meeting-summary :global(h2),
	.meeting-summary :global(h3),
	.meeting-summary :global(h4) {
		font-family: 'IBM Plex Mono', monospace;
		color: var(--civic-dark);
		margin-top: 1.5rem;
		margin-bottom: 0.75rem;
		font-weight: 600;
	}
	
	.meeting-summary :global(h1) { font-size: 1.5rem; }
	.meeting-summary :global(h2) { font-size: 1.3rem; }
	.meeting-summary :global(h3) { font-size: 1.15rem; }
	.meeting-summary :global(h4) { font-size: 1.05rem; }
	
	.meeting-summary :global(h1:first-child),
	.meeting-summary :global(h2:first-child),
	.meeting-summary :global(h3:first-child),
	.meeting-summary :global(h4:first-child) {
		margin-top: 0;
	}
	
	.meeting-summary :global(p) {
		margin-bottom: 1rem;
	}
	
	.meeting-summary :global(ul),
	.meeting-summary :global(ol) {
		margin: 1rem 0;
		padding-left: 2rem;
	}
	
	.meeting-summary :global(li) {
		margin-bottom: 0.5rem;
	}
	
	.meeting-summary :global(li > ul),
	.meeting-summary :global(li > ol) {
		margin-top: 0.5rem;
		margin-bottom: 0.5rem;
	}
	
	.meeting-summary :global(strong) {
		font-weight: 600;
		color: var(--civic-dark);
	}
	
	.meeting-summary :global(em) {
		font-style: italic;
	}
	
	.meeting-summary :global(code) {
		font-family: 'IBM Plex Mono', monospace;
		background: #f3f4f6;
		padding: 0.1rem 0.3rem;
		border-radius: 3px;
		font-size: 0.95em;
	}
	
	.meeting-summary :global(blockquote) {
		border-left: 3px solid var(--civic-blue);
		padding-left: 1rem;
		margin: 1rem 0;
		color: #6b7280;
		font-style: italic;
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