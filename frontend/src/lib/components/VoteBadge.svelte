<script lang="ts">
	import type { VoteTally, VoteOutcome } from '$lib/api/types';

	interface Props {
		tally: VoteTally;
		outcome?: VoteOutcome;
		size?: 'small' | 'medium';
		showDetails?: boolean;
	}

	let { tally, outcome, size = 'medium', showDetails = false }: Props = $props();

	const outcomeLabel = $derived.by(() => {
		if (!outcome || outcome === 'no_vote' || outcome === 'unknown') return null;
		const labels: Record<string, string> = {
			passed: 'Passed',
			failed: 'Failed',
			tabled: 'Tabled',
			withdrawn: 'Withdrawn',
			referred: 'Referred',
			amended: 'Amended'
		};
		return labels[outcome] || outcome;
	});

	const variant = $derived.by(() => {
		if (!outcome) return 'neutral';
		if (outcome === 'passed') return 'success';
		if (outcome === 'failed') return 'danger';
		return 'neutral';
	});

	const tallyText = $derived(`${tally.yes}-${tally.no}`);
	const hasVotes = $derived(tally.yes > 0 || tally.no > 0);
</script>

{#if hasVotes}
	<span class="vote-badge {variant} {size}" title="Yes: {tally.yes}, No: {tally.no}{tally.abstain ? `, Abstain: ${tally.abstain}` : ''}{tally.absent ? `, Absent: ${tally.absent}` : ''}">
		{#if outcomeLabel}
			<span class="outcome">{outcomeLabel}</span>
		{/if}
		<span class="tally">{tallyText}</span>
		{#if showDetails && (tally.abstain || tally.absent)}
			<span class="details">
				{#if tally.abstain}
					<span class="abstain">{tally.abstain}A</span>
				{/if}
			</span>
		{/if}
	</span>
{/if}

<style>
	.vote-badge {
		font-family: 'IBM Plex Mono', monospace;
		font-weight: 600;
		border-radius: 6px;
		border: 1px solid;
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		white-space: nowrap;
	}

	.medium {
		font-size: 0.8rem;
		padding: 0.3rem 0.6rem;
	}

	.small {
		font-size: 0.7rem;
		padding: 0.2rem 0.45rem;
	}

	.outcome {
		font-weight: 700;
	}

	.tally {
		opacity: 0.9;
	}

	.details {
		font-size: 0.85em;
		opacity: 0.75;
	}

	/* Success: passed */
	.success {
		background: var(--badge-green-bg);
		border-color: var(--badge-green-border);
		color: var(--badge-green-text);
	}

	/* Danger: failed */
	.danger {
		--badge-red-bg: #fee2e2;
		--badge-red-border: #fca5a5;
		--badge-red-text: #991b1b;
		background: var(--badge-red-bg);
		border-color: var(--badge-red-border);
		color: var(--badge-red-text);
	}

	:global(.dark) .danger {
		--badge-red-bg: #7f1d1d;
		--badge-red-border: #ef4444;
		--badge-red-text: #fca5a5;
	}

	/* Neutral: no outcome, tabled, etc */
	.neutral {
		background: var(--surface-secondary);
		border-color: var(--border-primary);
		color: var(--text-primary);
	}
</style>
