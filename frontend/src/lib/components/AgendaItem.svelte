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
	const displayNumber = $derived(item.agenda_number || `${item.sequence}.`);
	const anchorId = $derived(() => generateAnchorId(item));

	function toggleItem() {
		if (expandedItems.has(item.id)) {
			expandedItems.delete(item.id);
		} else {
			expandedItems.add(item.id);
		}
	}

	async function generateSimpleFlyer(position: 'yes' | 'no') {
		if (flyerGenerating) return;
		onFlyerGenerate(true);
		const flyerWindow = window.open('', '_blank');
		if (!flyerWindow) {
			onFlyerGenerate(false);
			alert('POPUP BLOCKED - ALLOW POPUPS TO GENERATE FLYER');
			return;
		}
		flyerWindow.document.write('<html><body style="font-family: monospace; padding: 2rem; text-align: center; background: #000; color: #0f0;">GENERATING FLYER...</body></html>');
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
			console.error('FLYER GENERATION FAILED:', error);
			const errorMsg = error instanceof Error ? error.message : 'UNKNOWN ERROR';
			flyerWindow.document.open();
			flyerWindow.document.write(`
				<html>
				<body style="font-family: monospace; padding: 2rem; background: #ff0000; color: #000;">
					<h2>⚠ FLYER GENERATION FAILED</h2>
					<p>${errorMsg}</p>
					<button onclick="window.close()" style="padding: 1rem; font-family: monospace; background: #000; color: #fff; border: 4px solid #fff; cursor: pointer; font-size: 1.2rem; margin-top: 2rem;">CLOSE</button>
				</body>
				</html>
			`);
			flyerWindow.document.close();
		} finally {
			onFlyerGenerate(false);
		}
	}
</script>

<div class="brutalist-agenda-item" id={anchorId()} data-expanded={isExpanded} data-has-summary={hasSummary}>
	<!-- Header - Always visible, clickable -->
	<div
		class="item-header-zone"
		role="button"
		tabindex="0"
		onclick={() => toggleItem()}
		onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleItem(); } }}
		aria-expanded={isExpanded}
		aria-label={isExpanded ? 'COLLAPSE ITEM' : 'EXPAND ITEM'}
	>
		<div class="item-number-block">
			<span class="item-number">{displayNumber}</span>
		</div>

		<div class="item-content-block">
			<h3 class="item-title">{item.title}</h3>

			<!-- Metadata badges -->
			<div class="item-metadata">
				{#if item.matter_file}
					{#if item.matter_id}
						<a
							href="/matter/{item.matter_id}"
							class="meta-badge meta-matter"
							title="LEGISLATIVE JOURNEY: {item.matter_file}"
							onclick={(e) => e.stopPropagation()}
							data-sveltekit-preload-data="hover"
						>
							{item.matter_file}
						</a>
					{:else}
						<span class="meta-badge meta-matter" title="MATTER: {item.matter_file}">
							{item.matter_file}
						</span>
					{/if}
				{/if}

				{#if item.matter_type}
					<span class="meta-badge meta-type">{item.matter_type}</span>
				{/if}

				{#if item.sponsors && item.sponsors.length > 0}
					<span class="meta-badge meta-sponsors">
						{item.sponsors.length === 1 ? item.sponsors[0] : `${item.sponsors.length} SPONSORS`}
					</span>
				{/if}

				{#if item.matter && item.matter.appearance_count && item.matter.appearance_count > 1}
					<a
						href="/matter/{item.matter.id}"
						class="meta-badge meta-timeline"
						title="TRACKED ACROSS {item.matter.appearance_count} MEETINGS"
						onclick={(e) => e.stopPropagation()}
						data-sveltekit-preload-data="hover"
					>
						{item.matter.appearance_count} APPEARANCES
					</a>
				{/if}

				{#if !hasSummary}
					<span class="meta-badge meta-unprocessed">UNPROCESSED</span>
				{/if}
			</div>

			<!-- Topics preview -->
			{#if item.topics && item.topics.length > 0}
				<div class="item-topics-inline">
					{#each item.topics.slice(0, 3) as topic}
						<span class="topic-chip" data-topic={topic.toLowerCase()}>{topic}</span>
					{/each}
					{#if item.topics.length > 3}
						<span class="topic-more">+{item.topics.length - 3}</span>
					{/if}
				</div>
			{/if}
		</div>

		<!-- Right side: attachments count + expand button -->
		<div class="item-controls">
			{#if item.attachments && item.attachments.length > 0}
				<div class="attachment-count">
					<span class="count-label">FILES</span>
					<span class="count-value">{item.attachments.length}</span>
				</div>
			{/if}
			<button class="expand-button" aria-label={isExpanded ? 'COLLAPSE' : 'EXPAND'}>
				{isExpanded ? '−' : '+'}
			</button>
		</div>
	</div>

	<!-- Expanded content -->
	{#if isExpanded}
		<div class="item-expanded-zone">
			{#if item.summary}
				<div class="item-summary-block">
					<div class="summary-label">SUMMARY</div>
					<div class="summary-content">
						{@html marked(item.summary)}
					</div>
				</div>

				<!-- Action buttons -->
				<div class="item-action-panel">
					<div class="action-label">TAKE ACTION</div>
					<div class="action-buttons">
						<button
							class="action-btn action-support"
							disabled={flyerGenerating}
							onclick={(e) => {
								e.stopPropagation();
								generateSimpleFlyer('yes');
							}}
							aria-label={flyerGenerating ? 'GENERATING SUPPORT FLYER' : 'GENERATE SUPPORT FLYER'}
						>
							<span class="btn-icon">✓</span>
							<span class="btn-text">{flyerGenerating ? 'GENERATING...' : 'SUPPORT'}</span>
						</button>
						<button
							class="action-btn action-oppose"
							disabled={flyerGenerating}
							onclick={(e) => {
								e.stopPropagation();
								generateSimpleFlyer('no');
							}}
							aria-label={flyerGenerating ? 'GENERATING OPPOSITION FLYER' : 'GENERATE OPPOSITION FLYER'}
						>
							<span class="btn-icon">✗</span>
							<span class="btn-text">{flyerGenerating ? 'GENERATING...' : 'OPPOSE'}</span>
						</button>
					</div>
				</div>
			{/if}

			<!-- Attachments -->
			{#if item.attachments && item.attachments.length > 0}
				<div class="item-attachments-block">
					<div class="attachments-label">ATTACHED DOCUMENTS</div>
					<div class="attachments-grid">
						{#each item.attachments as attachment}
							{#if attachment.url}
								<a
									href={attachment.url}
									target="_blank"
									rel="noopener noreferrer"
									class="attachment-link"
									onclick={(e) => e.stopPropagation()}
								>
									<span class="attachment-icon">📄</span>
									<span class="attachment-name">{attachment.name || 'DOCUMENT'}</span>
									{#if attachment.pages}
										<span class="attachment-pages">{attachment.pages}</span>
									{/if}
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
	/* ===================================================================
	   BRUTALIST AGENDA ITEM - DATA BLOCK AESTHETIC
	   =================================================================== */

	.brutalist-agenda-item {
		background: var(--surface-primary, #0a0a0a);
		border: 4px solid var(--border-primary, #333);
		border-left: 8px solid var(--border-primary, #333);
		margin-bottom: 0;
		transition: all 0.2s ease;
		position: relative;
	}

	.brutalist-agenda-item[data-has-summary="true"] {
		border-left-color: var(--color-accent, #ffff00);
	}

	.brutalist-agenda-item[data-expanded="true"] {
		border-color: var(--color-accent, #ffff00);
		box-shadow: 0 0 0 4px rgba(255, 255, 0, 0.2);
	}

	.brutalist-agenda-item[data-has-summary="false"] {
		opacity: 0.6;
	}

	.brutalist-agenda-item[data-has-summary="false"][data-expanded="true"] {
		opacity: 1;
	}

	/* Header Zone */
	.item-header-zone {
		display: flex;
		align-items: flex-start;
		gap: 1rem;
		padding: 1.5rem;
		cursor: pointer;
		transition: background 0.1s ease;
		position: relative;
	}

	.item-header-zone::before {
		content: '>';
		position: absolute;
		left: 0.5rem;
		top: 50%;
		transform: translateY(-50%);
		color: var(--color-accent, #ffff00);
		font-size: 2rem;
		font-weight: 700;
		opacity: 0;
		transition: opacity 0.2s ease;
		font-family: var(--font-mono, monospace);
	}

	.item-header-zone:hover {
		background: var(--surface-secondary, #1a1a1a);
	}

	.item-header-zone:hover::before {
		opacity: 1;
	}

	/* Number Block */
	.item-number-block {
		flex-shrink: 0;
		min-width: 4rem;
		padding: 0.5rem 1rem;
		background: var(--surface-tertiary, #2a2a2a);
		border: 2px solid var(--border-primary, #333);
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.item-number {
		font-family: var(--font-display, 'Bebas Neue', sans-serif);
		font-size: 2rem;
		font-weight: 700;
		color: var(--color-accent, #ffff00);
		line-height: 1;
		letter-spacing: 0.05em;
	}

	/* Content Block */
	.item-content-block {
		flex: 1;
		min-width: 0;
	}

	.item-title {
		font-family: var(--font-mono, 'IBM Plex Mono', monospace);
		font-size: 1.1rem;
		font-weight: 700;
		color: var(--color-text, #fff);
		margin: 0 0 1rem 0;
		line-height: 1.4;
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}

	/* Metadata Badges */
	.item-metadata {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin-bottom: 0.75rem;
	}

	.meta-badge {
		display: inline-block;
		padding: 0.35rem 0.75rem;
		font-family: var(--font-mono, monospace);
		font-size: 0.7rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		border: 2px solid;
		transition: all 0.2s ease;
		text-decoration: none;
	}

	.meta-matter {
		background: transparent;
		color: var(--color-accent, #ffff00);
		border-color: var(--color-accent, #ffff00);
	}

	.meta-matter:hover {
		background: var(--color-accent, #ffff00);
		color: var(--color-bg, #000);
	}

	.meta-type {
		background: transparent;
		color: var(--color-text-dim, #999);
		border-color: var(--border-primary, #333);
	}

	.meta-sponsors {
		background: transparent;
		color: var(--color-info, #0ff);
		border-color: var(--color-info, #0ff);
	}

	.meta-timeline {
		background: transparent;
		color: var(--color-success, #0f0);
		border-color: var(--color-success, #0f0);
		text-decoration: none;
	}

	.meta-timeline:hover {
		background: var(--color-success, #0f0);
		color: var(--color-bg, #000);
	}

	.meta-unprocessed {
		background: var(--color-alert, #f00);
		color: var(--color-bg, #000);
		border-color: var(--color-alert, #f00);
	}

	/* Topics */
	.item-topics-inline {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
		align-items: center;
	}

	.topic-chip {
		display: inline-block;
		padding: 0.25rem 0.6rem;
		background: var(--surface-tertiary, #2a2a2a);
		color: var(--color-text, #fff);
		border: 2px solid var(--border-primary, #333);
		font-size: 0.65rem;
		font-weight: 700;
		font-family: var(--font-mono, monospace);
		text-transform: uppercase;
		letter-spacing: 0.1em;
	}

	.topic-more {
		font-size: 0.7rem;
		color: var(--color-text-dim, #999);
		font-family: var(--font-mono, monospace);
		font-weight: 700;
	}

	/* Controls */
	.item-controls {
		flex-shrink: 0;
		display: flex;
		align-items: flex-start;
		gap: 1rem;
	}

	.attachment-count {
		display: flex;
		flex-direction: column;
		align-items: center;
		padding: 0.5rem;
		background: var(--surface-tertiary, #2a2a2a);
		border: 2px solid var(--border-primary, #333);
		min-width: 4rem;
	}

	.count-label {
		font-family: var(--font-mono, monospace);
		font-size: 0.6rem;
		font-weight: 700;
		color: var(--color-text-dim, #999);
		letter-spacing: 0.1em;
		margin-bottom: 0.25rem;
	}

	.count-value {
		font-family: var(--font-display, 'Bebas Neue', sans-serif);
		font-size: 1.5rem;
		font-weight: 700;
		color: var(--color-accent, #ffff00);
		line-height: 1;
	}

	.expand-button {
		width: 3rem;
		height: 3rem;
		background: var(--surface-tertiary, #2a2a2a);
		border: 2px solid var(--border-accent, #ffff00);
		color: var(--color-accent, #ffff00);
		font-size: 2rem;
		font-weight: 700;
		cursor: pointer;
		transition: all 0.2s ease;
		font-family: var(--font-mono, monospace);
		line-height: 1;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.expand-button:hover {
		background: var(--color-accent, #ffff00);
		color: var(--color-bg, #000);
		box-shadow: 4px 4px 0 rgba(255, 255, 0, 0.3);
		transform: translate(-2px, -2px);
	}

	/* Expanded Zone */
	.item-expanded-zone {
		border-top: 4px solid var(--border-accent, #ffff00);
		animation: expandReveal 0.3s ease-out;
	}

	@keyframes expandReveal {
		from {
			opacity: 0;
			transform: scaleY(0.9);
		}
		to {
			opacity: 1;
			transform: scaleY(1);
		}
	}

	/* Summary Block */
	.item-summary-block {
		padding: 2rem 1.5rem;
		background: var(--surface-secondary, #1a1a1a);
		position: relative;
	}

	.summary-label {
		position: absolute;
		top: -0.6rem;
		left: 1.5rem;
		background: var(--color-bg, #000);
		padding: 0 0.75rem;
		font-family: var(--font-mono, monospace);
		font-size: 0.7rem;
		font-weight: 700;
		color: var(--color-accent, #ffff00);
		letter-spacing: 0.2em;
	}

	.summary-content {
		font-family: var(--font-body, monospace);
		line-height: 1.8;
		font-size: 1rem;
		color: var(--color-text, #fff);
		letter-spacing: 0.02em;
	}

	.summary-content :global(p) {
		margin: 1rem 0;
	}

	.summary-content :global(strong) {
		font-weight: 700;
		color: var(--color-accent, #ffff00);
	}

	.summary-content :global(h2) {
		font-size: 0.7rem;
		font-weight: 700;
		color: var(--color-text-dim, #999);
		margin: 1.5rem 0 0.75rem 0;
		text-transform: uppercase;
		letter-spacing: 0.15em;
		font-family: var(--font-mono, monospace);
	}

	.summary-content :global(ul),
	.summary-content :global(ol) {
		margin: 1rem 0;
		padding-left: 2rem;
	}

	.summary-content :global(li) {
		margin: 0.5rem 0;
	}

	/* Action Panel */
	.item-action-panel {
		padding: 1.5rem;
		background: var(--surface-primary, #0a0a0a);
		border-top: 2px solid var(--border-primary, #333);
		position: relative;
	}

	.action-label {
		position: absolute;
		top: -0.6rem;
		left: 1.5rem;
		background: var(--color-bg, #000);
		padding: 0 0.75rem;
		font-family: var(--font-mono, monospace);
		font-size: 0.7rem;
		font-weight: 700;
		color: var(--color-text-dim, #999);
		letter-spacing: 0.2em;
	}

	.action-buttons {
		display: flex;
		gap: 1rem;
		margin-top: 0.5rem;
	}

	.action-btn {
		flex: 1;
		padding: 1rem 1.5rem;
		border: 4px solid;
		cursor: pointer;
		transition: all 0.2s ease;
		font-family: var(--font-display, 'Bebas Neue', sans-serif);
		font-size: 1.5rem;
		font-weight: 700;
		letter-spacing: 0.1em;
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.75rem;
		position: relative;
	}

	.action-support {
		background: transparent;
		color: var(--color-success, #0f0);
		border-color: var(--color-success, #0f0);
	}

	.action-support:hover {
		background: var(--color-success, #0f0);
		color: var(--color-bg, #000);
		box-shadow: 8px 8px 0 rgba(0, 255, 0, 0.3);
		transform: translate(-4px, -4px);
	}

	.action-oppose {
		background: transparent;
		color: var(--color-alert, #f00);
		border-color: var(--color-alert, #f00);
	}

	.action-oppose:hover {
		background: var(--color-alert, #f00);
		color: var(--color-bg, #000);
		box-shadow: 8px 8px 0 rgba(255, 0, 0, 0.3);
		transform: translate(-4px, -4px);
	}

	.action-btn:active {
		transform: translate(0, 0);
		box-shadow: 2px 2px 0 rgba(255, 255, 255, 0.3);
	}

	.action-btn:disabled {
		opacity: 0.4;
		cursor: not-allowed;
		transform: none;
	}

	.action-btn:disabled:hover {
		transform: none;
		box-shadow: none;
		background: transparent;
	}

	.btn-icon {
		font-size: 2rem;
		line-height: 1;
	}

	.btn-text {
		line-height: 1;
	}

	/* Attachments Block */
	.item-attachments-block {
		padding: 1.5rem;
		background: var(--surface-tertiary, #2a2a2a);
		border-top: 2px solid var(--border-primary, #333);
		position: relative;
	}

	.attachments-label {
		position: absolute;
		top: -0.6rem;
		left: 1.5rem;
		background: var(--color-bg, #000);
		padding: 0 0.75rem;
		font-family: var(--font-mono, monospace);
		font-size: 0.7rem;
		font-weight: 700;
		color: var(--color-text-dim, #999);
		letter-spacing: 0.2em;
	}

	.attachments-grid {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		margin-top: 0.5rem;
	}

	.attachment-link {
		display: flex;
		align-items: center;
		gap: 1rem;
		padding: 0.75rem 1rem;
		background: var(--surface-primary, #0a0a0a);
		color: var(--color-text, #fff);
		border: 2px solid var(--border-primary, #333);
		text-decoration: none;
		font-size: 0.9rem;
		font-weight: 700;
		font-family: var(--font-mono, monospace);
		transition: all 0.2s ease;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.attachment-link:hover {
		border-color: var(--color-accent, #ffff00);
		background: var(--surface-secondary, #1a1a1a);
		padding-left: 1.5rem;
	}

	.attachment-icon {
		font-size: 1.2rem;
	}

	.attachment-name {
		flex: 1;
	}

	.attachment-pages {
		color: var(--color-text-dim, #999);
		font-size: 0.8rem;
	}

	/* Responsive */
	@media (max-width: 768px) {
		.item-header-zone {
			padding: 1rem;
		}

		.item-number-block {
			min-width: 3rem;
			padding: 0.5rem;
		}

		.item-number {
			font-size: 1.5rem;
		}

		.item-title {
			font-size: 1rem;
		}

		.item-controls {
			flex-direction: column;
			gap: 0.5rem;
		}

		.attachment-count {
			min-width: 3rem;
		}

		.expand-button {
			width: 2.5rem;
			height: 2.5rem;
			font-size: 1.5rem;
		}

		.action-buttons {
			flex-direction: column;
		}

		.action-btn {
			font-size: 1.2rem;
		}
	}
</style>
