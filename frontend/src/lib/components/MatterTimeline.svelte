<script lang="ts">
	import { getMatterTimeline } from '$lib/api/index';
	import { onMount } from 'svelte';

	interface Props {
		matterId: string;
		matterFile?: string;
	}

	let { matterId, matterFile }: Props = $props();

	let timeline = $state<any>(null);
	let loading = $state(true);
	let error = $state('');
	let selectedAppearance = $state<number | null>(null);

	onMount(async () => {
		try {
			const result = await getMatterTimeline(matterId);
			timeline = result;
			loading = false;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load matter timeline';
			loading = false;
		}
	});

	function formatDate(dateStr: string): string {
		if (!dateStr) return '';
		const date = new Date(dateStr);
		return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
	}

	function extractMeetingType(title: string): string {
		// Extract committee/meeting type from title
		const lower = title.toLowerCase();
		if (lower.includes('committee')) {
			const match = title.match(/([\w\s]+committee)/i);
			return match ? match[1] : 'Committee';
		}
		if (lower.includes('council')) return 'City Council';
		if (lower.includes('board')) return 'Board';
		if (lower.includes('commission')) return 'Commission';
		return 'Meeting';
	}
</script>

{#if loading}
	<div class="timeline-loading">Loading matter timeline...</div>
{:else if error}
	<div class="timeline-error">{error}</div>
{:else if timeline && timeline.timeline.length > 0}
	<div class="matter-timeline">
		<div class="timeline-header">
			<div class="timeline-title">
				{#if matterFile}
					<span class="matter-id">{matterFile}</span>
				{/if}
				<span class="appearance-count">{timeline.appearance_count} appearance{timeline.appearance_count === 1 ? '' : 's'}</span>
			</div>
		</div>

		<div class="timeline-track">
			<div class="track-line"></div>
			<div class="timeline-nodes">
				{#each timeline.timeline as appearance, index}
					{@const meetingType = extractMeetingType(appearance.meeting_title)}
					<button
						class="timeline-node"
						class:selected={selectedAppearance === index}
						class:has-summary={!!appearance.summary}
						onclick={() => selectedAppearance = selectedAppearance === index ? null : index}
						title="{meetingType} on {formatDate(appearance.meeting_date)}"
					>
						<div class="node-dot"></div>
						<div class="node-label">
							<div class="node-date">{formatDate(appearance.meeting_date)}</div>
							<div class="node-meeting">{meetingType}</div>
						</div>
					</button>
				{/each}
			</div>
		</div>

		{#if selectedAppearance !== null && timeline.timeline[selectedAppearance]}
			{@const selected = timeline.timeline[selectedAppearance]}
			<div class="timeline-detail">
				<div class="detail-header">
					<h4>{selected.meeting_title}</h4>
					<time>{formatDate(selected.meeting_date)}</time>
				</div>
				{#if selected.agenda_number}
					<div class="detail-meta">
						Agenda Item: {selected.agenda_number}
					</div>
				{/if}
				{#if selected.topics && selected.topics.length > 0}
					<div class="detail-topics">
						{#each JSON.parse(selected.topics) as topic}
							<span class="detail-topic-tag">{topic}</span>
						{/each}
					</div>
				{/if}
				{#if selected.summary}
					<div class="detail-summary">
						{selected.summary.substring(0, 300)}{selected.summary.length > 300 ? '...' : ''}
					</div>
				{/if}
				<a href="/{selected.banana}/{selected.meeting_id}" class="detail-link">
					View Full Meeting →
				</a>
			</div>
		{/if}
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
		transition: all 0.3s ease;
	}

	.timeline-header {
		margin-bottom: 2rem;
	}

	.timeline-title {
		display: flex;
		align-items: center;
		gap: 1rem;
		flex-wrap: wrap;
	}

	.matter-id {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.1rem;
		font-weight: 700;
		color: var(--civic-blue);
		padding: 0.35rem 0.75rem;
		background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
		border: 2px solid #3b82f6;
		border-radius: 8px;
	}

	.appearance-count {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
		color: var(--civic-gray);
		font-weight: 500;
	}

	.timeline-track {
		position: relative;
		padding: 2rem 0;
		overflow-x: auto;
		overflow-y: visible;
	}

	.track-line {
		position: absolute;
		top: 50%;
		left: 2rem;
		right: 2rem;
		height: 3px;
		background: linear-gradient(90deg, var(--civic-blue) 0%, var(--civic-accent) 100%);
		border-radius: 2px;
		transform: translateY(-50%);
		z-index: 1;
	}

	.timeline-nodes {
		position: relative;
		display: flex;
		justify-content: space-between;
		align-items: center;
		min-width: fit-content;
		padding: 0 2rem;
		gap: 2rem;
		z-index: 2;
	}

	.timeline-node {
		position: relative;
		background: none;
		border: none;
		cursor: pointer;
		padding: 0;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.5rem;
		transition: all 0.2s ease;
	}

	.timeline-node:hover {
		transform: translateY(-2px);
	}

	.node-dot {
		width: 18px;
		height: 18px;
		background: var(--surface-primary);
		border: 3px solid var(--civic-blue);
		border-radius: 50%;
		transition: all 0.2s ease;
		box-shadow: 0 2px 6px rgba(79, 70, 229, 0.2);
	}

	.timeline-node.has-summary .node-dot {
		background: var(--civic-green);
		border-color: var(--civic-green);
		box-shadow: 0 2px 8px rgba(16, 185, 129, 0.3);
	}

	.timeline-node.selected .node-dot {
		width: 24px;
		height: 24px;
		border-width: 4px;
		box-shadow: 0 4px 12px rgba(79, 70, 229, 0.4);
	}

	.timeline-node:hover .node-dot {
		transform: scale(1.15);
		box-shadow: 0 4px 12px rgba(79, 70, 229, 0.3);
	}

	.node-label {
		text-align: center;
		white-space: nowrap;
	}

	.node-date {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--civic-blue);
		margin-bottom: 0.25rem;
	}

	.node-meeting {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.7rem;
		color: var(--civic-gray);
		font-weight: 500;
		max-width: 120px;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.timeline-detail {
		margin-top: 2rem;
		padding: 1.5rem;
		background: var(--surface-secondary);
		border-left: 4px solid var(--civic-blue);
		border-radius: 8px;
		animation: slideIn 0.2s ease-out;
	}

	@keyframes slideIn {
		from {
			opacity: 0;
			transform: translateY(-10px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	.detail-header {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 1rem;
		margin-bottom: 1rem;
		flex-wrap: wrap;
	}

	.detail-header h4 {
		font-family: Georgia, 'Times New Roman', Times, serif;
		font-size: 1.1rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
	}

	.detail-header time {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
		color: var(--civic-gray);
	}

	.detail-meta {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8rem;
		color: var(--civic-gray);
		margin-bottom: 0.75rem;
	}

	.detail-topics {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin-bottom: 1rem;
	}

	.detail-topic-tag {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.7rem;
		padding: 0.25rem 0.6rem;
		background: var(--surface-primary);
		color: var(--civic-blue);
		border: 1px solid var(--border-primary);
		border-radius: 4px;
		font-weight: 500;
	}

	.detail-summary {
		font-family: Georgia, 'Times New Roman', Times, serif;
		font-size: 0.95rem;
		line-height: 1.6;
		color: var(--text-primary);
		margin-bottom: 1rem;
	}

	.detail-link {
		display: inline-block;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
		font-weight: 600;
		color: var(--civic-blue);
		text-decoration: none;
		transition: color 0.2s ease;
	}

	.detail-link:hover {
		color: var(--civic-accent);
		text-decoration: underline;
	}

	@media (max-width: 640px) {
		.matter-timeline {
			padding: 1rem;
		}

		.timeline-nodes {
			gap: 1.5rem;
		}

		.node-label {
			font-size: 0.7rem;
		}

		.node-meeting {
			max-width: 80px;
		}

		.detail-header {
			flex-direction: column;
			align-items: flex-start;
		}
	}
</style>
