<script lang="ts">
	import { marked } from 'marked';
	import type { HappeningItem } from '$lib/api/types';
	import { formatMeetingDate, extractTime } from '$lib/utils/date-utils';
	import { generateAnchorId } from '$lib/utils/anchor';
	import { generateMeetingSlug } from '$lib/utils/utils';
	import { sanitizeHtml } from '$lib/utils/sanitize';

	interface Props {
		items: HappeningItem[];
		cityUrl: string;
	}

	let { items, cityUrl }: Props = $props();

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

	function renderSummary(summary: string | null): string {
		if (!summary) return '';
		return sanitizeHtml(marked(summary) as string);
	}

	function getMeetingDateTime(item: HappeningItem): string {
		if (!item.meeting_date) return 'Date TBD';
		const dateStr = formatMeetingDate(item.meeting_date);
		const timeStr = extractTime(item.meeting_date);
		return timeStr ? `${dateStr} at ${timeStr}` : dateStr;
	}

	function generateIcsUrl(item: HappeningItem): string {
		if (!item.meeting_date) return '';

		const date = new Date(item.meeting_date);
		const endDate = new Date(date.getTime() + 2 * 60 * 60 * 1000); // +2 hours

		const formatIcsDate = (d: Date) => {
			return d.toISOString().replace(/[-:]/g, '').split('.')[0] + 'Z';
		};

		const title = encodeURIComponent(item.meeting_title || 'City Meeting');
		const description = encodeURIComponent(
			`${item.item_title || ''}\n\n${item.reason || ''}`
		);
		const location = encodeURIComponent(
			item.participation?.virtual_url || item.participation?.physical_location || ''
		);

		const icsContent = [
			'BEGIN:VCALENDAR',
			'VERSION:2.0',
			'PRODID:-//engagic//EN',
			'BEGIN:VEVENT',
			`DTSTART:${formatIcsDate(date)}`,
			`DTEND:${formatIcsDate(endDate)}`,
			`SUMMARY:${title}`,
			`DESCRIPTION:${description}`,
			`LOCATION:${location}`,
			'END:VEVENT',
			'END:VCALENDAR'
		].join('\n');

		return `data:text/calendar;charset=utf-8,${encodeURIComponent(icsContent)}`;
	}
</script>

{#if items.length > 0}
	<section class="happening-section">
		<div class="happening-header">
			<h2 class="happening-title">Happening This Week</h2>
			<span class="happening-subtitle">Important items where your voice can make a difference</span>
		</div>

		<div class="happening-list">
			{#each items as item (item.item_id)}
				<article class="happening-card">
					<div class="rank-badge">#{item.rank}</div>

					<div class="card-content">
						<div class="card-header">
							{#if item.matter_file}
								<span class="matter-badge">{item.matter_file}</span>
							{/if}
							<span class="meeting-badge">{item.meeting_title || 'Meeting'}</span>
						</div>

						<h3 class="item-title">
							<a href={getItemLink(item)} class="item-link">
								{item.item_title || 'Agenda Item'}
							</a>
						</h3>

						<div class="meeting-datetime">
							{getMeetingDateTime(item)}
						</div>

						<p class="reason">{item.reason}</p>

						{#if item.item_summary}
							<div class="summary">
								{@html renderSummary(item.item_summary)}
							</div>
						{/if}

						<div class="card-actions">
							{#if item.participation}
								<div class="participation-links">
									{#if item.participation.email}
										<a href="mailto:{item.participation.email}" class="action-btn email-btn">
											Email Comment
										</a>
									{/if}
									{#if item.participation.virtual_url}
										<a href={item.participation.virtual_url} target="_blank" rel="noopener noreferrer" class="action-btn virtual-btn">
											Join Virtual
										</a>
									{/if}
									{#if item.participation.phone}
										<a href="tel:{item.participation.phone}" class="action-btn phone-btn">
											Call In
										</a>
									{/if}
								</div>
							{/if}
							<div class="secondary-actions">
								<a href={getItemLink(item)} class="view-link">View Details</a>
								{#if item.meeting_date}
									<a href={generateIcsUrl(item)} download="meeting.ics" class="calendar-link">
										Add to Calendar
									</a>
								{/if}
							</div>
						</div>
					</div>
				</article>
			{/each}
		</div>
	</section>
{/if}

<style>
	.happening-section {
		margin-bottom: 3rem;
		padding: 1.5rem;
		background: linear-gradient(135deg, var(--surface-secondary) 0%, var(--surface-primary) 100%);
		border: 2px solid var(--civic-blue);
		border-radius: 16px;
		box-shadow: 0 4px 20px rgba(79, 70, 229, 0.1);
	}

	.happening-header {
		margin-bottom: 1.5rem;
		text-align: center;
	}

	.happening-title {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.5rem;
		font-weight: 700;
		color: var(--civic-blue);
		margin: 0 0 0.5rem 0;
	}

	.happening-subtitle {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
		color: var(--civic-gray);
	}

	.happening-list {
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
	}

	.happening-card {
		display: flex;
		gap: 1rem;
		padding: 1.25rem;
		background: var(--surface-primary);
		border: 1px solid var(--border-primary);
		border-left: 4px solid var(--civic-green);
		border-radius: 12px;
		transition: all 0.2s ease;
	}

	.happening-card:hover {
		border-left-color: var(--civic-accent);
		box-shadow: 0 4px 12px rgba(79, 70, 229, 0.1);
		transform: translateY(-2px);
	}

	.rank-badge {
		flex-shrink: 0;
		width: 2.5rem;
		height: 2.5rem;
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--civic-blue);
		color: white;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
		font-weight: 700;
		border-radius: 50%;
	}

	.card-content {
		flex: 1;
		min-width: 0;
	}

	.card-header {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin-bottom: 0.75rem;
	}

	.matter-badge {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		font-weight: 700;
		color: var(--badge-matter-text);
		background: linear-gradient(135deg, var(--badge-matter-bg-start) 0%, var(--badge-matter-bg-end) 100%);
		border: 1px solid var(--badge-matter-border);
		padding: 0.25rem 0.5rem;
		border-radius: 6px;
	}

	.meeting-badge {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--civic-gray);
		background: var(--surface-secondary);
		padding: 0.25rem 0.5rem;
		border-radius: 6px;
	}

	.item-title {
		font-family: Georgia, 'Times New Roman', Times, serif;
		font-size: 1.1rem;
		font-weight: 600;
		line-height: 1.4;
		margin: 0 0 0.5rem 0;
	}

	.item-link {
		color: var(--text-primary);
		text-decoration: none;
		transition: color 0.2s;
	}

	.item-link:hover {
		color: var(--civic-blue);
	}

	.meeting-datetime {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
		color: var(--civic-gray);
		margin-bottom: 0.75rem;
	}

	.reason {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
		font-weight: 500;
		color: var(--civic-green);
		background: rgba(34, 197, 94, 0.1);
		border-left: 3px solid var(--civic-green);
		padding: 0.75rem;
		margin: 0 0 0.75rem 0;
		border-radius: 0 6px 6px 0;
		line-height: 1.5;
	}

	:global(.dark) .reason {
		background: rgba(34, 197, 94, 0.15);
		color: #86efac;
	}

	.summary {
		font-family: Georgia, 'Times New Roman', Times, serif;
		font-size: 0.9rem;
		line-height: 1.6;
		color: var(--text-secondary);
		margin: 0 0 1rem 0;
	}

	.summary :global(p) {
		margin: 0.5rem 0;
	}

	.summary :global(p:first-child) {
		margin-top: 0;
	}

	.summary :global(ul),
	.summary :global(ol) {
		margin: 0.5rem 0;
		padding-left: 1.5rem;
	}

	.summary :global(li) {
		margin: 0.25rem 0;
	}

	.summary :global(h1),
	.summary :global(h2),
	.summary :global(h3),
	.summary :global(h4) {
		font-family: 'IBM Plex Mono', monospace;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0.75rem 0 0.5rem 0;
		font-size: 0.95rem;
	}

	.card-actions {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.participation-links {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.action-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		padding: 0.5rem 1rem;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8rem;
		font-weight: 600;
		text-decoration: none;
		border-radius: 6px;
		transition: all 0.2s;
	}

	.email-btn {
		background: var(--civic-green);
		color: white;
	}

	.email-btn:hover {
		filter: brightness(1.1);
		transform: translateY(-1px);
	}

	.virtual-btn {
		background: var(--civic-blue);
		color: white;
	}

	.virtual-btn:hover {
		filter: brightness(1.1);
		transform: translateY(-1px);
	}

	.phone-btn {
		background: var(--civic-orange);
		color: white;
	}

	.phone-btn:hover {
		filter: brightness(1.1);
		transform: translateY(-1px);
	}

	.secondary-actions {
		display: flex;
		gap: 1rem;
	}

	.view-link,
	.calendar-link {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8rem;
		font-weight: 500;
		color: var(--civic-blue);
		text-decoration: none;
		transition: color 0.2s;
	}

	.view-link:hover,
	.calendar-link:hover {
		color: var(--civic-accent);
		text-decoration: underline;
	}

	@media (max-width: 640px) {
		.happening-section {
			padding: 1rem;
			margin-bottom: 2rem;
		}

		.happening-title {
			font-size: 1.25rem;
		}

		.happening-card {
			flex-direction: column;
			padding: 1rem;
		}

		.rank-badge {
			width: 2rem;
			height: 2rem;
			font-size: 0.8rem;
		}

		.item-title {
			font-size: 1rem;
		}

		.participation-links {
			flex-direction: column;
		}

		.action-btn {
			justify-content: center;
		}
	}
</style>
