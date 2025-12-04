<script lang="ts">
	import { onMount } from 'svelte';
	import { authState } from '$lib/stores/auth.svelte';
	import {
		getDeliberation,
		getDeliberationResults,
		getMyVotes,
		submitComment,
		type ClusterResults,
		type DeliberationComment
	} from '$lib/api/deliberation';
	import CommentCard from './CommentCard.svelte';
	import ClusterViz from './ClusterViz.svelte';

	interface Props {
		deliberationId: string;
		matterId?: string;
		topic?: string;
	}

	let { deliberationId, matterId, topic }: Props = $props();

	let loading = $state(true);
	let comments = $state<DeliberationComment[]>([]);
	let results = $state<ClusterResults | null>(null);
	let myVotes = $state<Record<number, -1 | 0 | 1>>({});
	let stats = $state({ comment_count: 0, vote_count: 0, participant_count: 0 });

	let newComment = $state('');
	let submitting = $state(false);
	let submitError = $state<string | null>(null);
	let submitSuccess = $state(false);

	let activeTab = $state<'vote' | 'results'>('vote');

	const consensusMap = $derived(results?.consensus ?? {});

	onMount(async () => {
		await loadData();
	});

	async function loadData() {
		loading = true;
		try {
			const [delibData, resultsData] = await Promise.all([
				getDeliberation(deliberationId),
				getDeliberationResults(deliberationId)
			]);

			comments = delibData.comments;
			stats = delibData.stats;
			results = resultsData.results;

			if (authState.isAuthenticated && authState.accessToken) {
				const votesData = await getMyVotes(deliberationId, authState.accessToken);
				myVotes = votesData.votes;
			}
		} catch (e) {
			console.error('Failed to load deliberation:', e);
		} finally {
			loading = false;
		}
	}

	async function handleSubmitComment() {
		if (!newComment.trim() || submitting) return;

		if (!authState.isAuthenticated) {
			submitError = 'Sign in to submit a comment';
			return;
		}

		submitting = true;
		submitError = null;
		submitSuccess = false;

		try {
			const response = await submitComment(
				deliberationId,
				newComment.trim(),
				authState.accessToken ?? undefined
			);

			newComment = '';
			submitSuccess = true;

			if (response.comment.is_approved) {
				comments = [
					...comments,
					{
						id: response.comment.id,
						participant_number: response.comment.participant_number,
						txt: response.comment.txt
					}
				];
			}

			setTimeout(() => {
				submitSuccess = false;
			}, 3000);
		} catch (e: unknown) {
			submitError = e instanceof Error ? e.message : 'Failed to submit comment';
		} finally {
			submitting = false;
		}
	}

	function handleVoted(commentId: number, vote: -1 | 0 | 1) {
		myVotes = { ...myVotes, [commentId]: vote };
	}
</script>

<div class="deliberation-panel">
	<header class="panel-header">
		<h3>Community Deliberation</h3>
		{#if topic}
			<p class="topic">{topic}</p>
		{/if}
	</header>

	{#if loading}
		<div class="loading">Loading...</div>
	{:else}
		<div class="stats-bar">
			<span>{stats.participant_count} participants</span>
			<span>{stats.comment_count} comments</span>
			<span>{stats.vote_count} votes</span>
		</div>

		<div class="tabs">
			<button
				class="tab"
				class:active={activeTab === 'vote'}
				onclick={() => (activeTab = 'vote')}
			>
				Vote on Comments
			</button>
			<button
				class="tab"
				class:active={activeTab === 'results'}
				onclick={() => (activeTab = 'results')}
			>
				Opinion Groups
			</button>
		</div>

		{#if activeTab === 'vote'}
			<div class="tab-content">
				<div class="submit-section">
					<textarea
						bind:value={newComment}
						placeholder="Share your perspective (10-500 characters)..."
						maxlength="500"
						disabled={submitting || !authState.isAuthenticated}
					></textarea>
					<div class="submit-row">
						<span class="char-count">{newComment.length}/500</span>
						<button
							class="submit-btn"
							onclick={handleSubmitComment}
							disabled={submitting || newComment.trim().length < 10}
						>
							{submitting ? 'Submitting...' : 'Submit'}
						</button>
					</div>
					{#if submitError}
						<p class="submit-error">{submitError}</p>
					{/if}
					{#if submitSuccess}
						<p class="submit-success">Comment submitted! It may need approval before appearing.</p>
					{/if}
					{#if !authState.isAuthenticated}
						<p class="auth-hint">Sign in to submit comments and vote</p>
					{/if}
				</div>

				<div class="comments-list">
					{#if comments.length === 0}
						<p class="no-comments">No comments yet. Be the first to share your perspective!</p>
					{:else}
						{#each comments as comment (comment.id)}
							<CommentCard
								{comment}
								{deliberationId}
								userVote={myVotes[comment.id]}
								consensusScore={consensusMap[comment.id]}
								onVoted={handleVoted}
							/>
						{/each}
					{/if}
				</div>
			</div>
		{:else}
			<div class="tab-content results-tab">
				{#if results}
					<ClusterViz {results} width={320} height={220} />

					{#if Object.entries(consensusMap).filter(([, score]) => score >= 0.8).length > 0}
						<div class="consensus-section">
							<h4>Points of Agreement</h4>
							<ul class="consensus-list">
								{#each Object.entries(consensusMap).filter(([, score]) => score >= 0.8) as [commentId, score] (commentId)}
									{@const comment = comments.find((c) => c.id === Number(commentId))}
									{#if comment}
										<li>
											<span class="consensus-score">{Math.round(score * 100)}%</span>
											{comment.txt}
										</li>
									{/if}
								{/each}
							</ul>
						</div>
					{/if}
				{:else}
					<p class="no-results">
						Not enough participation yet for opinion clustering.
						Need at least 3 participants and 2 comments.
					</p>
				{/if}
			</div>
		{/if}
	{/if}
</div>

<style>
	.deliberation-panel {
		background: var(--bg-primary, white);
		border: 1px solid var(--border-primary, #e5e7eb);
		border-radius: 8px;
		overflow: hidden;
	}

	.panel-header {
		padding: 1rem;
		border-bottom: 1px solid var(--border-primary, #e5e7eb);
	}

	.panel-header h3 {
		margin: 0;
		font-size: 1rem;
		font-weight: 600;
		color: var(--text-primary, #1f2937);
	}

	.topic {
		margin: 0.25rem 0 0 0;
		font-size: 0.85rem;
		color: var(--text-secondary, #6b7280);
	}

	.loading {
		padding: 2rem;
		text-align: center;
		color: var(--text-secondary, #6b7280);
	}

	.stats-bar {
		display: flex;
		gap: 1.5rem;
		padding: 0.75rem 1rem;
		background: var(--bg-secondary, #f9fafb);
		border-bottom: 1px solid var(--border-primary, #e5e7eb);
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		color: var(--civic-gray, #6b7280);
	}

	.tabs {
		display: flex;
		border-bottom: 1px solid var(--border-primary, #e5e7eb);
	}

	.tab {
		flex: 1;
		padding: 0.75rem;
		border: none;
		background: none;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8rem;
		color: var(--text-secondary, #6b7280);
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.tab:hover {
		background: var(--bg-secondary, #f9fafb);
	}

	.tab.active {
		color: var(--text-primary, #1f2937);
		border-bottom: 2px solid var(--text-primary, #1f2937);
		margin-bottom: -1px;
	}

	.tab-content {
		padding: 1rem;
	}

	.submit-section {
		margin-bottom: 1rem;
	}

	textarea {
		width: 100%;
		min-height: 80px;
		padding: 0.75rem;
		border: 1px solid var(--border-primary, #e5e7eb);
		border-radius: 6px;
		font-family: inherit;
		font-size: 0.9rem;
		resize: vertical;
		box-sizing: border-box;
	}

	textarea:focus {
		outline: none;
		border-color: var(--text-primary, #1f2937);
	}

	textarea:disabled {
		background: var(--bg-secondary, #f9fafb);
		cursor: not-allowed;
	}

	.submit-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-top: 0.5rem;
	}

	.char-count {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.7rem;
		color: var(--civic-gray, #9ca3af);
	}

	.submit-btn {
		padding: 0.5rem 1rem;
		background: var(--text-primary, #1f2937);
		color: white;
		border: none;
		border-radius: 4px;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8rem;
		cursor: pointer;
		transition: opacity 0.15s ease;
	}

	.submit-btn:hover:not(:disabled) {
		opacity: 0.9;
	}

	.submit-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.submit-error {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		color: #ef4444;
		margin: 0.5rem 0 0 0;
	}

	.submit-success {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		color: #22c55e;
		margin: 0.5rem 0 0 0;
	}

	.auth-hint {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		color: var(--civic-gray, #9ca3af);
		margin: 0.5rem 0 0 0;
		font-style: italic;
	}

	.comments-list {
		max-height: 400px;
		overflow-y: auto;
	}

	.no-comments {
		text-align: center;
		color: var(--civic-gray, #9ca3af);
		padding: 2rem;
		font-style: italic;
	}

	.results-tab {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 1.5rem;
	}

	.no-results {
		text-align: center;
		color: var(--civic-gray, #9ca3af);
		padding: 2rem;
		font-style: italic;
	}

	.consensus-section {
		width: 100%;
	}

	.consensus-section h4 {
		font-size: 0.9rem;
		font-weight: 600;
		margin: 0 0 0.75rem 0;
		color: var(--text-primary, #1f2937);
	}

	.consensus-list {
		margin: 0;
		padding: 0;
		list-style: none;
	}

	.consensus-list li {
		padding: 0.5rem 0;
		border-bottom: 1px solid var(--border-primary, #e5e7eb);
		font-size: 0.85rem;
		line-height: 1.4;
	}

	.consensus-list li:last-child {
		border-bottom: none;
	}

	.consensus-score {
		display: inline-block;
		background: #dcfce7;
		color: #16a34a;
		padding: 0.15rem 0.4rem;
		border-radius: 3px;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.7rem;
		margin-right: 0.5rem;
	}
</style>
