<script lang="ts">
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import { SvelteSet } from 'svelte/reactivity';
	import { marked } from 'marked';
	import type { SearchResult, Meeting, MeetingVotesResponse, MeetingVoteMatter } from '$lib/api/index';
	import { isSearchSuccess, getMeetingVotes } from '$lib/api/index';
	import { extractTime } from '$lib/utils/date-utils';
	import { findItemByAnchor } from '$lib/utils/anchor';
	import { cleanSummary } from '$lib/utils/markdown-utils';
	import { truncateForMeta } from '$lib/utils/utils';
	import Footer from '$lib/components/Footer.svelte';
	import ParticipationBox from '$lib/components/ParticipationBox.svelte';
	import MeetingStatusBanner from '$lib/components/MeetingStatusBanner.svelte';
	import AgendaItem from '$lib/components/AgendaItem.svelte';
	import { logger } from '$lib/services/logger';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	// Vote data for this meeting
	let votesData = $state<MeetingVotesResponse | null>(null);

	// Map matter_id -> vote info for quick lookup
	const votesByMatter = $derived(() => {
		if (!votesData?.matters_with_votes) return new Map<string, MeetingVoteMatter>();
		const map = new Map<string, MeetingVoteMatter>();
		for (const mv of votesData.matters_with_votes) {
			map.set(mv.matter_id, mv);
		}
		return map;
	});

	onMount(async () => {
		if (data.selectedMeeting) {
			logger.trackEvent('meeting_view', { city: data.selectedMeeting.banana });
		}

		if (data.selectedMeeting?.id) {
			try {
				votesData = await getMeetingVotes(data.selectedMeeting.id);
			} catch {
				// No votes available for this meeting - expected
			}
		}
	});

	let city_banana = $page.params.city_url;
	let searchResults: SearchResult | null = $state(data.searchResults || null);
	let selectedMeeting: Meeting | null = $state(data.selectedMeeting || null);
	let highlightedItem = data.highlightedItem || null;
	let error = $state(data.error || '');
	let showProceduralItems = $state(false);
	let expandedTitles = new SvelteSet<string>();
	let expandedItems = new SvelteSet<string>();
	let flyerGenerating = $state(false);

	// Handle deep linking to specific items (supports both #item-5-e and #2025-5470 formats)
	function scrollToAnchoredItem(hash: string) {
		if (!hash) return;

		const matchingItem = findItemByAnchor(selectedMeeting!.items!, hash);
		if (!matchingItem) {
			logger.warn(`No matching item found for hash: #${hash}`);
			return;
		}

		// Show procedural items if needed
		if (!matchingItem.summary && !showProceduralItems) {
			showProceduralItems = true;
		}

		expandedItems.add(matchingItem.id);

		// Scroll after DOM renders
		requestAnimationFrame(() => {
			requestAnimationFrame(() => {
				const element = document.getElementById(hash);
				if (!element) {
					logger.warn(`Anchor element not found: #${hash}`);
					return;
				}

				element.scrollIntoView({ behavior: 'smooth', block: 'center' });
				const isDark = document.documentElement.classList.contains('dark');
				element.style.backgroundColor = isDark ? 'rgba(56, 189, 248, 0.15)' : 'rgba(14, 165, 233, 0.1)';
				setTimeout(() => {
					element.style.backgroundColor = '';
					element.style.transition = 'background-color 1s ease';
				}, 2000);
			});
		});
	}

	$effect(() => {
		if (typeof window !== 'undefined' && selectedMeeting?.items) {
			// Handle hash fragments (e.g., #item-5-e)
			if (window.location.hash) {
				scrollToAnchoredItem(window.location.hash.substring(1));
			}
			// Handle query param (e.g., ?item=item-5-e) - used for social sharing links
			const itemParam = $page.url.searchParams.get('item');
			if (itemParam && !window.location.hash) {
				scrollToAnchoredItem(itemParam);
			}
		}
	});

	// Extract city participation using type guard for proper narrowing
	const cityParticipation = $derived(
		searchResults && isSearchSuccess(searchResults) ? searchResults.participation : undefined
	);

	// Filter items by whether they have summaries
	const summarizedItems = $derived(
		selectedMeeting?.items?.filter(item => item.summary) || []
	);
	const proceduralItems = $derived(
		selectedMeeting?.items?.filter(item => !item.summary) || []
	);
	const displayedItems = $derived(
		showProceduralItems
			? selectedMeeting?.items || []
			: summarizedItems
	);

	// Pre-compute formatted date to avoid deep nesting in template
	const formattedDate = $derived.by(() => {
		if (!selectedMeeting?.date) return null;
		const date = new Date(selectedMeeting.date);
		if (isNaN(date.getTime()) || date.getTime() === 0) return null;

		const dayOfWeek = date.toLocaleDateString('en-US', { weekday: 'short' });
		const monthDay = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
		const timeStr = extractTime(selectedMeeting.date);

		return { dayOfWeek, monthDay, timeStr };
	});

	function handleFlyerGenerateChange(generating: boolean) {
		flyerGenerating = generating;
	}

	// Snapshot: Preserve UI state and scroll position during navigation
	export const snapshot = {
		capture: () => ({
			showProceduralItems,
			expandedTitles: Array.from(expandedTitles),
			expandedItems: Array.from(expandedItems),
			scrollY: typeof window !== 'undefined' ? window.scrollY : 0
		}),
		restore: (values: {
			showProceduralItems: boolean;
			expandedTitles: string[];
			expandedItems: string[];
			scrollY: number;
		}) => {
			showProceduralItems = values.showProceduralItems;
			expandedTitles.clear();
			values.expandedTitles.forEach(t => expandedTitles.add(t));
			expandedItems.clear();
			values.expandedItems.forEach(i => expandedItems.add(i));
			if (typeof window !== 'undefined' && typeof values.scrollY === 'number') {
				setTimeout(() => window.scrollTo(0, values.scrollY), 0);
			}
		}
	};

	// Search results with type guard applied once
	const searchData = $derived(
		searchResults && isSearchSuccess(searchResults) ? searchResults : null
	);
	const cityName = $derived(searchData?.city_name ?? '');
	const cityState = $derived(searchData?.state ?? '');

	// OG meta data
	const ogTitle = $derived.by(() => {
		if (highlightedItem?.title) return `${highlightedItem.title} - ${cityName}`;
		if (selectedMeeting?.title) return `${selectedMeeting.title} - ${cityName}`;
		return `City Council Meeting - ${cityName}`;
	});
	const ogDescription = $derived.by(() => {
		if (highlightedItem?.summary) return truncateForMeta(highlightedItem.summary);
		const firstSummary = summarizedItems[0]?.summary;
		if (firstSummary) return truncateForMeta(firstSummary);
		return `City council meeting agenda and summary for ${cityName}`;
	});
	const ogUrl = $derived(
		`https://engagic.org/${city_banana}/${$page.params.meeting_slug}`
	);

	// JSON-LD structured data for Event schema
	const jsonLd = $derived.by(() => {
		if (!selectedMeeting) return '';

		const ld: Record<string, unknown> = {
			'@context': 'https://schema.org',
			'@type': 'Event',
			name: selectedMeeting.title,
			url: ogUrl
		};

		if (selectedMeeting.date) {
			ld.startDate = selectedMeeting.date;
		}

		ld.description = ogDescription;

		// Event attendance mode based on meeting-level participation
		const meetingPart = selectedMeeting.participation;
		if (meetingPart?.virtual_url && meetingPart?.physical_location) {
			ld.eventAttendanceMode = 'https://schema.org/MixedEventAttendanceMode';
		} else if (meetingPart?.virtual_url) {
			ld.eventAttendanceMode = 'https://schema.org/OnlineEventAttendanceMode';
		} else {
			ld.eventAttendanceMode = 'https://schema.org/OfflineEventAttendanceMode';
		}

		// Location
		if (meetingPart?.physical_location) {
			ld.location = {
				'@type': 'Place',
				name: `${cityName} City Hall`,
				address: {
					'@type': 'PostalAddress',
					streetAddress: meetingPart.physical_location,
					addressLocality: cityName,
					addressRegion: cityState
				}
			};
		}

		// Organizer
		ld.organizer = {
			'@type': 'GovernmentOrganization',
			name: `${cityName} City Council`,
			address: {
				'@type': 'PostalAddress',
				addressLocality: cityName,
				addressRegion: cityState
			}
		};

		return JSON.stringify(ld);
	});
</script>

<svelte:head>
	<title>{selectedMeeting?.title || 'Meeting'} - engagic</title>
	<meta name="description" content="{ogDescription}" />

	<!-- Open Graph -->
	<meta property="og:title" content="{ogTitle}" />
	<meta property="og:description" content="{ogDescription}" />
	<meta property="og:type" content="article" />
	<meta property="og:url" content="{ogUrl}" />
	<meta property="og:image" content="https://engagic.org/icon-192.png" />
	<meta property="og:site_name" content="engagic" />

	<!-- Twitter -->
	<meta name="twitter:card" content="summary" />
	<meta name="twitter:title" content="{ogTitle}" />
	<meta name="twitter:description" content="{ogDescription}" />
	<meta name="twitter:image" content="https://engagic.org/icon-192.png" />

	<!-- JSON-LD Structured Data -->
	{#if jsonLd}
		{@html `<script type="application/ld+json">${jsonLd}</script>`}
	{/if}
</svelte:head>

<div class="container">
	<div class="main-content">
		<div class="top-nav">
			<a href="/{city_banana}" class="back-link" data-sveltekit-preload-data="hover">← {searchResults && isSearchSuccess(searchResults) ? searchResults.city_name : 'Back'}</a>
			<a href="/" class="compact-logo" aria-label="Return to engagic homepage" data-sveltekit-preload-data="hover">
				<img src="/icon-64.png" alt="engagic" class="logo-icon" />
			</a>
		</div>

	{#if selectedMeeting?.participation || cityParticipation}
		<ParticipationBox
			participation={selectedMeeting?.participation ?? {}}
			{cityParticipation}
		/>
	{/if}

	{#if error}
		<div class="error-message">
			{error}
		</div>
	{:else if selectedMeeting}
		<div class="meeting-detail">
			<MeetingStatusBanner status={selectedMeeting.meeting_status} />

			<div class="meeting-header">
				<div class="meeting-header-row">
					<h1 class="meeting-title">{selectedMeeting.title}</h1>
					{#if selectedMeeting.has_items && selectedMeeting.items && selectedMeeting.items.length > 0}
						<div class="meeting-helper">
							<span class="helper-dot"></span>
							<span class="helper-text-inline">Blue = summary | Green = how to participate</span>
						</div>
					{/if}
				</div>

				<div class="meeting-meta-row">
					<div class="meeting-meta-left">
						<div class="meeting-date">
							{#if formattedDate}
								{formattedDate.dayOfWeek}, {formattedDate.monthDay}{#if formattedDate.timeStr} - {formattedDate.timeStr}{/if}
							{:else}
								Date TBD
							{/if}
						</div>
						{#if selectedMeeting.committee_id}
							<a href="/{city_banana}/committees/{selectedMeeting.committee_id}"
							   class="committee-link"
							   data-sveltekit-preload-data="tap">
								View Committee
							</a>
						{/if}
					</div>
					<div class="meeting-meta-right">
						{#if selectedMeeting.agenda_url}
							<a href={selectedMeeting.agenda_url} target="_blank" rel="noopener noreferrer" class="document-link">
								<svg class="document-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
									<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
									<path d="M14 2v6h6"/>
									<line x1="16" y1="13" x2="8" y2="13"/>
									<line x1="16" y1="17" x2="8" y2="17"/>
								</svg>
								<span>View Agenda</span>
							</a>
						{:else if selectedMeeting.packet_url}
							{@const urls = Array.isArray(selectedMeeting.packet_url) ? selectedMeeting.packet_url : [selectedMeeting.packet_url]}
							<a href={urls[0]} target="_blank" rel="noopener noreferrer" class="document-link">
								<svg class="document-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
									<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>
									<rect x="8" y="2" width="8" height="4" rx="1" ry="1"/>
								</svg>
								<span>View Packet</span>
							</a>
						{/if}
						{#if selectedMeeting.has_items && selectedMeeting.items && selectedMeeting.items.length > 0 && proceduralItems.length > 0}
							<button
								class="toggle-procedural-btn"
								onclick={() => showProceduralItems = !showProceduralItems}
								aria-label={showProceduralItems ? `Hide ${proceduralItems.length} procedural items` : `Show ${proceduralItems.length} procedural items`}
								aria-expanded={showProceduralItems}
							>
								{showProceduralItems ? 'Hide' : 'Show'} {proceduralItems.length} Procedural
							</button>
						{/if}
					</div>
				</div>
			</div>

			{#if selectedMeeting.has_items && selectedMeeting.items && selectedMeeting.items.length > 0}
				<div class="agenda-items">
					{#each displayedItems as item (item.id)}
						{@const voteInfo = item.matter_id ? votesByMatter().get(item.matter_id) : undefined}
						<svelte:boundary onerror={(e) => logger.error('Agenda item error', { itemId: item.id }, e instanceof Error ? e : undefined)}>
							<AgendaItem
								{item}
								meeting={selectedMeeting}
								{expandedItems}
								{expandedTitles}
								{flyerGenerating}
								onFlyerGenerate={handleFlyerGenerateChange}
								{voteInfo}
							/>
							{#snippet failed(error: unknown, reset: () => void)}
								<div class="agenda-item-error">
									<p>Unable to display agenda item</p>
									<p class="error-detail-small">{item.agenda_number || item.sequence}: {error instanceof Error ? error.message : String(error)}</p>
								</div>
							{/snippet}
						</svelte:boundary>
					{/each}
				</div>
			{:else if selectedMeeting.summary}
				<div class="meeting-summary">
					{@html marked(cleanSummary(selectedMeeting.summary))}
				</div>
			{:else}
				<div class="no-summary">
					<p class="processing-title">AI Summary In Progress</p>
					<p class="processing-message">We're analyzing this meeting agenda right now. This usually takes 2-5 minutes.</p>
					<p class="processing-hint">Tip: Bookmark this page and check back shortly, or view the original document using the button above.</p>
				</div>
			{/if}
		</div>
	{/if}
	</div>

	<Footer />
</div>

<style>
	.container {
		width: var(--width-detail);
		position: relative;
	}

	.top-nav {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 1rem;
	}

	.back-link {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
		color: var(--civic-blue);
		text-decoration: none;
		font-weight: 500;
		transition: all 0.2s;
	}

	.back-link:hover {
		color: var(--civic-accent);
		text-decoration: underline;
	}

	.compact-logo {
		transition: transform 0.2s ease;
	}

	.compact-logo:hover {
		transform: scale(1.05);
	}

	.logo-icon {
		width: 48px;
		height: 48px;
		border-radius: 12px;
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
	}

	.meeting-detail {
		padding: 2rem;
		background: var(--surface-primary);
		border-radius: 16px;
		border: 1px solid var(--border-primary);
		box-shadow: 0 4px 16px var(--shadow-sm);
		transition: background 0.3s ease, border-color 0.3s ease;
	}

	.meeting-header {
		margin-bottom: 1.5rem;
	}

	.meeting-header-row {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 1.5rem;
		margin-bottom: 0.75rem;
	}

	.meeting-title {
		font-family: Georgia, 'Times New Roman', Times, serif;
		font-size: 2rem;
		color: var(--text-primary);
		margin: 0;
		font-weight: 700;
		line-height: 1.3;
		-webkit-font-smoothing: antialiased;
		-moz-osx-font-smoothing: grayscale;
		flex: 1;
		min-width: 0;
	}

	.meeting-date {
		font-family: 'IBM Plex Mono', monospace;
		color: var(--civic-blue);
		font-size: 1.05rem;
		font-weight: 600;
		-webkit-font-smoothing: antialiased;
		-moz-osx-font-smoothing: grayscale;
	}

	.committee-link {
		display: inline-block;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8rem;
		font-weight: 600;
		color: var(--badge-purple-text, #7c3aed);
		text-decoration: none;
		padding: 0.25rem 0.6rem;
		background: var(--badge-purple-bg, rgba(139, 92, 246, 0.1));
		border: 1px solid var(--badge-purple-border, rgba(139, 92, 246, 0.3));
		border-radius: 6px;
		margin-left: 0.75rem;
		transition: all 0.15s ease;
	}

	.committee-link:hover {
		background: var(--badge-purple-bg, rgba(139, 92, 246, 0.2));
		border-color: var(--badge-purple-text, #7c3aed);
		text-decoration: underline;
	}

	.meeting-meta-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 1rem;
	}

	.meeting-meta-left {
		flex: 1;
	}

	.meeting-meta-right {
		flex-shrink: 0;
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}

	.meeting-helper {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.35rem 0.75rem;
		background: #eff6ff;
		border: 1px solid #93c5fd;
		border-radius: 6px;
	}

	.helper-dot {
		width: 8px;
		height: 8px;
		background: #3b82f6;
		border-radius: 50%;
		flex-shrink: 0;
	}

	.helper-text-inline {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		color: #1e40af;
		font-weight: 500;
	}

	.document-link {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		padding: 0.5rem 0.85rem;
		background: var(--civic-blue);
		color: white;
		text-decoration: none;
		font-family: 'IBM Plex Mono', monospace;
		font-weight: 600;
		font-size: 0.8rem;
		border-radius: 6px;
		transition: all 0.2s ease;
		box-shadow: 0 1px 3px rgba(79, 70, 229, 0.2);
		flex-shrink: 0;
		align-self: flex-start;
	}

	.document-link:hover {
		background: var(--civic-accent);
		box-shadow: 0 2px 6px rgba(79, 70, 229, 0.25);
	}

	.document-link:active {
		transform: scale(0.98);
	}

	.document-icon {
		width: 1em;
		height: 1em;
		vertical-align: -0.125em;
		flex-shrink: 0;
	}

	.toggle-procedural-btn {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--civic-gray);
		background: var(--surface-primary);
		border: 1px solid var(--border-primary);
		border-radius: 5px;
		padding: 0.25rem 0.75rem;
		cursor: pointer;
		transition: all 0.2s ease;
	}

	.toggle-procedural-btn:hover {
		background: var(--surface-secondary);
		border-color: var(--civic-gray);
		color: var(--text-primary);
	}

	.agenda-items {
		display: flex;
		flex-direction: column;
		gap: 1rem;
		margin-top: 2rem;
	}

	.agenda-item-error {
		padding: 1rem;
		background: var(--surface-secondary);
		border: 2px solid #ef4444;
		border-radius: 8px;
		text-align: center;
		margin: 1rem 0;
	}

	.agenda-item-error p {
		margin: 0.25rem 0;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
		color: var(--text-primary);
	}

	.error-detail-small {
		color: #ef4444;
		font-size: 0.75rem;
	}

	.meeting-summary {
		font-family: Georgia, 'Times New Roman', Times, serif;
		line-height: 1.8;
		font-size: 1.05rem;
		color: var(--text-primary);
		padding: 0 2rem;
		-webkit-font-smoothing: antialiased;
		-moz-osx-font-smoothing: grayscale;
	}

	.meeting-summary :global(h1),
	.meeting-summary :global(h2),
	.meeting-summary :global(h3),
	.meeting-summary :global(h4),
	.meeting-summary :global(h5),
	.meeting-summary :global(h6) {
		font-family: Georgia, 'Times New Roman', Times, serif;
		color: var(--text-primary);
		margin-top: 2.5rem;
		margin-bottom: 1rem;
		line-height: 1.3;
		font-weight: 600;
	}

	.meeting-summary :global(h1) { font-size: 1.75rem; }
	.meeting-summary :global(h2) { font-size: 1.5rem; }
	.meeting-summary :global(h3) { font-size: 1.25rem; }
	.meeting-summary :global(h4) { font-size: 1.1rem; }

	.meeting-summary :global(h1:first-child),
	.meeting-summary :global(h2:first-child),
	.meeting-summary :global(h3:first-child),
	.meeting-summary :global(h4:first-child) {
		margin-top: 0;
	}

	.meeting-summary :global(p) {
		margin: 1.5rem 0;
	}

	.meeting-summary :global(ul),
	.meeting-summary :global(ol) {
		margin: 1.5rem 0;
		padding-left: 2rem;
	}

	.meeting-summary :global(li) {
		margin: 0.5rem 0;
	}

	.meeting-summary :global(blockquote) {
		margin: 2rem 0;
		padding-left: 1.5rem;
		border-left: 4px solid var(--text-secondary);
		color: var(--text-secondary);
		font-style: italic;
	}

	.meeting-summary :global(code) {
		font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
		font-size: 0.9em;
		background: var(--surface-secondary);
		color: var(--text-primary);
		padding: 0.2rem 0.4rem;
		border-radius: 3px;
	}

	.meeting-summary :global(pre) {
		margin: 2rem 0;
		padding: 1.5rem;
		background: var(--surface-secondary);
		color: var(--text-primary);
		overflow-x: auto;
		line-height: 1.5;
		border-radius: 6px;
	}

	.meeting-summary :global(pre code) {
		padding: 0;
		background: none;
	}

	.meeting-summary :global(a) {
		color: var(--civic-blue);
		text-decoration: underline;
	}

	.meeting-summary :global(strong) {
		font-weight: 600;
	}

	.meeting-summary :global(em) {
		font-style: italic;
	}

	.meeting-summary :global(hr) {
		margin: 3rem 0;
		border: none;
		border-top: 1px solid var(--border-primary);
	}

	.meeting-summary :global(img) {
		max-width: 100%;
		height: auto;
		margin: 2rem 0;
	}

	.no-summary {
		text-align: center;
		padding: 4rem 2rem;
		background: var(--surface-secondary);
		border-radius: 12px;
		border: 2px solid var(--border-primary);
		box-shadow: 0 2px 8px var(--shadow-sm);
	}

	.processing-title {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.3rem;
		font-weight: 600;
		color: var(--civic-blue);
		margin-bottom: 1rem;
	}

	.processing-message {
		font-family: Georgia, 'Times New Roman', Times, serif;
		font-size: 1.05rem;
		line-height: 1.7;
		color: var(--text-primary);
		margin: 0 auto 1rem;
		max-width: 500px;
	}

	.processing-hint {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
		line-height: 1.6;
		color: var(--civic-gray);
		margin: 0 auto;
		max-width: 500px;
		font-style: italic;
	}

	.error-message {
		font-family: Georgia, 'Times New Roman', Times, serif;
		color: #92400e;
		padding: 1.2rem;
		background: #fef3c7;
		border: 1px solid #fde68a;
		border-radius: 12px;
		margin-top: 1rem;
		font-size: 0.95rem;
		line-height: 1.6;
		box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
	}

	@media (max-width: 640px) {
		.container {
			--meeting-pad-x: 1.25rem;
			width: 100%;
			max-width: 100%;
			padding: 1rem 0.75rem;
			overflow-x: hidden;
		}

		.compact-logo {
			right: 0.75rem;
		}

		.logo-icon {
			width: 40px;
			height: 40px;
			border-radius: 10px;
		}

		.toggle-procedural-btn {
			font-size: 0.7rem;
			padding: 0.2rem 0.6rem;
		}

		.meeting-detail {
			padding: var(--meeting-pad-x) var(--meeting-pad-x) 0.75rem var(--meeting-pad-x);
		}

		.agenda-items {
			margin-left: calc(-1 * var(--meeting-pad-x));
			margin-right: calc(-1 * var(--meeting-pad-x));
			margin-bottom: -0.75rem;
		}

		.back-link {
			font-size: 0.75rem;
		}

		.top-nav {
			margin-bottom: 0.75rem;
		}

		.meeting-header {
			margin-bottom: 1.5rem;
		}

		.meeting-header-row {
			flex-direction: column;
			align-items: flex-start;
			gap: 0.75rem;
			margin-bottom: 0.75rem;
		}

		.meeting-title {
			font-size: 1.3rem;
			word-wrap: break-word;
			overflow-wrap: break-word;
		}

		.meeting-date {
			font-size: 0.85rem;
		}

		.meeting-meta-row {
			flex-direction: column;
			align-items: flex-start;
			gap: 0.75rem;
		}

		.meeting-meta-right {
			flex-wrap: wrap;
		}

		.document-link {
			width: auto;
			padding: 0.4rem 0.7rem;
			font-size: 0.75rem;
		}

		.meeting-helper {
			padding: 0.3rem 0.6rem;
		}

		.helper-dot {
			width: 6px;
			height: 6px;
		}

		.helper-text-inline {
			font-size: 0.7rem;
		}

		.meeting-summary {
			padding: 0 0.5rem;
			font-size: 1rem;
			line-height: 1.7;
			overflow-wrap: break-word;
			word-wrap: break-word;
		}

		.meeting-summary :global(h1) {
			font-size: 1.4rem;
			margin-top: 1.5rem;
		}
		.meeting-summary :global(h2) {
			font-size: 1.25rem;
			margin-top: 1.5rem;
		}
		.meeting-summary :global(h3) {
			font-size: 1.1rem;
			margin-top: 1.25rem;
		}

		.meeting-summary :global(p) {
			margin: 1rem 0;
		}

		.meeting-summary :global(ul),
		.meeting-summary :global(ol) {
			padding-left: 1rem;
			margin: 1rem 0;
		}

		.meeting-summary :global(blockquote) {
			margin: 1rem 0;
			padding-left: 1rem;
		}

		.meeting-summary :global(pre) {
			margin: 1rem 0;
			padding: 0.75rem;
			overflow-x: auto;
			font-size: 0.85rem;
		}
	}

	:global(.dark) .meeting-helper {
		background: #1e3a5f;
		border-color: #3b82f6;
	}

	:global(.dark) .helper-dot {
		background: #60a5fa;
	}

	:global(.dark) .helper-text-inline {
		color: #93c5fd;
	}

	:global(.dark) .error-message {
		background: #78350f;
		border-color: #b45309;
		color: #fef3c7;
	}
</style>
