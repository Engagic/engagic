<script lang="ts">
	import { authState } from '$lib/stores/auth.svelte';
	import { voteOnComment } from '$lib/api/deliberation';

	interface Props {
		comment: {
			id: number;
			participant_number: number;
			txt: string;
			created_at?: string;
		};
		deliberationId: string;
		userVote?: -1 | 0 | 1;
		consensusScore?: number;
		onVoted?: (commentId: number, vote: -1 | 0 | 1) => void;
	}

	let { comment, deliberationId, userVote, consensusScore, onVoted }: Props = $props();

	let voting = $state(false);
	let currentVote = $state(userVote);
	let error = $state<string | null>(null);

	const isHighConsensus = $derived(consensusScore !== undefined && consensusScore >= 0.8);

	async function vote(value: -1 | 0 | 1) {
		if (!authState.isAuthenticated) {
			error = 'Sign in to vote';
			setTimeout(() => (error = null), 5000);
			return;
		}

		if (voting) return;
		voting = true;
		error = null;

		const previousVote = currentVote;
		currentVote = value;

		try {
			await voteOnComment(deliberationId, comment.id, value, authState.accessToken ?? undefined);
			onVoted?.(comment.id, value);
		} catch (e: unknown) {
			currentVote = previousVote;
			error = e instanceof Error ? e.message : 'Vote failed';
			setTimeout(() => (error = null), 5000);
			console.error('Vote error:', e);
		} finally {
			voting = false;
		}
	}
</script>

<div class="comment-card" class:high-consensus={isHighConsensus}>
	<div class="comment-header">
		<span class="participant">Participant {comment.participant_number}</span>
		{#if isHighConsensus}
			<span class="consensus-badge">Consensus</span>
		{/if}
	</div>

	<p class="comment-text">{comment.txt}</p>

	<div class="vote-buttons" role="group" aria-label="Vote on this comment">
		<button
			class="vote-btn agree"
			class:active={currentVote === 1}
			onclick={() => vote(1)}
			disabled={voting}
			aria-label="Agree with this comment"
			aria-pressed={currentVote === 1}
		>
			<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
				<path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3" />
			</svg>
			<span>Agree</span>
		</button>

		<button
			class="vote-btn pass"
			class:active={currentVote === 0}
			onclick={() => vote(0)}
			disabled={voting}
			aria-label="Pass on this comment"
			aria-pressed={currentVote === 0}
		>
			<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
				<circle cx="12" cy="12" r="10" />
				<line x1="8" y1="12" x2="16" y2="12" />
			</svg>
			<span>Pass</span>
		</button>

		<button
			class="vote-btn disagree"
			class:active={currentVote === -1}
			onclick={() => vote(-1)}
			disabled={voting}
			aria-label="Disagree with this comment"
			aria-pressed={currentVote === -1}
		>
			<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
				<path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17" />
			</svg>
			<span>Disagree</span>
		</button>
	</div>

	{#if error}
		<p class="error">{error}</p>
	{/if}
</div>

<style>
	.comment-card {
		background: var(--bg-secondary, #f5f5f5);
		border-radius: 8px;
		padding: 1rem;
		margin-bottom: 0.75rem;
		border-left: 3px solid var(--border-primary, #ddd);
	}

	.comment-card.high-consensus {
		border-left-color: #22c55e;
		background: linear-gradient(to right, rgba(34, 197, 94, 0.05), transparent);
	}

	.comment-header {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-bottom: 0.5rem;
	}

	.participant {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		color: var(--civic-gray, #6b7280);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.consensus-badge {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.65rem;
		background: #22c55e;
		color: white;
		padding: 0.15rem 0.4rem;
		border-radius: 3px;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.comment-text {
		margin: 0 0 0.75rem 0;
		line-height: 1.5;
		color: var(--text-primary, #1f2937);
	}

	.vote-buttons {
		display: flex;
		gap: 0.5rem;
	}

	.vote-btn {
		display: flex;
		align-items: center;
		gap: 0.35rem;
		padding: 0.4rem 0.75rem;
		border: 1px solid var(--border-primary, #ddd);
		border-radius: 4px;
		background: var(--bg-primary, white);
		color: var(--text-secondary, #6b7280);
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.vote-btn:hover:not(:disabled) {
		border-color: var(--text-secondary, #6b7280);
	}

	.vote-btn:disabled {
		opacity: 0.5;
		cursor: default;
	}

	.vote-btn svg {
		width: 1rem;
		height: 1rem;
	}

	.vote-btn.agree.active {
		background: #dcfce7;
		border-color: #22c55e;
		color: #16a34a;
	}

	.vote-btn.pass.active {
		background: #fef9c3;
		border-color: #eab308;
		color: #ca8a04;
	}

	.vote-btn.disagree.active {
		background: #fee2e2;
		border-color: #ef4444;
		color: #dc2626;
	}

	.error {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.7rem;
		color: #ef4444;
		margin: 0.5rem 0 0 0;
	}
</style>
