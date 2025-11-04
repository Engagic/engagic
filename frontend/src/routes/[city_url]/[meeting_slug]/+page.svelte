<script lang="ts">
	import { page } from '$app/stores';
	import { SvelteSet } from 'svelte/reactivity';
	import { marked } from 'marked';
	import type { SearchResult, Meeting } from '$lib/api/index';
	import { config } from '$lib/api/config';
	import { extractTime } from '$lib/utils/date-utils';
	import Footer from '$lib/components/Footer.svelte';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	let city_banana = $page.params.city_url;
	let searchResults: SearchResult | null = $state(data.searchResults || null);
	let selectedMeeting: Meeting | null = $state(data.selectedMeeting || null);
	let error = $state(data.error || '');
	let showProceduralItems = $state(false);
	let expandedAttachments = new SvelteSet<string>();
	let expandedTitles = new SvelteSet<string>();
	let expandedItems = new SvelteSet<string>();
	let expandedThinking = new SvelteSet<string>();

	// Flyer generation state - simplified
	let flyerGenerating = $state(false);

	// Handle deep linking to specific items
	$effect(() => {
		if (typeof window !== 'undefined' && window.location.hash) {
			const hash = window.location.hash;
			const itemId = hash.replace('#item-', '');

			// Expand the item if it exists
			if (itemId) {
				expandedItems.add(itemId);

				// Scroll to the item after a short delay to ensure rendering
				setTimeout(() => {
					const element = document.getElementById(`item-${itemId}`);
					if (element) {
						element.scrollIntoView({ behavior: 'smooth', block: 'center' });
						// Add a subtle highlight effect
						element.style.backgroundColor = '#fef3c7';
						setTimeout(() => {
							element.style.backgroundColor = '';
							element.style.transition = 'background-color 1s ease';
						}, 2000);
					}
				}, 100);
			}
		}
	});

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



	function cleanSummary(rawSummary: string): string {
		if (!rawSummary) return '';

		// Remove ugly document headers but keep the markdown formatting
		return rawSummary
			.replace(/=== DOCUMENT \d+ ===/g, '')
			.replace(/--- SECTION \d+ SUMMARY ---/g, '')
			.replace(/Here's a concise summary of the[^:]*:/gi, '')
			.replace(/Here's a summary of the[^:]*:/gi, '')
			.replace(/Here's the key points[^:]*:/gi, '')
			.replace(/Here's a structured analysis[^:]*:/gi, '')
			.replace(/Summary of the[^:]*:/gi, '')
			.replace(/\n{3,}/g, '\n\n')
			.trim();
	}

	function toggleAttachments(itemId: string) {
		if (expandedAttachments.has(itemId)) {
			expandedAttachments.delete(itemId);
		} else {
			expandedAttachments.add(itemId);
		}
	}

	function toggleTitle(itemId: string) {
		if (expandedTitles.has(itemId)) {
			expandedTitles.delete(itemId);
		} else {
			expandedTitles.add(itemId);
		}
	}

	function toggleItem(itemId: string) {
		if (expandedItems.has(itemId)) {
			expandedItems.delete(itemId);
		} else {
			expandedItems.add(itemId);
		}
	}

	function toggleThinking(itemId: string) {
		if (expandedThinking.has(itemId)) {
			expandedThinking.delete(itemId);
		} else {
			expandedThinking.add(itemId);
		}
	}

	function parseSummaryForThinking(summary: string): { thinking: string | null; summary: string } {
		if (!summary) return { thinking: null, summary: '' };

		// Simple split on "## Thinking"
		const parts = summary.split(/^## Thinking\s*$/m);

		if (parts.length < 2) {
			// No thinking section found
			return { thinking: null, summary };
		}

		// Everything before "## Thinking" (usually empty or intro text)
		const before = parts[0].trim();

		// Everything after "## Thinking"
		const afterThinking = parts[1];

		// Find the next section heading to split thinking from summary
		const nextSectionMatch = afterThinking.match(/^##\s+/m);

		if (nextSectionMatch) {
			const thinkingEnd = nextSectionMatch.index!;
			const thinkingContent = afterThinking.substring(0, thinkingEnd).trim();
			const summaryContent = afterThinking.substring(thinkingEnd).trim();

			return {
				thinking: thinkingContent,
				summary: (before ? before + '\n\n' : '') + summaryContent
			};
		}

		// No next section - everything after "## Thinking" is thinking content
		return {
			thinking: afterThinking.trim(),
			summary: before || ''
		};
	}

	function truncateTitle(title: string, itemId: string): { main: string; remainder: string | null; isTruncated: boolean } {
		const semicolonIndex = title.indexOf(';');
		if (semicolonIndex !== -1 && semicolonIndex < title.length - 1) {
			const isExpanded = expandedTitles.has(itemId);
			if (isExpanded) {
				return { main: title, remainder: null, isTruncated: false };
			}
			const main = title.substring(0, semicolonIndex);
			const remainder = title.substring(semicolonIndex);
			return { main, remainder, isTruncated: true };
		}
		return { main: title, remainder: null, isTruncated: false };
	}

	function generateSimpleFlyer(item: any, position: 'yes' | 'no') {
		if (!selectedMeeting) return;

		// Get city info
		const cityName = searchResults && 'city_name' in searchResults ? searchResults.city_name : 'Your City';
		const state = searchResults && 'state' in searchResults ? searchResults.state : '';

		// Truncate title intelligently for flyer display
		let displayTitle = item.title;

		// Step 1: If there's a semicolon, take only the first part
		const semicolonIndex = displayTitle.indexOf(';');
		if (semicolonIndex !== -1 && semicolonIndex < displayTitle.length - 1) {
			displayTitle = displayTitle.substring(0, semicolonIndex);
		}

		// Step 2: If there's a period in the first 150 chars, take just the first sentence
		const periodIndex = displayTitle.indexOf('.');
		if (periodIndex !== -1 && periodIndex < 150) {
			displayTitle = displayTitle.substring(0, periodIndex + 1);
		}

		// Step 3: Hard cap at 150 characters with ellipsis
		if (displayTitle.length > 150) {
			displayTitle = displayTitle.substring(0, 147) + '...';
		}

		// Format date
		let dateStr = 'Date TBD';
		if (selectedMeeting.date) {
			const date = new Date(selectedMeeting.date);
			if (!isNaN(date.getTime())) {
				const dayOfWeek = date.toLocaleDateString('en-US', { weekday: 'long' });
				const monthDay = date.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
				const time = extractTime(selectedMeeting.date);
				dateStr = `${dayOfWeek}, ${monthDay}${time ? ' at ' + time : ''}`;
			}
		}

		// Participation methods
		const participation = selectedMeeting.participation || {};
		const methods = [];
		if (participation.email) methods.push(`EMAILING ${participation.email}`);
		if (participation.phone) methods.push(`CALLING ${participation.phone}`);
		if (participation.zoom_url || participation.virtual_url) {
			const url = participation.zoom_url || participation.virtual_url;
			methods.push(`ZOOMING AT ${url}`);
		}
		const participationText = methods.length > 0 ? methods.join('\n') : 'CONTACTING YOUR CITY COUNCIL';

		// Generate item-specific URL with hash for deep linking
		const meeting_slug = `${selectedMeeting.title?.toLowerCase().replace(/[^a-z0-9\s]/g, '').replace(/\s+/g, '_').substring(0, 50)}_${selectedMeeting.date ? new Date(selectedMeeting.date).toISOString().split('T')[0].replace(/-/g, '_') : 'undated'}_${selectedMeeting.id}`;
		const itemUrl = `https://engagic.org/${city_banana}/${meeting_slug}#item-${item.id}`;

		// Generate QR code URL using qrserver.com (public API, no Google)
		const qrCodeUrl = `https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=${encodeURIComponent(itemUrl)}`;

		// Generate HTML
		const html = `<!DOCTYPE html>
<html>
<head>
	<meta charset="UTF-8">
	<meta name="viewport" content="width=device-width, initial-scale=1.0">
	<title>${position === 'yes' ? 'Say Yes' : 'Say No'} - ${cityName}</title>
	<style>
		* { margin: 0; padding: 0; box-sizing: border-box; }
		body {
			font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
			background: white;
			padding: 2rem;
			max-width: 800px;
			margin: 0 auto;
			line-height: 1.6;
		}
		.header {
			font-size: 3rem;
			font-weight: 900;
			text-align: center;
			margin-bottom: 2rem;
			color: ${position === 'yes' ? '#16a34a' : '#dc2626'};
			text-transform: uppercase;
			letter-spacing: 2px;
		}
		.title {
			font-size: 1.75rem;
			font-weight: 700;
			text-align: center;
			margin-bottom: 2rem;
			padding: 2rem;
			background: #f3f4f6;
			border-radius: 12px;
			color: #1f2937;
			line-height: 1.4;
		}
		.city {
			font-size: 1.25rem;
			font-weight: 600;
			text-align: center;
			margin-bottom: 0.5rem;
			color: #4b5563;
		}
		.date {
			font-size: 1.1rem;
			font-weight: 600;
			text-align: center;
			margin-bottom: 3rem;
			color: #6b7280;
		}
		.participate {
			font-size: 1.5rem;
			font-weight: 700;
			margin-bottom: 1.5rem;
			color: #1f2937;
		}
		.methods {
			font-size: 1.25rem;
			white-space: pre-line;
			padding: 1.5rem;
			background: #f9fafb;
			border-radius: 8px;
			border: 2px solid #e5e7eb;
			color: #374151;
			line-height: 1.8;
		}
		.footer {
			margin-top: 3rem;
			display: flex;
			align-items: center;
			justify-content: center;
			gap: 1rem;
			flex-direction: column;
		}
		.qr-code {
			width: 100px;
			height: 100px;
		}
		.footer-text {
			font-size: 0.875rem;
			color: #9ca3af;
		}
		@media print {
			body { padding: 0; }
		}
		@media (max-width: 640px) {
			body { padding: 1rem; }
			.header { font-size: 2rem; }
			.title { font-size: 1.25rem; padding: 1.5rem; }
			.city { font-size: 1.1rem; }
			.date { font-size: 0.95rem; }
			.participate { font-size: 1.25rem; }
			.methods { font-size: 1rem; padding: 1rem; }
			.qr-code { width: 80px; height: 80px; }
		}
	</style>
</head>
<body>
	<div class="header">SAY ${position === 'yes' ? 'YES' : 'NO'} TO</div>
	<div class="title">${displayTitle}</div>
	<div class="city">${cityName}${state ? ', ' + state : ''}</div>
	<div class="date">${dateStr}</div>
	<div class="participate">YOU CAN PARTICIPATE BY:</div>
	<div class="methods">${participationText}</div>
	<div class="footer">
		<img src="${qrCodeUrl}" alt="QR Code to Meeting" class="qr-code" />
		<div class="footer-text">Scan to view full agenda at engagic.org</div>
	</div>
</body>
</html>`;

		// Open in new window
		const flyerWindow = window.open('', '_blank');
		if (flyerWindow) {
			flyerWindow.document.write(html);
			flyerWindow.document.close();
		} else {
			alert('Please allow pop-ups to view flyer');
		}
	}


</script>

<svelte:head>
	<title>{selectedMeeting?.title || 'Meeting'} - engagic</title>
	<meta name="description" content="City council meeting agenda and summary" />
</svelte:head>

<div class="container">
	<div class="main-content">
		<div class="top-nav">
			<a href="/{city_banana}" class="back-link">← {searchResults && searchResults.success ? searchResults.city_name : 'Back'}</a>
			<a href="/" class="compact-logo" aria-label="Return to engagic homepage">
				<img src="/icon-64.png" alt="engagic" class="logo-icon" />
			</a>
		</div>

	{#if selectedMeeting?.participation}
		{@const p = selectedMeeting.participation}
		<div class="participation-box">
			<div class="participation-header">
				<span class="participation-label">How to Participate</span>
				{#if p.is_hybrid}
					<span class="participation-badge badge-hybrid">Hybrid Meeting</span>
				{:else if p.is_virtual_only}
					<span class="participation-badge badge-virtual">Virtual Only</span>
				{/if}
			</div>
			<div class="participation-content">
				{#if p.virtual_url}
					<div class="participation-item">
						<span class="participation-icon">📹</span>
						<a href={p.virtual_url} target="_blank" rel="noopener noreferrer" class="participation-link">
							Join Virtual Meeting
						</a>
						{#if p.meeting_id}
							<span class="meeting-id">Meeting ID: {p.meeting_id}</span>
						{/if}
					</div>
				{/if}
				{#if p.email}
					<div class="participation-item">
						<span class="participation-icon">✉️</span>
						<a href="mailto:{p.email}" class="participation-link">
							{p.email}
						</a>
					</div>
				{/if}
				{#if p.phone}
					<div class="participation-item">
						<span class="participation-icon">📞</span>
						<a href="tel:{p.phone}" class="participation-link">
							{p.phone}
						</a>
					</div>
				{/if}
			</div>
		</div>
	{/if}

	{#if error}
		<div class="error-message">
			{error}
		</div>
	{:else if selectedMeeting}
		<div class="meeting-detail">
			{#if selectedMeeting.meeting_status}
				{@const statusClass = selectedMeeting.meeting_status === 'revised' ? 'meeting-info-banner' : 'meeting-alert-banner'}
				{@const iconSymbol = selectedMeeting.meeting_status === 'revised' ? 'i' : '!'}
				<div class={statusClass}>
					<span class="alert-icon">{iconSymbol}</span>
					<span class="alert-text">This meeting has been {selectedMeeting.meeting_status}</span>
				</div>
			{/if}

			<div class="meeting-header">
				<div class="meeting-header-row">
					<h1 class="meeting-title">{selectedMeeting.title}</h1>
					{#if selectedMeeting.has_items && selectedMeeting.items && selectedMeeting.items.length > 0}
						<div class="meeting-helper">
							<span class="helper-dot"></span>
							<span class="helper-text-inline">Blue border = AI summary available</span>
						</div>
					{/if}
				</div>

				<div class="meeting-meta-row">
					<div class="meeting-meta-left">
						{#if selectedMeeting.date}
							{@const date = new Date(selectedMeeting.date)}
							{@const isValidDate = !isNaN(date.getTime()) && date.getTime() !== 0}
							{#if isValidDate}
								{@const dayOfWeek = date.toLocaleDateString('en-US', { weekday: 'short' })}
								{@const monthDay = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
								{@const timeStr = extractTime(selectedMeeting.date)}
								<div class="meeting-date">
									{dayOfWeek}, {monthDay}{#if timeStr} • {timeStr}{/if}
								</div>
							{:else}
								<div class="meeting-date">Date TBD</div>
							{/if}
						{:else}
							<div class="meeting-date">Date TBD</div>
						{/if}
					</div>
					<div class="meeting-meta-right">
						{#if selectedMeeting.agenda_url}
							<a href={selectedMeeting.agenda_url} target="_blank" rel="noopener noreferrer" class="document-link">
								<span class="document-icon">📄</span>
								<span>View Agenda</span>
							</a>
						{:else if selectedMeeting.packet_url}
							{@const urls = Array.isArray(selectedMeeting.packet_url) ? selectedMeeting.packet_url : [selectedMeeting.packet_url]}
							<a href={urls[0]} target="_blank" rel="noopener noreferrer" class="document-link">
								<span class="document-icon">📋</span>
								<span>View Packet</span>
							</a>
						{/if}
						{#if selectedMeeting.has_items && selectedMeeting.items && selectedMeeting.items.length > 0 && proceduralItems.length > 0}
							<button
								class="toggle-procedural-btn"
								onclick={() => showProceduralItems = !showProceduralItems}
							>
								{showProceduralItems ? 'Hide' : 'Show'} {proceduralItems.length} Procedural
							</button>
						{/if}
					</div>
				</div>
			</div>

			{#if selectedMeeting.has_items && selectedMeeting.items && selectedMeeting.items.length > 0}
				<!-- Item-based meeting display (58% of cities) -->

				<div class="agenda-items">
					{#each displayedItems as item}
						{@const titleParts = truncateTitle(item.title, item.id)}
						{@const isExpanded = expandedItems.has(item.id)}
						{@const hasSummary = !!item.summary}
						<div class="agenda-item" id="item-{item.id}" data-expanded={isExpanded} data-has-summary={hasSummary}>
							<div
								class="item-header-clickable"
								role="button"
								tabindex="0"
								onclick={() => toggleItem(item.id)}
								onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleItem(item.id); } }}
							>
								<div class="item-header">
									<div class="item-header-content">
										<div class="item-title-container">
											<span class="item-number">{item.sequence}.</span>
											<h3 class="item-title" data-truncated={titleParts.isTruncated}>
												{titleParts.main}
												{#if titleParts.remainder && !isExpanded}
													<span class="item-title-remainder">…</span>
												{:else if titleParts.remainder && isExpanded}
													{titleParts.remainder}
												{/if}
											</h3>
											{#if !hasSummary}
												<span class="procedural-badge">Unprocessed</span>
											{/if}
										</div>
										<div class="item-indicators">
											{#if item.topics && item.topics.length > 0}
												<div class="item-topics-preview">
													{#each item.topics.slice(0, 2) as topic}
														<span class="item-topic-tag-small" data-topic={topic.toLowerCase()}>{topic}</span>
													{/each}
													{#if item.topics.length > 2}
														<span class="topic-more">+{item.topics.length - 2} more</span>
													{/if}
												</div>
											{/if}
										</div>
										{#if !isExpanded && hasSummary}
											{@const summaryParts = parseSummaryForThinking(item.summary)}
											{@const cleanText = summaryParts.summary
												.replace(/^#+\s*Summary\s*$/mi, '')
												.replace(/^Summary:?\s*/mi, '')
												.replace(/\*\*Summary\*\*:?\s*/gi, '')
												.replace(/[#*\[\]]/g, '')
												.trim()}
											{@const sentences = cleanText.split(/\.\s+(?=[A-Z])/)}
											{@const secondSentence = sentences.length > 1 ? sentences[1] : sentences[0]}
											{@const preview = secondSentence.substring(0, 150)}
											<div class="item-summary-preview">
												{preview}{preview.length >= 150 ? '...' : ''}
											</div>
										{/if}
									</div>
									<div class="item-header-right">
										{#if item.attachments && item.attachments.length > 0}
											<span class="attachment-badge">{item.attachments.length}</span>
										{/if}
										<button class="expand-icon" aria-label={isExpanded ? 'Collapse item' : 'Expand item'}>
											{isExpanded ? '−' : '+'}
										</button>
									</div>
								</div>
							</div>

							{#if isExpanded}
								<div class="item-expanded-content">
									{#if item.summary}
										{@const summaryParts = parseSummaryForThinking(item.summary)}

										{#if summaryParts.thinking}
											<div class="thinking-section" class:expanded={expandedThinking.has(item.id)}>
												<button
													class="thinking-toggle"
													onclick={(e) => { e.stopPropagation(); toggleThinking(item.id); }}
												>
													💭 Thinking trace (click to {expandedThinking.has(item.id) ? 'collapse' : 'expand'})
												</button>
												{#if expandedThinking.has(item.id)}
													<div class="thinking-content">
														{@html marked(summaryParts.thinking)}
													</div>
												{/if}
											</div>
										{/if}

										<div class="item-summary">
											{@html marked(summaryParts.summary)}
										</div>

										<!-- Flyer generator buttons -->
										<div class="item-action-bar">
											<button
												class="flyer-btn flyer-btn-yes"
												onclick={(e) => {
													e.stopPropagation();
													generateSimpleFlyer(item, 'yes');
												}}
											>
												✓ Say Yes
											</button>
											<button
												class="flyer-btn flyer-btn-no"
												onclick={(e) => {
													e.stopPropagation();
													generateSimpleFlyer(item, 'no');
												}}
											>
												✗ Say No
											</button>
										</div>
									{/if}

									{#if item.attachments && item.attachments.length > 0}
										<div class="item-attachments-container">
											<div class="attachments-label">Attachments:</div>
											<div class="item-attachments">
												{#each item.attachments as attachment}
													{#if attachment.url}
														<a href={attachment.url} target="_blank" rel="noopener noreferrer" class="attachment-link" onclick={(e) => e.stopPropagation()}>
															{attachment.name || 'View Packet'}{attachment.pages ? ` (${attachment.pages})` : ''}
														</a>
													{/if}
												{/each}
											</div>
										</div>
									{/if}
								</div>
							{/if}
						</div>
					{/each}
				</div>
			{:else if selectedMeeting.summary}
				<!-- Monolithic meeting display (42% of cities) -->
				<div class="meeting-summary">
					{@html marked(cleanSummary(selectedMeeting.summary))}
				</div>
			{:else}
				<!-- Processing state -->
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


	.agenda-url-box {
		margin: 1.5rem 0;
		padding: 0;
		background: transparent;
		border: none;
	}

	.agenda-url-link {
		display: inline-block;
		padding: 0.75rem 1.25rem;
		background: var(--civic-blue);
		color: white;
		text-decoration: none;
		font-family: 'IBM Plex Mono', monospace;
		font-weight: 600;
		font-size: 0.9rem;
		border-radius: 6px;
		transition: all 0.2s;
		box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
	}

	.agenda-url-link:hover {
		background: #0369a1;
		box-shadow: 0 2px 5px rgba(0, 0, 0, 0.15);
		transform: translateY(-1px);
	}

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
		margin-bottom: 0.5rem;
	}

	.multi-url-compact {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		align-items: center;
	}

	.compact-url-link {
		color: var(--civic-blue);
		text-decoration: none;
		font-size: 0.85rem;
		font-weight: 500;
		padding: 0.25rem 0.5rem;
		background: white;
		border-radius: 4px;
		border: 1px solid #bae6fd;
		transition: background 0.2s;
	}

	.compact-url-link:hover {
		background: #f0f9ff;
		text-decoration: none;
	}

	.url-separator {
		color: #94a3b8;
		font-size: 0.9rem;
	}

	.participation-box {
		margin: 1.5rem 0;
		padding: 1.25rem 1.5rem;
		background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
		border: 2px solid #22c55e;
		border-radius: 12px;
		box-shadow: 0 4px 12px rgba(34, 197, 94, 0.15);
	}

	.participation-header {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-bottom: 0.75rem;
	}

	.participation-label {
		font-family: 'IBM Plex Mono', monospace;
		font-weight: 600;
		color: #15803d;
		font-size: 0.85rem;
		text-transform: uppercase;
		letter-spacing: 0.5px;
	}

	.participation-badge {
		padding: 0.2rem 0.6rem;
		border-radius: 12px;
		font-size: 0.75rem;
		font-weight: 500;
		font-family: 'IBM Plex Mono', monospace;
	}

	.badge-hybrid {
		background: #fef3c7;
		color: #92400e;
		border: 1px solid #fbbf24;
	}

	.badge-virtual {
		background: #dbeafe;
		color: #1e40af;
		border: 1px solid #60a5fa;
	}

	.participation-content {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.participation-item {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		flex-wrap: wrap;
	}

	.participation-icon {
		font-size: 1rem;
		flex-shrink: 0;
	}

	.participation-link {
		color: #15803d;
		text-decoration: none;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
		font-weight: 500;
		transition: color 0.2s;
	}

	.participation-link:hover {
		color: #166534;
		text-decoration: underline;
	}

	.meeting-id {
		color: #6b7280;
		font-size: 0.8rem;
		font-family: 'IBM Plex Mono', monospace;
		margin-left: 0.5rem;
	}

	.city-header {
		margin-bottom: 1rem;
	}

	.meeting-detail {
		padding: 2rem;
		background: var(--civic-white);
		border-radius: 16px;
		border: 1px solid var(--civic-border);
		box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
	}

	.meeting-alert-banner {
		background: #fef2f2;
		border: 1px solid #fecaca;
		border-radius: 6px;
		padding: 0.75rem 1rem;
		margin-bottom: 1.5rem;
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.meeting-info-banner {
		background: #eff6ff;
		border: 1px solid #bfdbfe;
		border-radius: 6px;
		padding: 0.75rem 1rem;
		margin-bottom: 1.5rem;
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.alert-icon {
		flex-shrink: 0;
		width: 24px;
		height: 24px;
		background: #dc2626;
		color: white;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		font-weight: 700;
		font-size: 0.9rem;
	}

	.meeting-info-banner .alert-icon {
		background: #2563eb;
	}

	.alert-text {
		color: #991b1b;
		font-weight: 600;
		font-size: 0.95rem;
		text-transform: capitalize;
	}

	.meeting-info-banner .alert-text {
		color: #1e40af;
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
		color: var(--civic-dark);
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
		font-size: 0.85rem;
	}

	.meeting-divider {
		margin: 2rem 0;
		height: 1px;
		background: var(--civic-border);
	}

	.meeting-summary {
		font-family: Georgia, 'Times New Roman', Times, serif;
		line-height: 1.8;
		font-size: 1.05rem;
		color: #1f2937;
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
		color: var(--civic-dark);
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
		border-left: 4px solid #333;
		color: #333;
		font-style: italic;
	}

	.meeting-summary :global(code) {
		font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
		font-size: 0.9em;
		background: #f5f5f5;
		padding: 0.2rem 0.4rem;
		border-radius: 3px;
	}

	.meeting-summary :global(pre) {
		margin: 2rem 0;
		padding: 1.5rem;
		background: #f5f5f5;
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
		border-top: 1px solid #ddd;
	}

	.meeting-summary :global(img) {
		max-width: 100%;
		height: auto;
		margin: 2rem 0;
	}

	.no-summary {
		text-align: center;
		padding: 4rem 2rem;
		background: linear-gradient(135deg, #eff6ff 0%, #f8fafc 100%);
		border-radius: 12px;
		border: 2px solid #bfdbfe;
		box-shadow: 0 2px 8px rgba(79, 70, 229, 0.08);
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
		color: var(--civic-dark);
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

	/* Item-based meeting styles */

	.toggle-procedural-btn {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--civic-gray);
		background: white;
		border: 1px solid #e2e8f0;
		border-radius: 5px;
		padding: 0.25rem 0.75rem;
		cursor: pointer;
		transition: all 0.2s ease;
	}

	.toggle-procedural-btn:hover {
		background: #f8fafc;
		border-color: var(--civic-gray);
		color: var(--civic-dark);
	}

	.agenda-items-header {
		margin-bottom: 2rem;
	}

	.agenda-title {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.95rem;
		font-weight: 600;
		color: var(--civic-gray);
		margin: 0 0 1rem 0;
		text-transform: uppercase;
		letter-spacing: 0.5px;
	}

	.meeting-topics {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin-top: 0.75rem;
	}

	.topic-badge {
		display: inline-block;
		padding: 0.25rem 0.75rem;
		background: #f0f9ff;
		color: #0369a1;
		border-radius: 12px;
		font-size: 0.8rem;
		font-weight: 500;
		font-family: 'IBM Plex Mono', monospace;
	}

	.agenda-items {
		display: flex;
		flex-direction: column;
		gap: 1rem;
		margin-top: 2rem;
	}

	.agenda-item {
		background: white;
		border-radius: 12px;
		border: 1px solid #e2e8f0;
		border-left: 4px solid #cbd5e1;
		box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
		transition: all 0.2s ease;
		overflow: hidden;
	}

	.agenda-item[data-has-summary="true"] {
		border-left-color: #93c5fd;
	}

	.agenda-item[data-has-summary="false"] {
		border-left-color: #e2e8f0;
		background: #f8fafc;
		opacity: 0.75;
	}

	.agenda-item[data-expanded="true"] {
		border-left-color: var(--civic-blue);
	}

	.agenda-item[data-has-summary="false"][data-expanded="true"] {
		opacity: 1;
	}

	.agenda-item:hover {
		border-left-color: var(--civic-accent);
		box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
	}

	.item-header-clickable {
		padding: 1rem 1.25rem;
		cursor: pointer;
		transition: background 0.15s ease;
	}

	.item-header-clickable:hover {
		background: #f8fafc;
	}

	.item-header {
		display: flex;
		align-items: flex-start;
		gap: 0.75rem;
		justify-content: space-between;
	}

	.item-title-container {
		display: flex;
		align-items: baseline;
		gap: 0.5rem;
		margin-bottom: 0.35rem;
		flex-wrap: wrap;
	}

	.procedural-badge {
		display: inline-block;
		padding: 0.15rem 0.5rem;
		background: #fef3c7;
		color: #92400e;
		border: 1px solid #fbbf24;
		border-radius: 10px;
		font-size: 0.65rem;
		font-weight: 600;
		font-family: 'IBM Plex Mono', monospace;
		text-transform: uppercase;
		letter-spacing: 0.3px;
		margin-left: 0.5rem;
	}

	.item-summary-preview {
		margin-top: 0.5rem;
		padding: 0.75rem;
		background: #f8fafc;
		border-left: 2px solid #cbd5e1;
		border-radius: 4px;
		font-family: Georgia, 'Times New Roman', Times, serif;
		font-size: 0.9rem;
		line-height: 1.6;
		color: #475569;
		font-style: italic;
	}

	.item-number {
		color: var(--civic-gray);
		font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
		font-size: 1.125rem;
		font-weight: 500;
		flex-shrink: 0;
	}

	.item-header-content {
		flex: 1;
		min-width: 0;
	}

	.item-header-right {
		flex-shrink: 0;
		display: flex;
		align-items: flex-start;
		gap: 0.5rem;
	}

	.attachment-badge {
		display: flex;
		align-items: center;
		justify-content: center;
		min-width: 1.5rem;
		height: 1.5rem;
		padding: 0 0.35rem;
		background: #f1f5f9;
		color: var(--civic-gray);
		border-radius: 12px;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.7rem;
		font-weight: 600;
	}

	.expand-icon {
		flex-shrink: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		width: 1.75rem;
		height: 1.75rem;
		background: transparent;
		border: 1.5px solid #cbd5e1;
		border-radius: 6px;
		color: var(--civic-gray);
		font-size: 1.1rem;
		font-weight: 400;
		cursor: pointer;
		transition: all 0.2s ease;
	}

	.expand-icon:hover {
		background: var(--civic-blue);
		border-color: var(--civic-blue);
		color: white;
	}

	.item-title {
		font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
		font-size: 1.125rem;
		font-weight: 500;
		color: var(--civic-dark);
		margin: 0;
		line-height: 1.45;
		-webkit-font-smoothing: antialiased;
		-moz-osx-font-smoothing: grayscale;
		flex: 1;
		min-width: 0;
	}

	.item-title-remainder {
		color: var(--civic-gray);
		font-weight: 400;
	}

	.item-indicators {
		display: flex;
		align-items: center;
		gap: 1rem;
		flex-wrap: wrap;
	}

	.item-topics-preview {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
		align-items: center;
	}

	.item-topic-tag-small {
		display: inline-block;
		padding: 0.25rem 0.65rem;
		background: var(--topic-bg, #f1f5f9);
		color: var(--topic-color, #475569);
		border: 1.5px solid var(--topic-border, #cbd5e1);
		border-radius: 12px;
		font-size: 0.7rem;
		font-weight: 600;
		font-family: 'IBM Plex Mono', monospace;
		text-transform: uppercase;
		letter-spacing: 0.3px;
	}

	.topic-more {
		font-size: 0.7rem;
		color: var(--civic-gray);
		font-family: 'IBM Plex Mono', monospace;
		font-weight: 500;
	}

	.attachment-indicator {
		font-size: 0.75rem;
		color: var(--civic-gray);
		font-family: 'IBM Plex Mono', monospace;
		font-weight: 500;
		padding: 0.25rem 0.65rem;
		background: #f1f5f9;
		border-radius: 12px;
	}

	.item-expanded-content {
		padding: 0 1.25rem 1.25rem 1.25rem;
		border-top: 1px solid #f1f5f9;
		animation: slideDown 0.2s ease-out;
	}

	@keyframes slideDown {
		from {
			opacity: 0;
			transform: translateY(-10px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	/* Topic color system - meaningful, consistent colors */
	.item-topic-tag-small[data-topic="housing"],
	.item-topic-tag[data-topic="housing"] {
		--topic-bg: #fef3c7;
		--topic-color: #92400e;
		--topic-border: #fbbf24;
	}

	.item-topic-tag-small[data-topic="zoning"],
	.item-topic-tag[data-topic="zoning"] {
		--topic-bg: #e0e7ff;
		--topic-color: #3730a3;
		--topic-border: #6366f1;
	}

	.item-topic-tag-small[data-topic="budget"],
	.item-topic-tag[data-topic="budget"] {
		--topic-bg: #d1fae5;
		--topic-color: #065f46;
		--topic-border: #10b981;
	}

	.item-topic-tag-small[data-topic="transportation"],
	.item-topic-tag[data-topic="transportation"] {
		--topic-bg: #dbeafe;
		--topic-color: #1e40af;
		--topic-border: #3b82f6;
	}

	.item-topic-tag-small[data-topic="environment"],
	.item-topic-tag[data-topic="environment"] {
		--topic-bg: #dcfce7;
		--topic-color: #166534;
		--topic-border: #22c55e;
	}

	.item-topic-tag-small[data-topic="public safety"],
	.item-topic-tag[data-topic="public safety"] {
		--topic-bg: #fee2e2;
		--topic-color: #991b1b;
		--topic-border: #ef4444;
	}

	.item-topic-tag-small[data-topic="development"],
	.item-topic-tag[data-topic="development"] {
		--topic-bg: #fae8ff;
		--topic-color: #6b21a8;
		--topic-border: #a855f7;
	}

	.item-topic-tag-small[data-topic="infrastructure"],
	.item-topic-tag[data-topic="infrastructure"] {
		--topic-bg: #f3f4f6;
		--topic-color: #374151;
		--topic-border: #6b7280;
	}

	.item-topic-tag-small[data-topic="parks"],
	.item-topic-tag[data-topic="parks"] {
		--topic-bg: #ecfdf5;
		--topic-color: #14532d;
		--topic-border: #059669;
	}

	.item-topic-tag-small[data-topic="governance"],
	.item-topic-tag[data-topic="governance"] {
		--topic-bg: #fef2f2;
		--topic-color: #7f1d1d;
		--topic-border: #dc2626;
	}

	.item-topic-tag-small[data-topic="health"],
	.item-topic-tag[data-topic="health"] {
		--topic-bg: #fff7ed;
		--topic-color: #7c2d12;
		--topic-border: #f97316;
	}

	.item-topic-tag-small[data-topic="education"],
	.item-topic-tag[data-topic="education"] {
		--topic-bg: #fef3c7;
		--topic-color: #78350f;
		--topic-border: #eab308;
	}

	.item-topic-tag-small[data-topic="economic development"],
	.item-topic-tag[data-topic="economic development"] {
		--topic-bg: #ede9fe;
		--topic-color: #5b21b6;
		--topic-border: #8b5cf6;
	}

	.item-topic-tag-small[data-topic="utilities"],
	.item-topic-tag[data-topic="utilities"] {
		--topic-bg: #e0f2fe;
		--topic-color: #075985;
		--topic-border: #0ea5e9;
	}

	.item-summary {
		font-family: Georgia, 'Times New Roman', Times, serif;
		line-height: 1.7;
		font-size: 1rem;
		color: #1f2937;
		margin-bottom: 1.5rem;
		letter-spacing: 0.01em;
		-webkit-font-smoothing: antialiased;
		-moz-osx-font-smoothing: grayscale;
	}

	.thinking-content {
		font-family: Georgia, 'Times New Roman', Times, serif;
		line-height: 1.7;
		font-size: 1rem;
		color: #1f2937;
		letter-spacing: 0.01em;
	}

	.item-summary :global(p) {
		margin: 1rem 0;
	}

	.item-summary :global(p:first-child) {
		margin-top: 0;
	}

	.item-summary :global(strong) {
		font-weight: 700;
		color: var(--civic-dark);
	}

	.item-summary :global(h2) {
		font-size: 0.625rem;
		font-weight: 600;
		color: var(--civic-dark);
		opacity: 0.4;
		margin: 1.5rem 0 0.75rem 0;
		text-transform: uppercase;
		letter-spacing: 1px;
		font-family: 'IBM Plex Mono', monospace;
	}

	.item-summary :global(ul),
	.item-summary :global(ol) {
		margin: 0.75rem 0;
		padding-left: 1.5rem;
	}

	.item-summary :global(li) {
		margin: 0.4rem 0;
	}

	/* Thinking trace - reactive templating */
	.thinking-section {
		margin-bottom: 1.5rem;
	}

	.thinking-toggle {
		display: block;
		width: 100%;
		text-align: left;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8rem;
		font-weight: 600;
		color: var(--civic-blue);
		padding: 0.75rem 1rem;
		background: white;
		border: 2px solid var(--civic-border);
		border-radius: 8px;
		cursor: pointer;
		transition: all 0.2s ease;
		box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
	}

	.thinking-toggle:hover {
		border-color: var(--civic-blue);
		box-shadow: 0 2px 6px rgba(79, 70, 229, 0.15);
		transform: translateY(-1px);
	}

	.thinking-section.expanded .thinking-toggle {
		border-color: var(--civic-blue);
		background: #eff6ff;
	}

	.thinking-content {
		margin-top: 0.75rem;
		padding: 1rem;
		border-left: 3px solid var(--civic-blue);
		background: #f8fafc;
		border-radius: 4px;
		animation: expandThinking 0.2s ease forwards;
		font-family: Georgia, 'Times New Roman', Times, serif;
		line-height: 1.7;
		font-size: 1rem;
		color: #1f2937;
		letter-spacing: 0.01em;
	}

	.thinking-content :global(h2) {
		display: none;
	}

	.thinking-content :global(p) {
		margin: 1rem 0;
	}

	.thinking-content :global(p:first-child) {
		margin-top: 0;
	}

	.thinking-content :global(strong) {
		font-weight: 700;
		color: var(--civic-dark);
	}

	.thinking-content :global(ul),
	.thinking-content :global(ol) {
		margin: 0.75rem 0;
		padding-left: 1.5rem;
	}

	.thinking-content :global(li) {
		margin: 0.4rem 0;
	}

	@keyframes expandThinking {
		from {
			opacity: 0;
			transform: translateY(-10px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	.item-attachments-container {
		margin-top: 1rem;
	}

	.attachments-label {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8rem;
		font-weight: 600;
		color: var(--civic-gray);
		margin-bottom: 0.5rem;
		text-transform: uppercase;
		letter-spacing: 0.5px;
	}

	.item-attachments {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.attachment-link {
		display: inline-block;
		padding: 0.5rem 1rem;
		background: white;
		color: var(--civic-blue);
		border: 1.5px solid #cbd5e1;
		border-radius: 8px;
		text-decoration: none;
		font-size: 0.85rem;
		font-weight: 600;
		font-family: 'IBM Plex Mono', monospace;
		transition: all 0.2s;
		box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
	}

	.attachment-link:hover {
		background: #eff6ff;
		border-color: var(--civic-blue);
		transform: translateY(-1px);
		box-shadow: 0 2px 6px rgba(79, 70, 229, 0.2);
	}

	@media (max-width: 640px) {
		.container {
			width: 100%;
			padding: 1rem 0.75rem;
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

		.procedural-badge {
			font-size: 0.6rem;
			padding: 0.12rem 0.4rem;
		}

		.item-summary-preview {
			font-size: 0.85rem;
			padding: 0.6rem;
			margin-top: 0.4rem;
		}

		.meeting-detail {
			padding: 1.5rem;
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
		}

		.packet-url-box {
			padding: 0.75rem;
			margin: 1rem 0;
		}

		.packet-url-label {
			font-size: 0.8rem;
		}

		.compact-url-link {
			font-size: 0.8rem;
			padding: 0.2rem 0.4rem;
		}

		.meeting-summary {
			font-size: 1rem;
			line-height: 1.7;
			overflow-wrap: break-word;
			word-wrap: break-word;
		}

		.meeting-summary :global(h1) { font-size: 1.4rem; }
		.meeting-summary :global(h2) { font-size: 1.25rem; }
		.meeting-summary :global(h3) { font-size: 1.1rem; }

		.meeting-header {
			margin-bottom: 1.5rem;
		}

		.item-header-clickable {
			padding: 0.75rem 1rem;
		}

		.item-expanded-content {
			padding: 0 1rem 1rem 1rem;
		}

		.thinking-toggle {
			font-size: 0.75rem;
			padding: 0.65rem 0.85rem;
		}

		.item-header {
			gap: 0.5rem;
		}

		.item-number {
			font-size: 1rem;
		}

		.expand-icon {
			width: 1.5rem;
			height: 1.5rem;
			font-size: 1rem;
		}

		.attachment-badge {
			min-width: 1.25rem;
			height: 1.25rem;
			font-size: 0.65rem;
		}

		.item-title {
			font-size: 1rem;
		}

		.item-topic-tag-small {
			font-size: 0.65rem;
			padding: 0.2rem 0.5rem;
		}

		.attachment-indicator {
			font-size: 0.65rem;
			padding: 0.2rem 0.5rem;
		}

		.item-summary {
			font-size: 0.9rem;
		}

		.agenda-url-link {
			font-size: 0.85rem;
			padding: 0.65rem 1rem;
		}

		.attachments-toggle {
			font-size: 0.75rem;
			padding: 0.4rem 0.6rem;
		}

		.attachment-link {
			font-size: 0.8rem;
			padding: 0.35rem 0.65rem;
		}

		.participation-box {
			padding: 0.75rem 1rem;
			margin: 1rem 0;
		}

		.participation-label {
			font-size: 0.8rem;
		}

		.participation-link {
			font-size: 0.85rem;
		}

		.meeting-id {
			font-size: 0.75rem;
		}

		.participation-badge {
			font-size: 0.7rem;
			padding: 0.15rem 0.5rem;
		}

		.flyer-btn {
			font-size: 0.85rem;
			padding: 0.75rem 1.25rem;
		}
	}

	/* Flyer Generator Styles */

	.item-action-bar {
		margin-top: 1.5rem;
		padding-top: 1rem;
		border-top: 1px solid #f1f5f9;
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
	}

	.flyer-btn {
		flex: 1;
		min-width: 140px;
		padding: 0.875rem 1.5rem;
		border: none;
		border-radius: 8px;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
		font-weight: 700;
		cursor: pointer;
		transition: all 0.2s ease;
		text-transform: uppercase;
		letter-spacing: 0.5px;
	}

	.flyer-btn-yes {
		background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
		color: white;
		box-shadow: 0 2px 6px rgba(34, 197, 94, 0.3);
	}

	.flyer-btn-yes:hover {
		background: linear-gradient(135deg, #16a34a 0%, #15803d 100%);
		box-shadow: 0 4px 12px rgba(34, 197, 94, 0.4);
		transform: translateY(-1px);
	}

	.flyer-btn-no {
		background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
		color: white;
		box-shadow: 0 2px 6px rgba(239, 68, 68, 0.3);
	}

	.flyer-btn-no:hover {
		background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%);
		box-shadow: 0 4px 12px rgba(239, 68, 68, 0.4);
		transform: translateY(-1px);
	}

	.flyer-btn:active {
		transform: translateY(0);
	}
</style>