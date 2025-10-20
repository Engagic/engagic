<script lang="ts">
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import { searchMeetings, type SearchResult, type Meeting } from '$lib/api/index';
	import { parseCityUrl, generateMeetingSlug } from '$lib/utils/utils';
	import Footer from '$lib/components/Footer.svelte';

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
				error = 'message' in result ? result.message : 'Failed to load city meetings';
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

	function processSummary(rawSummary: string): Array<{type: 'header' | 'text', content: string}> {
		if (!rawSummary) return [];
		
		// Remove ugly document headers
		let cleaned = rawSummary
			.replace(/=== DOCUMENT \d+ ===/g, '')
			.replace(/--- SECTION \d+ SUMMARY ---/g, '')
			.replace(/Here's a concise summary of the[^:]*:/gi, '')
			.replace(/Here's a summary of the[^:]*:/gi, '')
			.replace(/Here's the key points[^:]*:/gi, '')
			.replace(/Here's a structured analysis[^:]*:/gi, '')
			.replace(/Summary of the[^:]*:/gi, '')
			.trim();
		
		// Clean up extra whitespace
		cleaned = cleaned
			.replace(/\n{3,}/g, '\n\n')
			.replace(/^\s*\n+/, '')
			.trim();
		
		// Process into structured content
		const lines = cleaned.split('\n');
		const processed = [];
		let currentText = '';
		
		for (const line of lines) {
			// Check if this line has bold markdown header
			const headerMatch = line.match(/^\*\*([^*]+):\*\*$/);
			if (headerMatch) {
				// Save any accumulated text first
				if (currentText.trim()) {
					processed.push({ type: 'text' as const, content: currentText.trim() });
					currentText = '';
				}
				// Add the header
				processed.push({ type: 'header' as const, content: headerMatch[1] });
			} else {
				// Accumulate regular text (with light markdown cleanup)
				let cleanedLine = line
					// Remove remaining bold/italic that isn't a header
					.replace(/\*\*([^*]+)\*\*/g, '$1')
					.replace(/\*([^*]+)\*/g, '$1')
					.replace(/_([^_]+)_/g, '$1')
					// Clean bullet points
					.replace(/^\s*[\*\+]\s+/g, '- ');
				
				currentText += (currentText ? '\n' : '') + cleanedLine;
			}
		}
		
		// Add any remaining text
		if (currentText.trim()) {
			processed.push({ type: 'text' as const, content: currentText.trim() });
		}
		
		return processed;
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
		<a href="/{city_url}" class="back-link">← Back to {searchResults && searchResults.success ? searchResults.city_name : 'city'} meetings</a>
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
				{#if searchResults && searchResults.success}
					<div class="meeting-location">
						{searchResults.city_name}, {searchResults.state}
					</div>
				{/if}
				<div class="meeting-date">
					{formatMeetingDate(selectedMeeting.start || selectedMeeting.meeting_date)}
				</div>
			</div>
			
			{#if selectedMeeting.processed_summary}
				{@const processedContent = processSummary(selectedMeeting.processed_summary)}
				<div class="meeting-summary">
					{#if processedContent.length === 1 && processedContent[0].type === 'text'}
						<!-- Plain text summary without headers -->
						<div class="summary-content">
							{processedContent[0].content}
						</div>
					{:else}
						<!-- Structured summary with headers -->
						{#each processedContent as block}
							{#if block.type === 'header'}
								<h3 class="summary-header">{block.content}</h3>
							{:else}
								<div class="summary-text">
									{block.content}
								</div>
							{/if}
						{/each}
					{/if}
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

	<Footer />
</div>

<style>

	.packet-url-box {
		margin: 1.5rem 0;
		padding: 1rem;
		background: #f0f9ff;
		border: 1px solid #bae6fd;
		border-radius: 8px;
		overflow: hidden;
		word-wrap: break-word;
		overflow-wrap: break-word;
	}

	.packet-url-content {
		display: flex;
		align-items: flex-start;
		gap: 0.75rem;
		flex-direction: column;
	}

	.packet-url-label {
		font-weight: 500;
		color: var(--civic-dark);
		font-size: 0.85rem;
		line-height: 1.4;
	}

	.packet-url-link {
		color: var(--civic-blue);
		text-decoration: none;
		word-break: break-word;
		overflow-wrap: break-word;
		font-size: 0.85rem;
		width: 100%;
		display: block;
		line-height: 1.4;
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

	.meeting-location {
		color: var(--civic-blue);
		font-size: 1.2rem;
		margin: 0.3rem 0;
		font-weight: 500;
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
			word-wrap: break-word;
			overflow-wrap: break-word;
		}
		
		.meeting-detail {
			padding: 1rem;
		}

		.packet-url-box {
			padding: 0.75rem;
			margin: 1rem 0;
		}

		.packet-url-label {
			font-size: 0.8rem;
		}

		.packet-url-link {
			font-size: 0.75rem;
		}

		.back-link {
			font-size: 1rem;
		}

		.meeting-summary {
			font-size: 1rem;
			overflow-wrap: break-word;
			word-wrap: break-word;
		}

		.meeting-header {
			margin-bottom: 1.5rem;
		}
	}
</style>