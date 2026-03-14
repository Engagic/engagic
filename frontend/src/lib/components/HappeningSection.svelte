<script lang="ts">
	import type { HappeningItem } from '$lib/api/types';
	import { formatMeetingDate, extractTime } from '$lib/utils/date-utils';
	import { generateAnchorId } from '$lib/utils/anchor';
	import { generateMeetingSlug } from '$lib/utils/utils';

	interface Props {
		items: HappeningItem[];
		cityUrl: string;
	}

	let { items, cityUrl }: Props = $props();
	let showAll = $state(false);

	const visibleItems = $derived(showAll ? items : items.slice(0, 1));
	const hiddenCount = $derived(items.length - 1);

	function truncateTitle(title: string | null, maxLen: number = 120): string {
		if (!title) return 'Agenda Item';
		if (title.length <= maxLen) return title;
		return title.substring(0, maxLen).trim() + '…';
	}

	function getItemLink(item: HappeningItem): string {
		const slug = generateMeetingSlug({
			id: item.meeting_id,
			title: item.meeting_title || '',
			date: item.meeting_date || '',
			banana: ''
		} as Parameters<typeof generateMeetingSlug>[0]);
		const anchor = generateAnchorId({
			id: item.item_id,
			agenda_number: item.agenda_number || undefined,
			matter_file: item.matter_file || undefined
		});
		return `/${cityUrl}/${slug}?item=${anchor}`;
	}

	function getMeetingDateTime(item: HappeningItem): string {
		if (!item.meeting_date) return 'Date TBD';
		const dateStr = formatMeetingDate(item.meeting_date);
		const timeStr = extractTime(item.meeting_date);
		return timeStr ? `${dateStr} at ${timeStr}` : dateStr;
	}

</script>

{#if items.length > 0}
	<section class="happening-section">
		<div class="happening-header">
			<h2 class="happening-title">Happening This Week</h2>
			<span class="happening-subtitle">Important items where your voice can make a difference</span>
		</div>

		<div class="happening-list">
			{#each visibleItems as item (item.item_id)}
				<a href={getItemLink(item)} class="happening-card">
					<div class="rank-badge">#{item.rank}</div>
					<div class="card-content">
						<div class="card-meta">
							{#if item.matter_file}
								<span class="matter-badge">{item.matter_file}</span>
							{/if}
							<span class="meeting-badge">{item.meeting_title || 'Meeting'}</span>
							<span class="meeting-datetime">{getMeetingDateTime(item)}</span>
						</div>
						<div class="item-title">{truncateTitle(item.item_title)}</div>
						{#if item.reason}
							<div class="reason">{item.reason}</div>
						{/if}
					</div>
					<span class="view-arrow">→</span>
				</a>
			{/each}
		</div>

		{#if hiddenCount > 0}
			<button class="show-more-btn" onclick={() => showAll = !showAll}>
				{showAll ? 'Show less' : `${hiddenCount} more important item${hiddenCount === 1 ? '' : 's'} this week`}
			</button>
		{/if}
	</section>
{/if}

<style>
	.happening-section {
		margin-bottom: 2rem;
		padding: 0;
		background: transparent;
		border: none;
	}

	.happening-header {
		margin-bottom: 0.75rem;
		display: flex;
		align-items: baseline;
		gap: 0.75rem;
		flex-wrap: wrap;
		padding-bottom: 0.5rem;
		border-bottom: 2px solid var(--text-primary);
	}

	.happening-title {
		font-family: var(--font-body);
		font-size: 0.7rem;
		font-weight: 700;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--civic-gray);
		margin: 0;
	}

	.happening-subtitle {
		font-family: var(--font-body);
		font-size: 0.7rem;
		color: var(--civic-gray);
		opacity: 0.7;
	}

	.happening-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.happening-card {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 0.75rem 0;
		background: transparent;
		border: none;
		border-bottom: 1px solid var(--border-primary);
		transition: padding-left 0.2s ease;
		text-decoration: none;
		color: inherit;
	}

	.happening-card:hover {
		padding-left: 6px;
	}

	.rank-badge {
		flex-shrink: 0;
		width: 1.75rem;
		height: 1.75rem;
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--civic-blue);
		color: white;
		font-family: var(--font-mono);
		font-size: 0.75rem;
		font-weight: 700;
		border-radius: 50%;
	}

	.card-content {
		flex: 1;
		min-width: 0;
	}

	.card-meta {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.4rem;
		margin-bottom: 0.25rem;
	}

	.matter-badge {
		font-family: var(--font-mono);
		font-size: 0.7rem;
		font-weight: 700;
		color: var(--badge-matter-text);
		background: var(--badge-matter-bg);
		border: 1px solid var(--badge-matter-border);
		padding: 0.1rem 0.35rem;
		border-radius: var(--radius-xs);
	}

	.meeting-badge {
		font-family: var(--font-mono);
		font-size: 0.7rem;
		font-weight: 500;
		color: var(--civic-gray);
	}

	.meeting-datetime {
		font-family: var(--font-mono);
		font-size: 0.7rem;
		color: var(--civic-gray);
		opacity: 0.8;
	}

	.meeting-badge::before {
		content: '·';
		margin-right: 0.4rem;
		color: var(--civic-gray);
		opacity: 0.5;
	}

	.meeting-datetime::before {
		content: '·';
		margin-right: 0.4rem;
		color: var(--civic-gray);
		opacity: 0.5;
	}

	.item-title {
		font-family: var(--font-display);
		font-size: 0.95rem;
		font-weight: 400;
		line-height: 1.3;
		color: var(--text-primary);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.reason {
		font-family: var(--font-mono);
		font-size: 0.75rem;
		color: var(--civic-gray);
		margin-top: 0.2rem;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.view-arrow {
		flex-shrink: 0;
		color: var(--civic-gray);
		font-size: 1rem;
		opacity: 0.5;
		transition: opacity var(--transition-normal);
	}

	.happening-card:hover .view-arrow {
		opacity: 1;
		color: var(--civic-blue);
	}

	.show-more-btn {
		display: block;
		width: 100%;
		margin-top: 0.5rem;
		padding: 0.4rem 0.75rem;
		background: transparent;
		border: 1px dashed var(--border-primary);
		border-radius: var(--radius-md);
		font-family: var(--font-mono);
		font-size: 0.8rem;
		font-weight: 500;
		color: var(--civic-gray);
		cursor: pointer;
		transition: all var(--transition-normal);
		text-align: center;
	}

	.show-more-btn:hover {
		color: var(--civic-blue);
		border-color: var(--civic-blue);
	}

	@media (max-width: 640px) {
		.happening-section {
			padding: 0.75rem;
		}

		.happening-header {
			flex-direction: column;
			gap: 0.25rem;
		}

		.item-title {
			white-space: normal;
			display: -webkit-box;
			-webkit-line-clamp: 2;
			-webkit-box-orient: vertical;
		}

		.card-meta {
			flex-wrap: wrap;
		}

		.meeting-datetime {
			width: 100%;
		}

		.meeting-datetime::before {
			display: none;
		}
	}
</style>
