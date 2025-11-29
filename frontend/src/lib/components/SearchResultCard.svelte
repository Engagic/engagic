<script lang="ts">
	import { highlightMatch, sanitizeHtml } from '$lib/utils/sanitize';
	import { marked } from 'marked';
	import type { CitySearchResult, CitySearchItemResult, CitySearchMatterResult } from '$lib/api/types';
	import { generateMeetingSlug } from '$lib/utils/utils';

	interface Props {
		result: CitySearchResult;
		query: string;
		cityUrl: string;
	}

	let { result, query, cityUrl }: Props = $props();
	let expanded = $state(false);

	function formatDate(dateStr: string | undefined): string {
		if (!dateStr) return '';
		const date = new Date(dateStr);
		return date.toLocaleDateString('en-US', {
			year: 'numeric',
			month: 'short',
			day: 'numeric'
		});
	}

	function isItemResult(r: CitySearchResult): r is CitySearchItemResult {
		return r.type === 'item';
	}

	function isMatterResult(r: CitySearchResult): r is CitySearchMatterResult {
		return r.type === 'matter';
	}

	function getMeetingLink(): string {
		if (isItemResult(result)) {
			const meeting = {
				id: result.meeting_id,
				title: result.meeting_title || '',
				date: result.meeting_date || ''
			};
			const slug = generateMeetingSlug(meeting as any);
			return `/${cityUrl}/${slug}`;
		}
		return '';
	}

	function getHighlightedContext(): string {
		if (result.context?.includes('<mark>')) {
			return sanitizeHtml(result.context);
		}
		return highlightMatch(result.context, query);
	}

	function renderSummary(): string {
		if (isItemResult(result) && result.summary) {
			return marked(result.summary) as string;
		}
		if (isMatterResult(result) && result.canonical_summary) {
			return marked(result.canonical_summary) as string;
		}
		return '';
	}

	const topics = $derived.by(() => {
		if (isItemResult(result)) {
			return result.topics || [];
		}
		if (isMatterResult(result)) {
			return result.canonical_topics || [];
		}
		return [];
	});

	const attachments = $derived.by(() => {
		return result.attachments || [];
	});
</script>

<div class="result-card" class:expanded>
	<button
		class="result-card-header"
		onclick={() => expanded = !expanded}
		aria-expanded={expanded}
	>
		<div class="result-content">
			<!-- Legislative Context Bar -->
			<div class="legislative-context">
				{#if isItemResult(result)}
					{#if result.item_sequence}
						<span class="agenda-position">Item {result.item_sequence}</span>
					{/if}
					{#if result.agenda_number}
						<span class="agenda-number">{result.agenda_number}</span>
					{/if}
				{/if}
				{#if result.matter_file}
					<span class="matter-badge">
						{#if result.matter_type}{result.matter_type}: {/if}{result.matter_file}
					</span>
				{/if}
				{#if attachments.length > 0}
					<span class="attachment-count">
						{attachments.length} doc{attachments.length !== 1 ? 's' : ''}
					</span>
				{/if}
			</div>

			<!-- Highlighted context snippet -->
			<p class="result-context">
				{@html getHighlightedContext()}
			</p>

			<!-- Title -->
			{#if isItemResult(result) && result.item_title}
				<h4 class="result-title">{result.item_title}</h4>
			{:else if isMatterResult(result) && result.title}
				<h4 class="result-title">{result.title}</h4>
			{/if}

			<!-- Meta info -->
			<div class="result-meta">
				{#if isItemResult(result)}
					{#if result.meeting_date}
						<span class="result-date">{formatDate(result.meeting_date)}</span>
						<span class="separator">-</span>
					{/if}
					{#if result.meeting_title}
						<span class="meeting-title">{result.meeting_title}</span>
					{/if}
				{:else if isMatterResult(result)}
					{#if result.appearance_count && result.appearance_count > 1}
						<span class="appearance-count">{result.appearance_count} appearances</span>
						<span class="separator">-</span>
					{/if}
					<span class="result-date">Last seen: {formatDate(result.last_seen)}</span>
				{/if}
			</div>
		</div>

		<div class="expand-icon" aria-hidden="true">
			{expanded ? '-' : '+'}
		</div>
	</button>

	{#if expanded}
		<div class="result-expanded">
			<!-- Topics -->
			{#if topics.length > 0}
				<div class="topics-row">
					{#each topics as topic (topic)}
						<span class="topic-tag">{topic}</span>
					{/each}
				</div>
			{/if}

			<!-- Sponsors (matters only) -->
			{#if isMatterResult(result) && result.sponsors && result.sponsors.length > 0}
				<div class="sponsors-row">
					<span class="label">Sponsors:</span>
					{#each result.sponsors as sponsor (sponsor)}
						<span class="sponsor-name">{sponsor}</span>
					{/each}
				</div>
			{/if}

			<!-- Full Summary -->
			{#if renderSummary()}
				<div class="full-summary">
					{@html renderSummary()}
				</div>
			{:else}
				<div class="no-summary">
					No summary available.
				</div>
			{/if}

			<!-- Attachments -->
			{#if attachments.length > 0}
				<div class="attachments-section">
					<span class="label">Documents:</span>
					<div class="attachment-list">
						{#each attachments as attachment (attachment.url)}
							<a
								href={attachment.url}
								target="_blank"
								rel="noopener noreferrer"
								class="attachment-link"
								onclick={(e) => e.stopPropagation()}
							>
								{attachment.name || 'View Document'}
							</a>
						{/each}
					</div>
				</div>
			{/if}

			<!-- Actions -->
			<div class="result-actions">
				{#if isItemResult(result)}
					<a
						href={getMeetingLink()}
						class="action-link primary"
						onclick={(e) => e.stopPropagation()}
					>
						View Meeting
					</a>
					{#if result.agenda_url}
						<a
							href={result.agenda_url}
							target="_blank"
							rel="noopener noreferrer"
							class="action-link secondary"
							onclick={(e) => e.stopPropagation()}
						>
							Official Agenda
						</a>
					{/if}
				{/if}
			</div>
		</div>
	{/if}
</div>

<style>
	.result-card {
		background: var(--surface-card);
		border: 1px solid var(--border);
		border-radius: var(--radius-md);
		overflow: hidden;
		transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
	}

	.result-card.expanded {
		border-color: var(--color-action);
		box-shadow: 0 4px 12px rgba(249, 115, 22, 0.1);
	}

	.result-card-header {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 1rem;
		width: 100%;
		padding: 1rem;
		background: transparent;
		border: none;
		text-align: left;
		cursor: pointer;
		transition: background 0.1s ease;
	}

	.result-card-header:hover {
		background: var(--surface-secondary);
	}

	.result-content {
		flex: 1;
		min-width: 0;
	}

	.legislative-context {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
		align-items: center;
		margin-bottom: 0.75rem;
	}

	.agenda-position {
		display: inline-block;
		padding: 2px 8px;
		background: var(--color-action);
		color: white;
		border-radius: var(--radius-sm);
		font-size: var(--text-xs);
		font-weight: var(--font-semibold);
		font-family: var(--font-mono);
	}

	.agenda-number {
		display: inline-block;
		padding: 2px 8px;
		background: var(--surface-secondary);
		color: var(--text-secondary);
		border-radius: var(--radius-sm);
		font-size: var(--text-xs);
		font-weight: var(--font-medium);
		font-family: var(--font-mono);
	}

	.matter-badge {
		display: inline-block;
		padding: 2px 8px;
		background: var(--color-action-soft);
		border: 1px solid var(--color-action);
		color: var(--color-action-hover);
		border-radius: var(--radius-sm);
		font-size: var(--text-xs);
		font-weight: var(--font-semibold);
		font-family: var(--font-mono);
	}

	.attachment-count {
		display: inline-block;
		padding: 2px 8px;
		background: var(--surface-secondary);
		border: 1px solid var(--border);
		color: var(--text-secondary);
		border-radius: var(--radius-sm);
		font-size: var(--text-xs);
		font-weight: var(--font-medium);
	}

	.result-context {
		margin: 0 0 0.75rem 0;
		line-height: var(--leading-relaxed);
		color: var(--text);
		font-size: var(--text-base);
		font-family: var(--font-body);
	}

	.result-context :global(mark) {
		background: var(--color-action-soft);
		color: var(--color-action-hover);
		padding: 2px 4px;
		border-radius: var(--radius-sm);
		font-weight: var(--font-medium);
	}

	.result-title {
		font-size: var(--text-sm);
		font-weight: var(--font-medium);
		margin: 0 0 0.5rem 0;
		color: var(--text-secondary);
		font-family: var(--font-body);
	}

	.result-meta {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
		align-items: center;
		font-size: var(--text-sm);
		color: var(--text-muted);
	}

	.separator {
		color: var(--text-muted);
	}

	.meeting-title {
		color: var(--text-secondary);
	}

	.appearance-count {
		color: var(--color-action);
		font-weight: var(--font-medium);
	}

	.expand-icon {
		flex-shrink: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		width: 1.75rem;
		height: 1.75rem;
		background: var(--surface-secondary);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		color: var(--text);
		font-size: var(--text-lg);
		font-weight: bold;
		transition: all var(--transition-fast);
	}

	.result-card-header:hover .expand-icon {
		background: var(--color-action-soft);
		border-color: var(--color-action);
		color: var(--color-action);
	}

	/* Expanded section */
	.result-expanded {
		padding: 1rem;
		padding-top: 0.75rem;
		border-top: 1px solid var(--border);
		animation: slideDown 0.15s ease-out;
	}

	@keyframes slideDown {
		from {
			opacity: 0;
			transform: translateY(-8px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	.topics-row {
		display: flex;
		flex-wrap: wrap;
		gap: 0.375rem;
		margin-bottom: 0.75rem;
	}

	.topic-tag {
		display: inline-block;
		padding: 2px 8px;
		background: var(--color-action-soft);
		color: var(--color-action-hover);
		border-radius: 999px;
		font-size: var(--text-xs);
		font-weight: var(--font-medium);
		font-family: var(--font-mono);
	}

	.sponsors-row {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		align-items: center;
		margin-bottom: 0.75rem;
	}

	.label {
		font-size: var(--text-sm);
		font-weight: var(--font-medium);
		color: var(--text-secondary);
	}

	.sponsor-name {
		display: inline-block;
		padding: 2px 8px;
		background: var(--surface-secondary);
		border: 1px solid var(--border);
		color: var(--text-secondary);
		border-radius: var(--radius-sm);
		font-size: var(--text-xs);
		font-weight: var(--font-medium);
	}

	.full-summary {
		padding: 1rem;
		background: var(--surface-card);
		border-left: 3px solid var(--color-action);
		border-radius: var(--radius-sm);
		margin-bottom: 0.75rem;
		font-size: var(--text-sm);
		line-height: var(--leading-relaxed);
		color: var(--text);
		font-family: var(--font-body);
	}

	.full-summary :global(p) {
		margin: 0.5rem 0;
	}

	.full-summary :global(ul),
	.full-summary :global(ol) {
		margin: 0.5rem 0;
		padding-left: 1.5rem;
	}

	.full-summary :global(li) {
		margin: 0.25rem 0;
	}

	.full-summary :global(h1),
	.full-summary :global(h2),
	.full-summary :global(h3),
	.full-summary :global(h4),
	.full-summary :global(h5),
	.full-summary :global(h6) {
		font-family: var(--font-mono);
		font-weight: var(--font-semibold);
		color: var(--text);
		margin: 1rem 0 0.5rem 0;
		line-height: var(--leading-tight);
	}

	.full-summary :global(h1) { font-size: var(--text-lg); }
	.full-summary :global(h2) { font-size: var(--text-base); }
	.full-summary :global(h3) { font-size: var(--text-base); }
	.full-summary :global(h4),
	.full-summary :global(h5),
	.full-summary :global(h6) { font-size: var(--text-sm); }

	.full-summary :global(blockquote) {
		margin: 0.75rem 0;
		padding: 0.5rem 1rem;
		border-left: 3px solid var(--color-action);
		background: var(--surface-secondary);
		font-style: italic;
	}

	.full-summary :global(code) {
		font-family: var(--font-mono);
		font-size: 0.85em;
		background: var(--surface-secondary);
		padding: 0.15rem 0.35rem;
		border-radius: var(--radius-sm);
	}

	.full-summary :global(pre) {
		margin: 0.75rem 0;
		padding: 1rem;
		background: var(--surface-secondary);
		border-radius: var(--radius-sm);
		overflow-x: auto;
	}

	.full-summary :global(pre code) {
		background: none;
		padding: 0;
	}

	.no-summary {
		padding: 1rem;
		text-align: center;
		color: var(--text-muted);
		font-style: italic;
		background: var(--surface-secondary);
		border-radius: var(--radius-sm);
		margin-bottom: 0.75rem;
	}

	.attachments-section {
		margin-bottom: 0.75rem;
	}

	.attachment-list {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin-top: 0.375rem;
	}

	.attachment-link {
		display: inline-block;
		padding: 6px 12px;
		background: var(--surface-card);
		color: var(--color-action);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		text-decoration: none;
		font-size: var(--text-sm);
		font-weight: var(--font-medium);
		transition: all var(--transition-fast);
	}

	.attachment-link:hover {
		background: var(--surface-secondary);
		border-color: var(--color-action);
	}

	.result-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin-top: 0.75rem;
	}

	.action-link {
		display: inline-block;
		padding: 8px 16px;
		text-decoration: none;
		font-weight: var(--font-medium);
		font-size: var(--text-sm);
		border-radius: var(--radius-sm);
		transition: all var(--transition-fast);
	}

	.action-link.primary {
		background: var(--color-action);
		color: white;
	}

	.action-link.primary:hover {
		background: var(--color-action-hover);
	}

	.action-link.secondary {
		background: var(--surface-secondary);
		color: var(--color-action);
		border: 1px solid var(--border);
	}

	.action-link.secondary:hover {
		background: var(--color-action-soft);
		border-color: var(--color-action);
	}

	@media (max-width: 640px) {
		.result-card-header {
			padding: 0.875rem;
		}

		.result-expanded {
			padding: 0.875rem;
		}

		.result-context {
			font-size: 0.9rem;
		}

		.result-meta {
			font-size: 0.75rem;
		}
	}
</style>
