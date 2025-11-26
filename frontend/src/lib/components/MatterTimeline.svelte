<script lang="ts">
	import type { MatterTimelineResponse, MatterTimelineAppearance } from '$lib/api/types';
	import { generateAnchorId } from '$lib/utils/anchor';

	interface Props {
		timelineData: MatterTimelineResponse;
		matterFile?: string;
	}

	let { timelineData, matterFile }: Props = $props();

	function formatDate(dateStr: string): string {
		if (!dateStr) return '';
		const date = new Date(dateStr);
		return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
	}

	function extractMeetingType(title: string): { short: string; type: 'committee' | 'council' | 'board' | 'other' } {
		const lower = title.toLowerCase();

		// Specific patterns first (more precise)
		if (lower.includes('planning commission')) return { short: 'Planning', type: 'committee' };
		if (lower.includes('city council')) return { short: 'Council', type: 'council' };
		if (lower.includes('town council')) return { short: 'Council', type: 'council' };
		if (lower.includes('board of supervisors')) return { short: 'Supervisors', type: 'board' };
		if (lower.includes('school board')) return { short: 'School Board', type: 'board' };
		if (lower.includes('zoning board')) return { short: 'Zoning', type: 'board' };

		// Generic patterns
		if (lower.includes('commission')) return { short: 'Commission', type: 'committee' };
		if (lower.includes('committee')) return { short: 'Committee', type: 'committee' };
		if (lower.includes('council')) return { short: 'Council', type: 'council' };
		if (lower.includes('board')) return { short: 'Board', type: 'board' };

		// Fallback: first two meaningful words
		const words = title.split(/\s+/).filter(w => w.length > 2);
		if (words.length >= 2) {
			return { short: words.slice(0, 2).join(' '), type: 'other' };
		}
		return { short: title.slice(0, 12) || 'Meeting', type: 'other' };
	}

	function buildItemAnchor(appearance: MatterTimelineAppearance): string {
		return generateAnchorId({
			id: appearance.item_id,
			agenda_number: appearance.agenda_number,
			matter_file: timelineData.matter?.matter_file || matterFile || undefined
		});
	}

	function buildMeetingLink(appearance: MatterTimelineAppearance): string {
		const date = new Date(appearance.meeting_date);
		const year = date.getFullYear();
		const month = String(date.getMonth() + 1).padStart(2, '0');
		const day = String(date.getDate()).padStart(2, '0');
		const meetingSlug = `${year}-${month}-${day}-${appearance.meeting_id}`;
		const anchor = buildItemAnchor(appearance);
		return `/${appearance.banana}/${meetingSlug}#${anchor}`;
	}

	// Group appearances by date (handles same-day multiple committees)
	interface DateGroup {
		date: string;
		appearances: MatterTimelineAppearance[];
		isFuture: boolean;
	}

	const groupedTimeline = $derived.by((): DateGroup[] => {
		const groups: Record<string, MatterTimelineAppearance[]> = {};
		const now = new Date();

		timelineData.timeline.forEach(appearance => {
			const dateKey = appearance.meeting_date.split('T')[0];
			if (!groups[dateKey]) groups[dateKey] = [];
			groups[dateKey].push(appearance);
		});

		return Object.entries(groups).map(([date, appearances]) => ({
			date,
			appearances,
			isFuture: new Date(date) > now
		}));
	});

	// Check if any appearance is in the future (upcoming vote)
	const isUpcoming = $derived(groupedTimeline.some(g => g.isFuture));

	// Use list view if too many nodes (prevents cramped horizontal)
	const useListView = $derived(groupedTimeline.length > 6);
</script>

{#if timelineData.timeline.length > 0}
	<div class="matter-timeline" class:has-upcoming={isUpcoming}>
		<div class="timeline-header">
			<div class="timeline-meta">
				{#if matterFile}
					<span class="matter-id">{matterFile}</span>
				{/if}
				<span class="appearance-count">{timelineData.appearance_count} step{timelineData.appearance_count === 1 ? '' : 's'}</span>
			</div>
			{#if isUpcoming}
				<span class="upcoming-badge">Upcoming</span>
			{/if}
		</div>

		<!-- Horizontal progress bar (desktop, not too many nodes) -->
		{#if !useListView}
			<div class="timeline-track">
				<div class="track-line"></div>
				<div class="track-progress" style="width: {Math.min(100, (groupedTimeline.filter(g => !g.isFuture).length / Math.max(groupedTimeline.length, 3)) * 100)}%"></div>

				{#each groupedTimeline as group, index}
					{@const isFirst = index === 0}
					{@const isLast = index === groupedTimeline.length - 1}
					{@const isActive = isLast && !group.isFuture}
					{@const firstAppearance = group.appearances[0]}
					{@const meetingInfo = extractMeetingType(firstAppearance.meeting_title)}
					{@const hasMultiple = group.appearances.length > 1}

					<a
						href={buildMeetingLink(firstAppearance)}
						class="track-node"
						class:active={isActive}
						class:future={group.isFuture}
						class:first={isFirst}
						class:last={isLast}
						style="left: {groupedTimeline.length === 1 ? 50 : (index / (groupedTimeline.length - 1)) * 100}%"
						data-sveltekit-preload-data="tap"
						title={hasMultiple ? `${group.appearances.length} meetings on this date` : firstAppearance.meeting_title}
					>
						<div class="node-dot" class:committee={meetingInfo.type === 'committee'} class:council={meetingInfo.type === 'council'} class:board={meetingInfo.type === 'board'} class:multiple={hasMultiple}>
							{#if hasMultiple}
								<span class="node-count">{group.appearances.length}</span>
							{/if}
						</div>
						<div class="node-label">
							<span class="node-type">{hasMultiple ? 'Multiple' : meetingInfo.short}</span>
							<span class="node-date">{formatDate(group.date)}</span>
						</div>
					</a>
				{/each}
			</div>
		{/if}

		<!-- Compact list for mobile or many nodes -->
		<div class="timeline-list" class:force-show={useListView}>
			{#each timelineData.timeline as appearance, index}
				{@const meetingInfo = extractMeetingType(appearance.meeting_title)}
				{@const isLast = index === timelineData.timeline.length - 1}
				{@const isFuture = new Date(appearance.meeting_date) > new Date()}

				<a
					href={buildMeetingLink(appearance)}
					class="list-item"
					class:active={isLast && !isFuture}
					class:future={isFuture}
					data-sveltekit-preload-data="tap"
				>
					<span class="list-dot" class:committee={meetingInfo.type === 'committee'} class:council={meetingInfo.type === 'council'} class:board={meetingInfo.type === 'board'}></span>
					<span class="list-type">{meetingInfo.short}</span>
					<span class="list-date">{formatDate(appearance.meeting_date)}</span>
					{#if appearance.agenda_number}
						<span class="list-agenda">#{appearance.agenda_number}</span>
					{/if}
					<span class="list-arrow">-></span>
				</a>
			{/each}
		</div>
	</div>
{:else}
	<div class="timeline-empty">No timeline data available</div>
{/if}

<style>
	.timeline-empty {
		text-align: center;
		padding: var(--space-lg);
		color: var(--text-muted);
		font-family: var(--font-body);
		font-size: var(--text-sm);
	}

	.matter-timeline {
		background: var(--surface-secondary);
		border: 1px solid var(--border-primary);
		border-radius: var(--radius-lg);
		padding: var(--space-lg);
		margin: var(--space-md) 0;
	}

	.matter-timeline.has-upcoming {
		border-color: var(--action-coral);
		background: var(--surface-warm);
	}

	/* Header row */
	.timeline-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-sm);
		margin-bottom: var(--space-md);
	}

	.timeline-meta {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		flex-wrap: wrap;
	}

	.matter-id {
		font-family: var(--font-mono);
		font-size: var(--text-sm);
		font-weight: var(--font-semibold);
		color: var(--text);
		padding: 0.2rem 0.5rem;
		background: var(--surface-primary);
		border: 1px solid var(--border-primary);
		border-radius: var(--radius-sm);
	}

	.appearance-count {
		font-family: var(--font-body);
		font-size: var(--text-xs);
		color: var(--text-muted);
		font-weight: var(--font-medium);
	}

	.upcoming-badge {
		font-family: var(--font-body);
		font-size: var(--text-xs);
		font-weight: var(--font-semibold);
		color: white;
		background: var(--action-coral);
		padding: 0.2rem 0.5rem;
		border-radius: var(--radius-full);
		text-transform: uppercase;
		letter-spacing: 0.02em;
	}

	/* Horizontal track (desktop) */
	.timeline-track {
		position: relative;
		height: 90px;
		margin: var(--space-sm) 0;
		padding: 0 40px; /* Increased padding for edge labels */
	}

	.track-line {
		position: absolute;
		top: 12px;
		left: 40px;
		right: 40px;
		height: 3px;
		background: var(--border-primary);
		border-radius: 2px;
	}

	.track-progress {
		position: absolute;
		top: 12px;
		left: 40px;
		height: 3px;
		background: var(--text-muted);
		border-radius: 2px;
		transition: width var(--transition-normal);
	}

	.matter-timeline.has-upcoming .track-progress {
		background: var(--action-coral);
	}

	.track-node {
		position: absolute;
		transform: translateX(-50%);
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 6px;
		text-decoration: none;
		transition: transform var(--transition-fast);
		z-index: 1;
	}

	/* Align first node label to left edge */
	.track-node.first {
		align-items: flex-start;
	}
	.track-node.first .node-label {
		text-align: left;
		align-items: flex-start;
	}

	/* Align last node label to right edge */
	.track-node.last {
		align-items: flex-end;
	}
	.track-node.last .node-label {
		text-align: right;
		align-items: flex-end;
	}

	.track-node:hover {
		transform: translateX(-50%) translateY(-2px);
		z-index: 2;
	}

	.node-dot {
		width: 22px;
		height: 22px;
		border-radius: 50%;
		background: var(--surface-primary);
		border: 3px solid var(--text-muted);
		transition: all var(--transition-fast);
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.node-dot.multiple {
		width: 26px;
		height: 26px;
	}

	.node-count {
		font-family: var(--font-body);
		font-size: 0.6rem;
		font-weight: var(--font-bold);
		color: var(--text-muted);
	}

	.track-node:hover .node-dot {
		transform: scale(1.1);
	}

	.track-node.active .node-dot {
		background: var(--action-coral);
		border-color: var(--action-coral);
	}

	.track-node.active .node-count {
		color: white;
	}

	.track-node.future .node-dot {
		background: var(--surface-warm);
		border-color: var(--action-coral);
		border-style: dashed;
	}

	/* Meeting type colors for dots */
	.node-dot.committee { border-color: var(--committee-color, #8b5cf6); }
	.node-dot.council { border-color: var(--council-color, #3b82f6); }
	.node-dot.board { border-color: var(--board-color, #10b981); }
	.track-node.active .node-dot.committee,
	.track-node.active .node-dot.council,
	.track-node.active .node-dot.board {
		background: var(--action-coral);
		border-color: var(--action-coral);
	}

	.node-label {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 1px;
		text-align: center;
		max-width: 70px;
	}

	.node-type {
		font-family: var(--font-body);
		font-size: 0.7rem;
		font-weight: var(--font-semibold);
		color: var(--text);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		max-width: 70px;
	}

	.node-date {
		font-family: var(--font-body);
		font-size: 0.6rem;
		color: var(--text-muted);
		white-space: nowrap;
	}

	.track-node.future .node-type,
	.track-node.future .node-date {
		color: var(--action-coral);
	}

	/* List view (mobile fallback + many nodes) */
	.timeline-list {
		display: none;
		flex-direction: column;
		gap: var(--space-xs);
	}

	.timeline-list.force-show {
		display: flex;
	}

	.list-item {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		padding: var(--space-sm) var(--space-md);
		background: var(--surface-primary);
		border: 1px solid var(--border-primary);
		border-radius: var(--radius-md);
		text-decoration: none;
		transition: all var(--transition-fast);
	}

	.list-item:hover {
		border-color: var(--action-coral);
		background: var(--surface-warm);
	}

	.list-item.active {
		border-color: var(--action-coral);
		border-width: 2px;
	}

	.list-item.future {
		border-style: dashed;
		border-color: var(--action-coral);
		background: var(--surface-warm);
	}

	.list-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: var(--text-muted);
		flex-shrink: 0;
	}

	.list-item.active .list-dot {
		background: var(--action-coral);
	}

	.list-dot.committee { background: var(--committee-color, #8b5cf6); }
	.list-dot.council { background: var(--council-color, #3b82f6); }
	.list-dot.board { background: var(--board-color, #10b981); }

	.list-type {
		font-family: var(--font-body);
		font-size: var(--text-sm);
		font-weight: var(--font-medium);
		color: var(--text);
		flex: 1;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.list-date {
		font-family: var(--font-body);
		font-size: var(--text-xs);
		color: var(--text-muted);
		white-space: nowrap;
	}

	.list-agenda {
		font-family: var(--font-mono);
		font-size: var(--text-xs);
		color: var(--text-muted);
	}

	.list-arrow {
		font-family: var(--font-mono);
		font-size: var(--text-sm);
		color: var(--text-muted);
		transition: color var(--transition-fast);
	}

	.list-item:hover .list-arrow {
		color: var(--action-coral);
	}

	/* Responsive: show list, hide track on mobile or when force-show */
	@media (max-width: 640px) {
		.timeline-track {
			display: none;
		}

		.timeline-list {
			display: flex;
		}

		.matter-timeline {
			padding: var(--space-md);
		}
	}

	/* Hide track when list is force-shown (many nodes) */
	.timeline-list.force-show ~ .timeline-track,
	.timeline-track:has(~ .timeline-list.force-show) {
		display: none;
	}
</style>
