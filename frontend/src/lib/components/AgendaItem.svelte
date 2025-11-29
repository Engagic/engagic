<script lang="ts">
	import { marked } from 'marked';
	import type { AgendaItem as AgendaItemType, Meeting } from '$lib/api/types';
	import { generateFlyer } from '$lib/api/index';
	import { generateAnchorId } from '$lib/utils/anchor';
	import { buildItemShareLink } from '$lib/utils/utils';
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
	let linkCopied = $state(false);

	// Display agenda_number exactly as provided (already formatted), only add dot for sequence fallback
	const displayNumber = $derived(item.agenda_number || `${item.sequence}.`);

	// Generate anchor ID using shared utility (agenda_number > matter_file > item.id)
	const anchorId = $derived(generateAnchorId(item));

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

	async function copyShareLink() {
		if (linkCopied) return;

		try {
			const shareLink = buildItemShareLink(meeting.banana, meeting, item);

			if (navigator.clipboard && navigator.clipboard.writeText) {
				await navigator.clipboard.writeText(shareLink);
			} else {
				// Fallback for older browsers
				const textArea = document.createElement('textarea');
				textArea.value = shareLink;
				textArea.style.position = 'fixed';
				textArea.style.left = '-999999px';
				document.body.appendChild(textArea);
				textArea.select();
				document.execCommand('copy');
				document.body.removeChild(textArea);
			}

			linkCopied = true;
			setTimeout(() => {
				linkCopied = false;
			}, 2000);
		} catch (error) {
			console.error('Failed to copy link:', error);
			alert('Failed to copy link to clipboard');
		}
	}

	const titleParts = $derived(truncateTitle(item.title));
</script>

<div class="agenda-item" id={anchorId} data-expanded={isExpanded} data-has-summary={hasSummary}>
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
				<div class="item-title-row">
					<span class="item-number">{displayNumber}</span>
					<h3 class="item-title" data-truncated={titleParts.isTruncated}>
						{titleParts.main}
						{#if titleParts.remainder && !isExpanded}
							<span class="item-title-remainder">…</span>
						{:else if titleParts.remainder && isExpanded}
							{titleParts.remainder}
						{/if}
					</h3>
				</div>
				<div class="item-badges-row">
					{#if item.matter_file}
						{#if item.matter_id}
							<a
								href="/matter/{item.matter_id}"
								class="matter-badge matter-badge-link"
								title="View legislative journey for {item.matter_file}"
								onclick={(e) => e.stopPropagation()}
								data-sveltekit-preload-data="tap"
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
							data-sveltekit-preload-data="tap"
						>
							{item.matter.appearance_count} appearances
						</a>
					{/if}
					{#if !hasSummary}
						<span class="procedural-badge">Unprocessed</span>
					{/if}
					{#if item.topics && item.topics.length > 0}
						{#each item.topics.slice(0, 2) as topic (topic)}
							<span class="item-topic-tag-small" data-topic={topic.toLowerCase()}>{topic}</span>
						{/each}
						{#if item.topics.length > 2}
							<span class="topic-more">+{item.topics.length - 2} more</span>
						{/if}
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
					<button
						class="flyer-btn flyer-btn-share"
						disabled={linkCopied}
						onclick={(e) => {
							e.stopPropagation();
							copyShareLink();
						}}
						aria-label={linkCopied ? 'Link copied to clipboard' : 'Copy shareable link to this agenda item'}
					>
						{linkCopied ? '✓ Copied!' : '🔗 Share Link'}
					</button>
				</div>
			{/if}

			{#if item.attachments && item.attachments.length > 0}
				<div class="item-attachments-container">
					<div class="attachments-label">Attachments:</div>
					<div class="item-attachments">
						{#each item.attachments as attachment (attachment.url || attachment.name)}
							{#if attachment.url}
								<a href={attachment.url} target="_blank" rel="noopener noreferrer" class="attachment-link" onclick={(e) => e.stopPropagation()}>
									{attachment.name || 'View Packet'}
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
		background: var(--surface);
		border-radius: var(--radius-lg);
		border: 1px solid var(--border);
		border-left: 3px solid var(--border);
		box-shadow: 0 1px 3px var(--shadow-sm);
		transition: all var(--transition-normal);
		overflow: hidden;
	}

	.agenda-item[data-has-summary="true"] {
		border-left-color: var(--color-info);
	}

	.agenda-item[data-has-summary="false"] {
		border-left-color: var(--border);
		background: var(--surface-secondary);
		opacity: 0.75;
	}

	.agenda-item[data-expanded="true"] {
		border-left-color: var(--color-action);
	}

	.agenda-item[data-has-summary="false"][data-expanded="true"] {
		opacity: 1;
	}

	.agenda-item:hover {
		border-left-color: var(--color-action);
		box-shadow: 0 4px 12px var(--shadow-md);
	}

	.item-header-clickable {
		padding: 1rem 1.25rem;
		cursor: pointer;
		transition: background var(--transition-fast);
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

	.item-title-row {
		display: flex;
		align-items: baseline;
		gap: 0.5rem;
		margin-bottom: 0.5rem;
	}

	.item-badges-row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		flex-wrap: wrap;
		row-gap: 0.25rem;
	}

	.procedural-badge {
		display: inline-block;
		padding: 0.15rem 0.5rem;
		background: var(--badge-neutral-bg);
		color: var(--badge-neutral-text);
		border: 1px solid var(--badge-neutral-border);
		border-radius: var(--radius-sm);
		font-size: var(--text-xs);
		font-weight: var(--font-semibold);
		font-family: var(--font-mono);
		text-transform: uppercase;
		letter-spacing: 0.3px;
	}

	.matter-badge {
		display: inline-block;
		padding: 0.2rem 0.6rem;
		background: var(--badge-neutral-bg);
		color: var(--badge-neutral-text);
		border: 1px solid var(--badge-neutral-border);
		border-radius: var(--radius-sm);
		font-size: var(--text-xs);
		font-weight: var(--font-semibold);
		font-family: var(--font-mono);
		transition: all var(--transition-fast);
	}

	.matter-badge-link {
		text-decoration: none;
		cursor: pointer;
	}

	.matter-badge:hover,
	.matter-badge-link:hover {
		filter: brightness(0.95);
		transform: translateY(-1px);
	}

	.matter-type-badge {
		display: inline-block;
		padding: 0.2rem 0.6rem;
		background: var(--item-type-bg);
		color: var(--item-type-text);
		border: 1px solid var(--item-type-border);
		border-radius: var(--radius-sm);
		font-size: var(--text-xs);
		font-weight: var(--font-semibold);
		font-family: var(--font-mono);
		text-transform: capitalize;
		letter-spacing: 0.3px;
	}

	.sponsors-badge {
		display: inline-block;
		padding: 0.2rem 0.6rem;
		background: var(--badge-neutral-bg);
		color: var(--badge-neutral-text);
		border: 1px solid var(--badge-neutral-border);
		border-radius: var(--radius-sm);
		font-size: var(--text-xs);
		font-weight: var(--font-medium);
		font-family: var(--font-mono);
	}

	.matter-timeline-badge {
		display: inline-block;
		padding: 0.2rem 0.6rem;
		background: var(--badge-success-bg);
		color: var(--badge-success-text);
		border: 1px solid var(--badge-success-border);
		border-radius: var(--radius-sm);
		font-size: var(--text-xs);
		font-weight: var(--font-semibold);
		font-family: var(--font-mono);
		text-decoration: none;
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.matter-timeline-badge:hover {
		filter: brightness(0.95);
		transform: translateY(-1px);
	}

	.item-summary-preview {
		margin-top: 0.5rem;
		padding: 0.75rem;
		background: var(--bg-warm);
		border-left: 2px solid var(--border);
		border-radius: var(--radius-sm);
		font-family: var(--font-body);
		font-size: var(--text-sm);
		line-height: var(--leading-relaxed);
		color: var(--text-muted);
		font-style: italic;
	}

	.item-number {
		color: var(--text-muted);
		font-family: var(--font-body);
		font-size: var(--text-lg);
		font-weight: var(--font-medium);
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
		color: var(--text-muted);
		border-radius: var(--radius-sm);
		font-family: var(--font-mono);
		font-size: var(--text-xs);
		font-weight: var(--font-semibold);
	}

	.expand-icon {
		flex-shrink: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		width: 1.75rem;
		height: 1.75rem;
		background: transparent;
		border: 1.5px solid var(--border);
		border-radius: var(--radius-sm);
		color: var(--text-muted);
		font-size: var(--text-lg);
		font-weight: var(--font-normal);
		cursor: pointer;
		transition: all var(--transition-normal);
	}

	.expand-icon:hover {
		background: var(--color-action);
		border-color: var(--color-action);
		color: white;
	}

	.item-title {
		font-family: var(--font-body);
		font-size: var(--text-lg);
		font-weight: var(--font-medium);
		color: var(--text);
		margin: 0;
		line-height: var(--leading-snug);
		-webkit-font-smoothing: antialiased;
		-moz-osx-font-smoothing: grayscale;
		flex: 1;
		min-width: 0;
		word-wrap: break-word;
		overflow-wrap: break-word;
	}

	.item-title-remainder {
		color: var(--text-muted);
		font-weight: var(--font-normal);
	}

	.item-topic-tag-small {
		display: inline-block;
		padding: 0.25rem 0.65rem;
		background: var(--bg-warm);
		color: var(--text-muted);
		border: none;
		border-radius: var(--radius-sm);
		font-size: var(--text-xs);
		font-weight: var(--font-medium);
		font-family: var(--font-body);
		text-transform: uppercase;
		letter-spacing: 0.3px;
	}

	.topic-more {
		font-size: var(--text-xs);
		color: var(--text-muted);
		font-family: var(--font-body);
		font-weight: var(--font-medium);
	}

	.item-expanded-content {
		padding: 0 1.25rem 1.25rem 1.25rem;
		border-top: 1px solid var(--border);
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
		font-family: var(--font-body);
		line-height: var(--leading-relaxed);
		font-size: var(--text-base);
		color: var(--text);
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
		font-weight: var(--font-bold);
		color: var(--text);
	}

	.item-summary :global(h2) {
		font-size: var(--text-xs);
		font-weight: var(--font-semibold);
		color: var(--text);
		opacity: 0.4;
		margin: 1.5rem 0 0.75rem 0;
		text-transform: uppercase;
		letter-spacing: 1px;
		font-family: var(--font-mono);
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
		font-family: var(--font-mono);
		font-size: var(--text-sm);
		font-weight: var(--font-semibold);
		color: var(--text-muted);
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
		background: var(--surface);
		color: var(--color-action);
		border: 1.5px solid var(--border);
		border-radius: var(--radius-md);
		text-decoration: none;
		font-size: var(--text-sm);
		font-weight: var(--font-semibold);
		font-family: var(--font-mono);
		transition: all var(--transition-normal);
		box-shadow: 0 1px 2px var(--shadow-sm);
	}

	.attachment-link:hover {
		background: var(--surface-hover);
		border-color: var(--color-action);
		transform: translateY(-1px);
		box-shadow: 0 2px 6px var(--shadow-md);
	}

	.item-action-bar {
		margin-top: 1.5rem;
		padding-top: 1rem;
		border-top: 1px solid var(--border);
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
	}

	.flyer-btn {
		flex: 1;
		min-width: 140px;
		padding: 0.875rem 1.5rem;
		border: none;
		border-radius: var(--radius-md);
		font-family: var(--font-body);
		font-size: var(--text-sm);
		font-weight: var(--font-bold);
		cursor: pointer;
		transition: all var(--transition-normal);
		text-transform: uppercase;
		letter-spacing: 0.5px;
	}

	.flyer-btn-yes {
		background: var(--color-success);
		color: white;
	}

	.flyer-btn-yes:hover {
		filter: brightness(1.1);
		transform: translateY(-1px);
	}

	.flyer-btn-no {
		background: var(--color-error);
		color: white;
	}

	.flyer-btn-no:hover {
		filter: brightness(1.1);
		transform: translateY(-1px);
	}

	.flyer-btn-share {
		background: transparent;
		border: 1.5px solid var(--color-action);
		color: var(--color-action);
	}

	.flyer-btn-share:hover {
		background: var(--color-action);
		color: white;
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

		.item-title-row {
			gap: 0.35rem;
			margin-bottom: 0.4rem;
		}

		.item-number {
			font-size: 1rem;
		}

		.item-title {
			font-size: 1rem;
		}

		.item-badges-row {
			gap: 0.35rem;
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
