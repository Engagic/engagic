<script lang="ts">
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import { marked } from 'marked';
	import { searchMeetings, type SearchResult, type Meeting } from '$lib/api/index';
	import { parseCityUrl, generateMeetingSlug } from '$lib/utils/utils';
	import Footer from '$lib/components/Footer.svelte';

	let city_banana = $page.params.city_url;
	let meeting_slug = $page.params.meeting_slug;
	let searchResults: SearchResult | null = $state(null);
	let selectedMeeting: Meeting | null = $state(null);
	let loading = $state(true);
	let error = $state('');
	let expandedAttachments = $state<Set<string>>(new Set());


	async function loadMeetingData() {
		loading = true;
		error = '';

		try {
			// Parse the city URL
			const parsed = parseCityUrl(city_banana);
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
			error = 'Unable to load meeting data. The agenda packet may not be posted yet, or there may be a temporary issue accessing city records. Please try again later.';
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
		const newSet = new Set(expandedAttachments);
		if (newSet.has(itemId)) {
			newSet.delete(itemId);
		} else {
			newSet.add(itemId);
		}
		expandedAttachments = newSet;
	}

	function wrapThinkingSections() {
		// Wrap thinking sections for easy hover/click styling
		const summaries = document.querySelectorAll('.item-summary, .meeting-summary');
		summaries.forEach(summary => {
			const headings = summary.querySelectorAll('h2');
			headings.forEach(h2 => {
				if (h2.textContent?.trim() === 'Thinking') {
					const wrapper = document.createElement('div');
					wrapper.className = 'thinking-section';

					// Insert wrapper before the h2
					h2.parentNode?.insertBefore(wrapper, h2);
					wrapper.appendChild(h2);

					// Move all siblings until we hit another h2 or end
					let next = wrapper.nextSibling;
					while (next && next.nodeName !== 'H2') {
						const current = next;
						next = next.nextSibling;
						wrapper.appendChild(current);
					}

					// Add click handler for mobile toggle
					wrapper.addEventListener('click', () => {
						wrapper.classList.toggle('expanded');
					});
				}
			});
		});
	}

	onMount(async () => {
		await loadMeetingData();
		// Wait for DOM to be ready, then wrap thinking sections
		setTimeout(wrapThinkingSections, 100);
	});

</script>

<svelte:head>
	<title>{selectedMeeting?.title || 'Meeting'} - engagic</title>
	<meta name="description" content="City council meeting agenda and summary" />
</svelte:head>

<div class="container">
	<div class="main-content">
		<a href="/" class="compact-logo">engagic</a>

		<div class="breadcrumb">
			<a href="/{city_banana}" class="back-link">← {searchResults && searchResults.success ? searchResults.city_name : 'Back'}</a>
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
			{#if selectedMeeting.meeting_status}
				{@const statusClass = selectedMeeting.meeting_status === 'revised' ? 'meeting-info-banner' : 'meeting-alert-banner'}
				{@const iconSymbol = selectedMeeting.meeting_status === 'revised' ? 'i' : '!'}
				<div class={statusClass}>
					<span class="alert-icon">{iconSymbol}</span>
					<span class="alert-text">This meeting has been {selectedMeeting.meeting_status}</span>
				</div>
			{/if}

			<div class="meeting-header">
				<div class="meeting-header-top">
					<div class="meeting-header-text">
						<h1 class="meeting-title">{selectedMeeting.title}</h1>
						<div class="meeting-date">
							{formatMeetingDate(selectedMeeting.date)}
						</div>
					</div>
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
				</div>
			</div>

			{#if selectedMeeting.has_items && selectedMeeting.items && selectedMeeting.items.length > 0}
				<!-- Item-based meeting display (58% of cities) -->

				<div class="agenda-items">
					{#each selectedMeeting.items as item}
						<div class="agenda-item">
							<div class="item-header">
								<span class="item-number">{item.sequence}</span>
								<h3 class="item-title">{item.title}</h3>
							</div>

							{#if item.topics && item.topics.length > 0}
								<div class="item-topics">
									{#each item.topics as topic}
										<span class="item-topic-tag">{topic}</span>
									{/each}
								</div>
							{/if}

							{#if item.summary}
								<div class="item-summary">
									{@html marked(item.summary)}
								</div>
							{/if}

							{#if item.attachments && item.attachments.length > 0}
								<div class="item-attachments-container">
									<button
										class="attachments-toggle"
										onclick={() => toggleAttachments(item.id)}
									>
										<span class="toggle-icon">{expandedAttachments.has(item.id) ? '▼' : '▶'}</span>
										<span class="attachments-count">{item.attachments.length} {item.attachments.length === 1 ? 'attachment' : 'attachments'}</span>
									</button>
									{#if expandedAttachments.has(item.id)}
										<div class="item-attachments">
											{#each item.attachments as attachment}
												{#if attachment.url}
													<a href={attachment.url} target="_blank" rel="noopener noreferrer" class="attachment-link">
														{attachment.name || 'View Packet'}{attachment.pages ? ` (${attachment.pages})` : ''}
													</a>
												{/if}
											{/each}
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

	.compact-logo {
		position: absolute;
		top: 0;
		right: 1rem;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.1rem;
		font-weight: 700;
		color: var(--civic-blue);
		text-decoration: none;
		z-index: 10;
	}

	.compact-logo:hover {
		opacity: 0.8;
	}

	.breadcrumb {
		margin: 0.5rem 0 1.5rem 0;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		flex-wrap: wrap;
	}

	.back-link,
	.agenda-link {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
		color: var(--civic-blue);
		text-decoration: none;
		font-weight: 500;
		transition: all 0.2s;
	}

	.back-link:hover,
	.agenda-link:hover {
		color: var(--civic-accent);
		text-decoration: underline;
	}

	.agenda-link {
		padding: 0.4rem 0.75rem;
		border: 1.5px solid var(--civic-blue);
		border-radius: 6px;
		background: white;
	}

	.agenda-link:hover {
		background: var(--civic-blue);
		color: white;
		text-decoration: none;
		transform: translateY(-1px);
		box-shadow: 0 2px 4px rgba(79, 70, 229, 0.2);
	}

	.breadcrumb-separator {
		display: none;
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
		padding: 1rem 1.25rem;
		background: #f0fdf4;
		border: 1px solid #86efac;
		border-radius: 8px;
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
		border-radius: 8px;
		border: 1px solid var(--civic-border);
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

	.meeting-header-top {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 2rem;
	}

	.meeting-header-text {
		flex: 1;
	}

	.meeting-title {
		font-family: Georgia, 'Times New Roman', Times, serif;
		font-size: 1.8rem;
		color: var(--civic-dark);
		margin: 0 0 0.5rem 0;
		font-weight: 600;
		line-height: 1.3;
		-webkit-font-smoothing: antialiased;
		-moz-osx-font-smoothing: grayscale;
	}

	.meeting-date {
		font-family: Georgia, 'Times New Roman', Times, serif;
		color: var(--civic-gray);
		font-size: 1.05rem;
		-webkit-font-smoothing: antialiased;
		-moz-osx-font-smoothing: grayscale;
	}

	.document-link {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.75rem 1.25rem;
		background: var(--civic-blue);
		color: white;
		text-decoration: none;
		font-family: 'IBM Plex Mono', monospace;
		font-weight: 600;
		font-size: 0.9rem;
		border-radius: 8px;
		transition: all 0.2s;
		box-shadow: 0 2px 4px rgba(79, 70, 229, 0.2);
		flex-shrink: 0;
		align-self: flex-start;
	}

	.document-link:hover {
		background: var(--civic-accent);
		transform: translateY(-2px);
		box-shadow: 0 4px 8px rgba(79, 70, 229, 0.3);
	}

	.document-icon {
		font-size: 1rem;
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
		gap: 2rem;
	}

	.agenda-item {
		padding: 1.5rem;
		background: #fafafa;
		border-radius: 8px;
		border: 1px solid #e5e7eb;
	}

	.item-header {
		display: flex;
		align-items: flex-start;
		gap: 1rem;
		margin-bottom: 0.75rem;
	}

	.item-number {
		flex-shrink: 0;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 32px;
		height: 32px;
		background: var(--civic-blue);
		color: white;
		border-radius: 50%;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
		font-weight: 600;
	}

	.item-title {
		flex: 1;
		font-family: Georgia, 'Times New Roman', Times, serif;
		font-size: 1.15rem;
		font-weight: 600;
		color: var(--civic-dark);
		margin: 0;
		line-height: 1.4;
		-webkit-font-smoothing: antialiased;
		-moz-osx-font-smoothing: grayscale;
	}

	.item-topics {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
		margin-bottom: 0.75rem;
	}

	.item-topic-tag {
		display: inline-block;
		padding: 0.2rem 0.6rem;
		background: white;
		color: #64748b;
		border: 1px solid #e2e8f0;
		border-radius: 8px;
		font-size: 0.75rem;
		font-weight: 500;
		font-family: 'IBM Plex Mono', monospace;
	}

	.item-summary {
		font-family: Georgia, 'Times New Roman', Times, serif;
		line-height: 1.7;
		font-size: 1rem;
		color: #374151;
		margin-bottom: 0.75rem;
		-webkit-font-smoothing: antialiased;
		-moz-osx-font-smoothing: grayscale;
	}

	.item-summary :global(p) {
		margin: 0.75rem 0;
	}

	.item-summary :global(strong) {
		font-weight: 600;
		color: var(--civic-dark);
	}

	.item-summary :global(ul),
	.item-summary :global(ol) {
		margin: 0.75rem 0;
		padding-left: 1.5rem;
	}

	.item-summary :global(li) {
		margin: 0.4rem 0;
	}

	/* Collapse thinking trace by default, expand on click only */
	:global(.thinking-section) {
		position: relative;
		margin-bottom: 1rem;
		cursor: pointer;
	}

	:global(.thinking-section::before) {
		content: "💭 Thinking trace (click to expand)";
		display: block;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8rem;
		font-weight: 600;
		color: var(--civic-blue);
		padding: 0.75rem 1rem;
		background: white;
		border: 2px solid var(--civic-border);
		border-radius: 8px;
		margin-bottom: 0.75rem;
		transition: all 0.2s ease;
		box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
	}

	:global(.thinking-section:hover::before) {
		border-color: var(--civic-blue);
		box-shadow: 0 2px 6px rgba(79, 70, 229, 0.15);
		transform: translateY(-1px);
	}

	:global(.thinking-section.expanded::before) {
		content: "💭 Thinking trace (click to collapse)";
		border-color: var(--civic-blue);
		background: #eff6ff;
	}

	:global(.thinking-section > *) {
		display: none;
		opacity: 0;
		transform: translateY(-10px);
	}

	:global(.thinking-section.expanded > *) {
		display: block;
		animation: expandThinking 0.2s ease forwards;
		padding: 0.5rem;
		border-left: 2px solid var(--civic-blue);
		background: #f8fafc;
		margin-bottom: 0.5rem;
		border-radius: 4px;
	}

	@keyframes expandThinking {
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	.item-attachments-container {
		margin-top: 0.75rem;
	}

	.attachments-toggle {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.5rem 0.75rem;
		background: white;
		border: 1px solid #e5e7eb;
		border-radius: 6px;
		cursor: pointer;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8rem;
		color: #64748b;
		transition: all 0.2s;
		width: fit-content;
	}

	.attachments-toggle:hover {
		background: #f9fafb;
		border-color: #d1d5db;
	}

	.toggle-icon {
		font-size: 0.7rem;
		color: #94a3b8;
		transition: transform 0.2s;
	}

	.attachments-count {
		font-weight: 500;
	}

	.item-attachments {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin-top: 0.5rem;
		padding-left: 0.25rem;
	}

	.attachment-link {
		display: inline-block;
		padding: 0.4rem 0.75rem;
		background: white;
		color: var(--civic-blue);
		border: 1px solid #bae6fd;
		border-radius: 6px;
		text-decoration: none;
		font-size: 0.85rem;
		font-weight: 500;
		font-family: 'IBM Plex Mono', monospace;
		transition: all 0.2s;
	}

	.attachment-link:hover {
		background: #f0f9ff;
		border-color: #7dd3fc;
	}

	@media (max-width: 640px) {
		.container {
			width: 100%;
			padding: 1rem 0.75rem;
		}

		.compact-logo {
			font-size: 0.95rem;
			right: 0.75rem;
		}

		.breadcrumb {
			margin: 0.25rem 0 1rem 0;
			gap: 0.5rem;
		}

		.meeting-detail {
			padding: 1rem;
		}

		.back-link,
		.agenda-link {
			font-size: 0.75rem;
		}

		.meeting-header {
			margin-bottom: 1rem;
		}

		.meeting-header-top {
			flex-direction: column;
			gap: 1rem;
		}

		.document-link {
			width: auto;
			padding: 0.5rem 0.85rem;
			font-size: 0.8rem;
			align-self: flex-end;
		}

		.meeting-title {
			font-size: 1.3rem;
			word-wrap: break-word;
			overflow-wrap: break-word;
		}

		.meeting-date {
			font-size: 0.85rem;
			margin-top: 0.25rem;
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

		.agenda-item {
			padding: 0.75rem 0;
			border: none;
			background: transparent;
			box-shadow: none;
			border-bottom: 1px solid var(--civic-border);
			border-radius: 0;
		}

		.item-header {
			gap: 0.5rem;
		}

		.item-number {
			display: none;
		}

		.item-title {
			font-size: 0.95rem;
		}

		.item-topics {
			display: none;
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
	}
</style>