<script lang="ts">
	import type { MatterTimelineResponse, MatterTimelineAppearance } from '$lib/api/types';
	import { generateAnchorId } from '$lib/utils/anchor';
	import { goto } from '$app/navigation';
	import VoteBadge from './VoteBadge.svelte';

	interface Props {
		timelineData: MatterTimelineResponse;
		matterFile?: string;
	}

	let { timelineData, matterFile }: Props = $props();

	// Vote badges removed from timeline to prevent N+1 API requests when listing many matters
	// Votes are shown on the individual meeting page instead

	function formatDate(dateStr: string): string {
		if (!dateStr) return '';
		const date = new Date(dateStr);
		return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
	}

	function extractMeetingType(title: string): { name: string; type: 'committee' | 'council' | 'board' | 'other' } {
		// Extract committee/meeting type from title
		const lower = title.toLowerCase();
		if (lower.includes('committee')) {
			const match = title.match(/([\w\s]+committee)/i);
			return { name: match ? match[1] : 'Committee', type: 'committee' };
		}
		if (lower.includes('council')) {
			return { name: 'City Council', type: 'council' };
		}
		if (lower.includes('board')) {
			const match = title.match(/([\w\s]+board)/i);
			return { name: match ? match[1] : 'Board', type: 'board' };
		}
		if (lower.includes('commission')) {
			const match = title.match(/([\w\s]+commission)/i);
			return { name: match ? match[1] : 'Commission', type: 'committee' };
		}
		return { name: 'Meeting', type: 'other' };
	}

	function getDateContext(index: number, total: number): string {
		// Show truthful date context instead of fake legislative status
		if (total === 1) return 'Only appearance';
		if (index === 0) return 'First discussed';
		if (index === total - 1) return 'Most recent';
		return `Step ${index + 1}`;
	}

	function buildItemAnchor(appearance: MatterTimelineAppearance): string {
		// Build anchor ID with full hierarchy: agenda_number > matter_file > item_id
		// Use matter_file from the matter object (all appearances share the same matter_file)
		return generateAnchorId({
			id: appearance.item_id,
			agenda_number: appearance.agenda_number,
			matter_file: timelineData.matter?.matter_file || matterFile || undefined
		});
	}

	function buildMeetingLink(appearance: MatterTimelineAppearance): string {
		// Build meeting slug from date and ID
		const date = new Date(appearance.meeting_date);
		const year = date.getFullYear();
		const month = String(date.getMonth() + 1).padStart(2, '0');
		const day = String(date.getDate()).padStart(2, '0');
		const meetingSlug = `${year}-${month}-${day}-${appearance.meeting_id}`;

		// Build full meeting URL with anchor
		const anchor = buildItemAnchor(appearance);
		return `/${appearance.banana}/${meetingSlug}#${anchor}`;
	}

	function navigateToCommittee(e: MouseEvent, banana: string, committeeId: string) {
		e.preventDefault();
		e.stopPropagation();
		goto(`/${banana}/committees/${committeeId}`);
	}
</script>

{#if timelineData.timeline.length > 0}
	<div class="matter-timeline">
		<div class="timeline-header">
			<div class="timeline-title">
				{#if matterFile}
					<span class="matter-id">{matterFile}</span>
				{/if}
				<span class="appearance-count">{timelineData.appearance_count} appearance{timelineData.appearance_count === 1 ? '' : 's'}</span>
			</div>
			<div class="timeline-subtitle">Legislative Journey</div>
		</div>

		<div class="timeline-flow">
			{#each timelineData.timeline as appearance, index}
				{@const meetingInfo = extractMeetingType(appearance.meeting_title)}
				{@const dateContext = getDateContext(index, timelineData.timeline.length)}

				<div class="flow-step">
					<a
						href={buildMeetingLink(appearance)}
						class="step-card"
						class:committee={meetingInfo.type === 'committee'}
						class:council={meetingInfo.type === 'council'}
						class:board={meetingInfo.type === 'board'}
						class:has-summary={!!appearance.summary}
						data-sveltekit-preload-data="tap"
					>
						<div class="step-number">{index + 1}</div>
						<div class="step-content">
							<div class="step-header">
								<div class="step-type">{appearance.meeting_title}</div>
								<div class="step-status">{dateContext}</div>
							</div>
							<div class="step-meta">
								<span class="step-date">{formatDate(appearance.meeting_date)}</span>
								{#if appearance.committee && appearance.committee_id}
									<button
									   type="button"
									   class="step-committee-link"
									   onclick={(e) => navigateToCommittee(e, appearance.banana, appearance.committee_id!)}>
										{appearance.committee}
									</button>
								{:else if appearance.committee}
									<span class="step-committee">{appearance.committee}</span>
								{/if}
							</div>
							{#if appearance.agenda_number}
								<div class="step-agenda">Item {appearance.agenda_number}</div>
							{/if}
						</div>
						{#if appearance.vote_outcome && appearance.vote_tally}
							<VoteBadge tally={appearance.vote_tally} outcome={appearance.vote_outcome} size="small" />
						{/if}
						<div class="step-arrow">→</div>
					</a>
				</div>
			{/each}
		</div>
	</div>
{:else}
	<div class="timeline-empty">No timeline data available</div>
{/if}

<style>
	.timeline-loading,
	.timeline-error,
	.timeline-empty {
		text-align: center;
		padding: 2rem;
		color: var(--civic-gray);
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
	}

	.timeline-error {
		color: var(--civic-red);
	}

	.matter-timeline {
		background: var(--surface-primary);
		border: 2px solid var(--border-primary);
		border-radius: 12px;
		padding: 1.5rem;
		margin: 1.5rem 0;
	}

	.timeline-header {
		margin-bottom: 2rem;
		border-bottom: 2px solid var(--border-primary);
		padding-bottom: 1rem;
	}

	.timeline-title {
		display: flex;
		align-items: center;
		gap: 1rem;
		flex-wrap: wrap;
		margin-bottom: 0.5rem;
	}

	.matter-id {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.1rem;
		font-weight: 700;
		color: var(--badge-blue-text);
		padding: 0.35rem 0.75rem;
		background: var(--badge-blue-bg);
		border: 2px solid var(--badge-blue-border);
		border-radius: 8px;
	}

	.appearance-count {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
		color: var(--civic-gray);
		font-weight: 500;
	}

	.timeline-subtitle {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.5px;
		color: var(--civic-gray);
		font-weight: 600;
	}

	/* Vertical flow timeline */
	.timeline-flow {
		display: flex;
		flex-direction: column;
		gap: 0;
		position: relative;
	}

	.flow-step {
		position: relative;
		animation: fadeIn 0.3s ease-out;
	}

	@keyframes fadeIn {
		from {
			opacity: 0;
			transform: translateY(10px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	.step-card {
		width: 100%;
		display: flex;
		align-items: center;
		gap: 1rem;
		padding: 1rem 1.25rem;
		background: var(--surface-secondary);
		border: 2px solid var(--border-primary);
		border-left: 4px solid var(--civic-blue);
		border-radius: 8px;
		cursor: pointer;
		transition: all 0.2s ease;
		font-family: 'IBM Plex Mono', monospace;
		text-align: left;
	}

	.step-card:hover {
		transform: translateX(4px);
		border-left-width: 6px;
		box-shadow: 0 4px 12px rgba(79, 70, 229, 0.15);
	}

	.step-card.committee {
		border-left-color: var(--committee-color);
	}

	.step-card.council {
		border-left-color: var(--council-color);
	}

	.step-card.board {
		border-left-color: var(--board-color);
	}

	.step-card.has-summary {
		background: linear-gradient(135deg, var(--surface-secondary) 0%, rgba(16, 185, 129, 0.05) 100%);
	}

	.flow-step.selected .step-card {
		border-left-width: 6px;
		box-shadow: 0 6px 16px rgba(79, 70, 229, 0.2);
	}

	.step-number {
		flex-shrink: 0;
		width: 36px;
		height: 36px;
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--civic-blue);
		color: var(--civic-white);
		border-radius: 50%;
		font-weight: 700;
		font-size: 0.9rem;
	}

	.step-card.committee .step-number {
		background: var(--committee-color);
	}

	.step-card.council .step-number {
		background: var(--council-color);
	}

	.step-card.board .step-number {
		background: var(--board-color);
	}

	.step-content {
		flex: 1;
	}

	.step-header {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
		margin-bottom: 0.25rem;
	}

	.step-type {
		font-weight: 700;
		font-size: 0.9rem;
		color: var(--text-primary);
		font-family: 'IBM Plex Mono', monospace;
		line-height: 1.3;
	}

	.step-status {
		font-size: 0.7rem;
		padding: 0.2rem 0.5rem;
		background: var(--civic-blue);
		color: var(--civic-white);
		border-radius: 4px;
		text-transform: uppercase;
		letter-spacing: 0.5px;
		font-weight: 700;
		border: 1.5px solid currentColor;
	}

	.step-card.committee .step-status {
		background: var(--surface-primary);
		color: var(--committee-color);
		border-color: var(--committee-color);
	}

	.step-card.council .step-status {
		background: var(--surface-primary);
		color: var(--council-color);
		border-color: var(--council-color);
	}

	.step-card.board .step-status {
		background: var(--surface-primary);
		color: var(--board-color);
		border-color: var(--board-color);
	}

	.step-meta {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		flex-wrap: wrap;
	}

	.step-date {
		font-size: 0.8rem;
		color: var(--civic-gray);
		font-weight: 500;
	}

	.step-committee {
		font-size: 0.7rem;
		padding: 0.15rem 0.5rem;
		background: var(--badge-purple-bg, rgba(139, 92, 246, 0.1));
		color: var(--badge-purple-text, #7c3aed);
		border: 1px solid var(--badge-purple-border, rgba(139, 92, 246, 0.3));
		border-radius: 4px;
		font-weight: 600;
	}

	.step-committee-link {
		font-family: inherit;
		font-size: 0.7rem;
		padding: 0.15rem 0.5rem;
		background: var(--badge-purple-bg, rgba(139, 92, 246, 0.1));
		color: var(--badge-purple-text, #7c3aed);
		border: 1px solid var(--badge-purple-border, rgba(139, 92, 246, 0.3));
		border-radius: 4px;
		font-weight: 600;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.step-committee-link:hover {
		background: var(--badge-purple-bg, rgba(139, 92, 246, 0.2));
		border-color: var(--badge-purple-text, #7c3aed);
	}

	.step-agenda {
		font-size: 0.75rem;
		color: var(--civic-gray);
		margin-top: 0.25rem;
	}

	.step-arrow {
		flex-shrink: 0;
		font-size: 1.2rem;
		color: var(--civic-blue);
		transition: transform 0.2s ease;
	}

	@media (max-width: 640px) {
		.matter-timeline {
			padding: 1rem;
		}

		.step-card {
			padding: 0.75rem 1rem;
			gap: 0.75rem;
		}

		.step-number {
			width: 28px;
			height: 28px;
			font-size: 0.8rem;
		}

		.step-type {
			font-size: 0.85rem;
		}

		.step-status {
			font-size: 0.65rem;
			padding: 0.15rem 0.4rem;
		}
	}
</style>
