<script lang="ts">
	import { marked } from 'marked';
	import type { AgendaItem as AgendaItemType, Meeting } from '$lib/api/types';
	import { generateFlyer } from '$lib/api/index';
	import { generateAnchorId } from '$lib/utils/anchor';
	import { SvelteSet } from 'svelte/reactivity';

	interface Props {
		item: AgendaItemType;
		meeting: Meeting;
		expandedItems: SvelteSet<string>;
		expandedTitles: SvelteSet<string>;
		flyerGenerating: boolean;
		onFlyerGenerate: (generating: boolean) => void;
	}

	let { item, meeting, expandedItems, expandedTitles, flyerGenerating, onFlyerGenerate }: Props = $props();

	const isExpanded = $derived(expandedItems.has(item.id));
	const hasSummary = $derived(!!item.summary);

	// Display agenda_number exactly as provided (already formatted), only add dot for sequence fallback
	const displayNumber = $derived(item.agenda_number || `${item.sequence}.`);

	// Generate anchor ID using shared utility (agenda_number > matter_file > item.id)
	const anchorId = $derived(() => generateAnchorId(item));

	function toggleItem() {
		if (expandedItems.has(item.id)) {
			expandedItems.delete(item.id);
		} else {
			expandedItems.add(item.id);
		}
	}

	function truncateTitle(title: string): { main: string; remainder: string | null; isTruncated: boolean } {
		const semicolonIndex = title.indexOf(';');
		if (semicolonIndex !== -1 && semicolonIndex < title.length - 1) {
			const isTitleExpanded = expandedTitles.has(item.id);
			if (isTitleExpanded) {
				return { main: title, remainder: null, isTruncated: false };
			}
			const main = title.substring(0, semicolonIndex);
			const remainder = title.substring(semicolonIndex);
			return { main, remainder, isTruncated: true };
		}
		return { main: title, remainder: null, isTruncated: false };
	}

	async function generateSimpleFlyer(position: 'yes' | 'no') {
		if (flyerGenerating) return;

		onFlyerGenerate(true);

		const flyerWindow = window.open('', '_blank');

		if (!flyerWindow) {
			onFlyerGenerate(false);
			alert('Please allow pop-ups for this site to view flyers');
			return;
		}

		flyerWindow.document.write('<html><body style="font-family: system-ui; padding: 2rem; text-align: center;">Loading flyer...</body></html>');

		try {
			const apiPosition = position === 'yes' ? 'support' : 'oppose';
			const isDarkMode = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;

			const html = await generateFlyer({
				meeting_id: meeting.id,
				item_id: item.id,
				position: apiPosition,
				dark_mode: isDarkMode || false
			});

			flyerWindow.document.open();
			flyerWindow.document.write(html);
			flyerWindow.document.close();
		} catch (error) {
			console.error('Failed to generate flyer:', error);
			const errorMsg = error instanceof Error ? error.message : 'Unknown error';

			flyerWindow.document.open();
			flyerWindow.document.write(`
				<html>
				<body style="font-family: system-ui; padding: 2rem; text-align: center;">
					<h2>Failed to generate flyer</h2>
					<p>${errorMsg}</p>
					<p><button onclick="window.close()">Close</button></p>
				</body>
				</html>
			`);
			flyerWindow.document.close();
		} finally {
			onFlyerGenerate(false);
		}
	}

	const titleParts = $derived(truncateTitle(item.title));
</script>

<div class="agenda-item" id={anchorId()} data-expanded={isExpanded} data-has-summary={hasSummary}>
	<div
		class="item-header-clickable"
		role="button"
		tabindex="0"
		onclick={() => toggleItem()}
		onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleItem(); } }}
		aria-expanded={isExpanded}
		aria-label={isExpanded ? 'Collapse agenda item details' : 'Expand agenda item details'}
	>
		<div class="item-header">
			<div class="item-header-content">
				<div class="item-title-container">
					<span class="item-number">{displayNumber}</span>
					<h3 class="item-title" data-truncated={titleParts.isTruncated}>
						{titleParts.main}
						{#if titleParts.remainder && !isExpanded}
							<span class="item-title-remainder">…</span>
						{:else if titleParts.remainder && isExpanded}
							{titleParts.remainder}
						{/if}
					</h3>
					{#if item.matter_file}
						{#if item.matter_id}
							<a
								href="/matter/{item.matter_id}"
								class="matter-badge matter-badge-link"
								title="View legislative journey for {item.matter_file}"
								onclick={(e) => e.stopPropagation()}
								data-sveltekit-preload-data="hover"
							>
								{item.matter_file}
							</a>
						{:else}
							<span class="matter-badge" title="Matter: {item.matter_file}">
								{item.matter_file}
							</span>
						{/if}
					{/if}
					{#if item.matter_type}
						<span class="matter-type-badge" title="Type: {item.matter_type}">
							{item.matter_type}
						</span>
					{/if}
					{#if item.sponsors && item.sponsors.length > 0}
						<span class="sponsors-badge" title="Sponsors: {item.sponsors.join(', ')}">
							{item.sponsors.length === 1 ? item.sponsors[0] : `${item.sponsors.length} sponsors`}
						</span>
					{/if}
					{#if item.matter && item.matter.appearance_count && item.matter.appearance_count > 1}
						<a
							href="/matter/{item.matter.id}"
							class="matter-timeline-badge"
							title="View legislative journey across {item.matter.appearance_count} meetings"
							onclick={(e) => e.stopPropagation()}
							data-sveltekit-preload-data="hover"
						>
							{item.matter.appearance_count} appearances
						</a>
					{/if}
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
					{@const cleanText = item.summary!
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
				<div class="item-summary">
					{@html marked(item.summary)}
				</div>

				<div class="item-action-bar">
					<button
						class="flyer-btn flyer-btn-yes"
						disabled={flyerGenerating}
						onclick={(e) => {
							e.stopPropagation();
							generateSimpleFlyer('yes');
						}}
						aria-label={flyerGenerating ? 'Generating support flyer' : 'Generate flyer expressing support for this item'}
					>
						{flyerGenerating ? '⏳ Generating...' : '✓ Say Yes'}
					</button>
					<button
						class="flyer-btn flyer-btn-no"
						disabled={flyerGenerating}
						onclick={(e) => {
							e.stopPropagation();
							generateSimpleFlyer('no');
						}}
						aria-label={flyerGenerating ? 'Generating opposition flyer' : 'Generate flyer expressing opposition to this item'}
					>
						{flyerGenerating ? '⏳ Generating...' : '✗ Say No'}
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

<style>
	.agenda-item {
		background: var(--surface-primary);
		border-radius: 12px;
		border: 1px solid var(--border-primary);
		border-left: 4px solid var(--border-primary);
		box-shadow: 0 1px 3px var(--shadow-sm);
		transition: all 0.2s ease;
		overflow: hidden;
	}

	.agenda-item[data-has-summary="true"] {
		border-left-color: #93c5fd;
	}

	.agenda-item[data-has-summary="false"] {
		border-left-color: var(--border-primary);
		background: var(--surface-secondary);
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
		background: var(--surface-hover);
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
		row-gap: 0.5rem;
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

	.matter-badge {
		display: inline-block;
		padding: 0.2rem 0.6rem;
		background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
		color: #1e40af;
		border: 1.5px solid #3b82f6;
		border-radius: 12px;
		font-size: 0.7rem;
		font-weight: 700;
		font-family: 'IBM Plex Mono', monospace;
		letter-spacing: 0.5px;
		margin-left: 0.5rem;
		box-shadow: 0 1px 3px rgba(59, 130, 246, 0.2);
		transition: all 0.2s ease;
		cursor: help;
	}

	.matter-badge-link {
		text-decoration: none;
		cursor: pointer;
	}

	.matter-badge:hover,
	.matter-badge-link:hover {
		background: linear-gradient(135deg, #bfdbfe 0%, #93c5fd 100%);
		border-color: #2563eb;
		transform: translateY(-1px);
		box-shadow: 0 2px 6px rgba(59, 130, 246, 0.3);
	}

	.matter-type-badge {
		display: inline-block;
		padding: 0.2rem 0.6rem;
		background: #f3f4f6;
		color: #4b5563;
		border: 1px solid #d1d5db;
		border-radius: 12px;
		font-size: 0.65rem;
		font-weight: 600;
		font-family: 'IBM Plex Mono', monospace;
		text-transform: capitalize;
		letter-spacing: 0.3px;
		margin-left: 0.5rem;
	}

	.sponsors-badge {
		display: inline-block;
		padding: 0.2rem 0.6rem;
		background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
		color: #92400e;
		border: 1.5px solid #f59e0b;
		border-radius: 12px;
		font-size: 0.65rem;
		font-weight: 600;
		font-family: 'IBM Plex Mono', monospace;
		letter-spacing: 0.3px;
		margin-left: 0.5rem;
		cursor: help;
	}

	.matter-timeline-badge {
		display: inline-block;
		padding: 0.2rem 0.6rem;
		background: linear-gradient(135deg, #dcfce7 0%, #bbf7d0 100%);
		color: #065f46;
		border: 1.5px solid #10b981;
		border-radius: 12px;
		font-size: 0.65rem;
		font-weight: 700;
		font-family: 'IBM Plex Mono', monospace;
		letter-spacing: 0.3px;
		margin-left: 0.5rem;
		text-decoration: none;
		cursor: pointer;
		transition: all 0.2s ease;
		box-shadow: 0 1px 3px rgba(16, 185, 129, 0.2);
	}

	.matter-timeline-badge:hover {
		background: linear-gradient(135deg, #bbf7d0 0%, #86efac 100%);
		border-color: #059669;
		transform: translateY(-1px);
		box-shadow: 0 2px 6px rgba(16, 185, 129, 0.3);
	}

	.item-summary-preview {
		margin-top: 0.5rem;
		padding: 0.75rem;
		background: var(--surface-secondary);
		border-left: 2px solid var(--border-primary);
		border-radius: 4px;
		font-family: Georgia, 'Times New Roman', Times, serif;
		font-size: 0.9rem;
		line-height: 1.6;
		color: var(--text-secondary);
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
		background: var(--surface-secondary);
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
		border: 1.5px solid var(--border-primary);
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
		color: var(--text-primary);
		margin: 0;
		line-height: 1.45;
		-webkit-font-smoothing: antialiased;
		-moz-osx-font-smoothing: grayscale;
		flex: 1 1 auto;
		min-width: 0;
		word-wrap: break-word;
		overflow-wrap: break-word;
		hyphens: auto;
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
		background: var(--topic-bg, var(--surface-secondary));
		color: var(--topic-color, var(--text-secondary));
		border: 1.5px solid var(--topic-border, var(--border-primary));
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

	.item-expanded-content {
		padding: 0 1.25rem 1.25rem 1.25rem;
		border-top: 1px solid var(--border-primary);
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

	.item-summary {
		font-family: Georgia, 'Times New Roman', Times, serif;
		line-height: 1.7;
		font-size: 1rem;
		color: var(--text-primary);
		margin-bottom: 1.5rem;
		letter-spacing: 0.01em;
		-webkit-font-smoothing: antialiased;
		-moz-osx-font-smoothing: grayscale;
	}

	.item-summary :global(p) {
		margin: 1rem 0;
	}

	.item-summary :global(p:first-child) {
		margin-top: 0;
	}

	.item-summary :global(strong) {
		font-weight: 700;
		color: var(--text-primary);
	}

	.item-summary :global(h2) {
		font-size: 0.625rem;
		font-weight: 600;
		color: var(--text-primary);
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
		background: var(--surface-primary);
		color: var(--civic-blue);
		border: 1.5px solid var(--border-primary);
		border-radius: 8px;
		text-decoration: none;
		font-size: 0.85rem;
		font-weight: 600;
		font-family: 'IBM Plex Mono', monospace;
		transition: all 0.2s;
		box-shadow: 0 1px 2px var(--shadow-sm);
	}

	.attachment-link:hover {
		background: var(--surface-hover);
		border-color: var(--civic-blue);
		transform: translateY(-1px);
		box-shadow: 0 2px 6px var(--shadow-md);
	}

	.item-action-bar {
		margin-top: 1.5rem;
		padding-top: 1rem;
		border-top: 1px solid var(--border-primary);
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

	.flyer-btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
		transform: none;
	}

	.flyer-btn:disabled:hover {
		transform: none;
		box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
	}

	@media (max-width: 640px) {
		.item-header-clickable {
			padding: 0.75rem 1rem;
		}

		.item-expanded-content {
			padding: 0 1rem 1rem 1rem;
		}

		.item-header {
			gap: 0.5rem;
		}

		.item-title-container {
			display: grid;
			grid-template-columns: auto 1fr;
			grid-template-rows: auto auto;
			gap: 0.35rem 0.5rem;
			align-items: baseline;
		}

		.item-number {
			font-size: 1rem;
			grid-column: 1;
			grid-row: 1;
		}

		.item-title {
			font-size: 1rem;
			grid-column: 2;
			grid-row: 1;
		}

		.item-title-container > *:not(.item-number):not(.item-title) {
			grid-column: 1 / -1;
			grid-row: 2;
			margin-left: 0;
			justify-self: flex-start;
		}

		.item-title-container > .matter-badge,
		.item-title-container > .matter-badge-link,
		.item-title-container > .matter-type-badge,
		.item-title-container > .sponsors-badge,
		.item-title-container > .matter-timeline-badge,
		.item-title-container > .procedural-badge {
			display: inline-block;
			margin-right: 0.35rem;
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

		.item-topic-tag-small {
			font-size: 0.65rem;
			padding: 0.2rem 0.5rem;
		}

		.item-summary {
			font-size: 0.9rem;
		}

		.attachment-link {
			font-size: 0.8rem;
			padding: 0.35rem 0.65rem;
		}

		.procedural-badge {
			font-size: 0.6rem;
			padding: 0.12rem 0.4rem;
		}

		.matter-badge,
		.matter-badge-link {
			font-size: 0.65rem;
			padding: 0.18rem 0.5rem;
		}

		.matter-type-badge {
			font-size: 0.6rem;
			padding: 0.18rem 0.5rem;
		}

		.sponsors-badge {
			font-size: 0.6rem;
			padding: 0.18rem 0.5rem;
		}

		.matter-timeline-badge {
			font-size: 0.6rem;
			padding: 0.18rem 0.5rem;
		}

		.item-summary-preview {
			font-size: 0.85rem;
			padding: 0.6rem;
			margin-top: 0.4rem;
		}

		.flyer-btn {
			font-size: 0.85rem;
			padding: 0.75rem 1.25rem;
		}
	}
</style>
