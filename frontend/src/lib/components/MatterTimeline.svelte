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
	let expandedAppearances = $state<Set<number>>(new Set());

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

	function inferStatus(index: number, total: number): string {
		// Infer legislative status from position in timeline
		if (index === 0) return 'Introduced';
		if (index === total - 1) return 'Recent';
		return 'Under Review';
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
			<div class="timeline-subtitle">Legislative Journey</div>
		</div>

		<div class="timeline-flow">
			{#each timeline.timeline as appearance, index}
				{@const meetingInfo = extractMeetingType(appearance.meeting_title)}
				{@const status = inferStatus(index, timeline.timeline.length)}
				{@const isExpanded = expandedAppearances.has(index)}

				<div class="flow-step" class:selected={isExpanded}>
					<button
						class="step-card"
						class:committee={meetingInfo.type === 'committee'}
						class:council={meetingInfo.type === 'council'}
						class:board={meetingInfo.type === 'board'}
						class:has-summary={!!appearance.summary}
						onclick={() => {
							if (isExpanded) {
								expandedAppearances.delete(index);
							} else {
								expandedAppearances.add(index);
							}
							expandedAppearances = expandedAppearances;
						}}
					>
						<div class="step-number">{index + 1}</div>
						<div class="step-content">
							<div class="step-header">
								<div class="step-type">{meetingInfo.name}</div>
								<div class="step-status">{status}</div>
							</div>
							<div class="step-date">{formatDate(appearance.meeting_date)}</div>
							{#if appearance.agenda_number}
								<div class="step-agenda">Item {appearance.agenda_number}</div>
							{/if}
						</div>
						<div class="step-expand">
							{isExpanded ? '▼' : '▶'}
						</div>
					</button>

					{#if isExpanded}
						<div class="step-detail">
							<h4 class="detail-title">{appearance.meeting_title}</h4>
							{#if appearance.topics}
								{@const topics = JSON.parse(appearance.topics)}
								{#if topics.length > 0}
									<div class="detail-topics">
										{#each topics as topic}
											<span class="detail-topic-tag">{topic}</span>
										{/each}
									</div>
								{/if}
							{/if}
							{#if appearance.summary}
								<div class="detail-summary">
									{appearance.summary.substring(0, 300)}{appearance.summary.length > 300 ? '...' : ''}
								</div>
							{/if}
							<a href="/{appearance.banana}/{appearance.meeting_id}" class="detail-link">
								View Full Meeting →
							</a>
						</div>
					{/if}
				</div>

				{#if index < timeline.timeline.length - 1}
					<div class="flow-arrow">
						<div class="arrow-line"></div>
						<div class="arrow-head">↓</div>
					</div>
				{/if}
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
		align-items: center;
		gap: 1rem;
		margin-bottom: 0.25rem;
	}

	.step-type {
		font-weight: 700;
		font-size: 1rem;
		color: var(--text-primary);
		font-family: 'IBM Plex Mono', monospace;
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

	.step-date {
		font-size: 0.8rem;
		color: var(--civic-gray);
		font-weight: 500;
	}

	.step-agenda {
		font-size: 0.75rem;
		color: var(--civic-gray);
		margin-top: 0.25rem;
	}

	.step-expand {
		flex-shrink: 0;
		font-size: 1.2rem;
		color: var(--civic-blue);
		transition: transform 0.2s ease;
	}

	/* Flow arrows */
	.flow-arrow {
		display: flex;
		flex-direction: column;
		align-items: center;
		height: 40px;
		position: relative;
	}

	.arrow-line {
		width: 2px;
		flex: 1;
		background: linear-gradient(180deg, var(--civic-blue) 0%, var(--civic-accent) 100%);
	}

	.arrow-head {
		font-size: 1.5rem;
		line-height: 1;
		color: var(--civic-accent);
		font-weight: bold;
	}

	/* Expanded detail */
	.step-detail {
		margin: 1rem 0 0 52px;
		padding: 1.25rem;
		background: var(--surface-primary);
		border: 2px solid var(--border-primary);
		border-left: 4px solid var(--civic-blue);
		border-radius: 8px;
		animation: expandIn 0.2s ease-out;
	}

	@keyframes expandIn {
		from {
			opacity: 0;
			max-height: 0;
			margin-top: 0;
		}
		to {
			opacity: 1;
			max-height: 500px;
			margin-top: 1rem;
		}
	}

	.detail-title {
		font-family: Georgia, 'Times New Roman', Times, serif;
		font-size: 1rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0 0 1rem 0;
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
		background: var(--surface-secondary);
		color: var(--civic-blue);
		border: 1px solid var(--border-primary);
		border-radius: 4px;
		font-weight: 500;
	}

	.detail-summary {
		font-family: Georgia, 'Times New Roman', Times, serif;
		font-size: 0.9rem;
		line-height: 1.6;
		color: var(--text-secondary);
		margin-bottom: 1rem;
	}

	.detail-link {
		display: inline-block;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
		font-weight: 600;
		color: var(--civic-blue);
		text-decoration: none;
		transition: all 0.2s ease;
	}

	.detail-link:hover {
		color: var(--civic-accent);
		text-decoration: underline;
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

		.step-detail {
			margin-left: 0;
		}

		.flow-arrow {
			height: 30px;
		}
	}
</style>
