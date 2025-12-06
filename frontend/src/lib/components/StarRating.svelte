<script lang="ts">
	import { onMount } from 'svelte';
	import { getRatingStats, submitRating } from '$lib/api';
	import type { RatingStats } from '$lib/api/types';

	interface Props {
		entityType: 'item' | 'meeting' | 'matter';
		entityId: string;
		size?: 'small' | 'medium';
		showCount?: boolean;
	}

	let { entityType, entityId, size = 'medium', showCount = true }: Props = $props();

	let stats = $state<RatingStats | null>(null);
	let loading = $state(true);
	let submitting = $state(false);
	let hoverRating = $state(0);
	let userRating = $state(0);
	let error = $state<string | null>(null);

	const avgRating = $derived(stats?.avg_rating ?? 0);
	const ratingCount = $derived(stats?.rating_count ?? 0);
	const displayRating = $derived(hoverRating || userRating || Math.round(avgRating));

	onMount(async () => {
		try {
			stats = await getRatingStats(entityType, entityId);
			userRating = stats.user_rating ?? 0;
		} catch {
			// No rating stats available - expected for new entities
		} finally {
			loading = false;
		}
	});

	async function handleRating(rating: number) {
		if (submitting) return;

		// Optimistic update
		const previousRating = userRating;
		const previousStats = stats;
		userRating = rating;

		submitting = true;
		error = null;

		try {
			await submitRating(entityType, entityId, rating);

			// Refresh stats after successful submission
			stats = await getRatingStats(entityType, entityId);
			userRating = stats.user_rating ?? rating;
		} catch (e) {
			// Rollback on error
			userRating = previousRating;
			stats = previousStats;
			error = 'Failed to submit rating';
		} finally {
			submitting = false;
		}
	}

	function handleKeyDown(e: KeyboardEvent, rating: number) {
		if (e.key === 'Enter' || e.key === ' ') {
			e.preventDefault();
			handleRating(rating);
		}
	}
</script>

<div class="star-rating {size}" class:loading class:submitting>
	<div
		class="stars"
		role="group"
		aria-label="Rate this {entityType}"
		onmouseleave={() => hoverRating = 0}
	>
		{#each [1, 2, 3, 4, 5] as star}
			<button
				class="star"
				class:filled={star <= displayRating}
				class:user-rated={star <= userRating && userRating > 0}
				onclick={() => handleRating(star)}
				onmouseenter={() => hoverRating = star}
				onkeydown={(e) => handleKeyDown(e, star)}
				disabled={submitting}
				aria-label="Rate {star} star{star === 1 ? '' : 's'}"
				title={userRating === star ? 'Your rating' : `Rate ${star} star${star === 1 ? '' : 's'}`}
			>
				<svg viewBox="0 0 24 24" fill="currentColor">
					<path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
				</svg>
			</button>
		{/each}
	</div>

	{#if showCount && !loading}
		<span class="rating-info">
			{#if ratingCount > 0}
				<span class="avg">{avgRating.toFixed(1)}</span>
				<span class="count">({ratingCount})</span>
			{:else}
				<span class="no-ratings">No ratings yet</span>
			{/if}
		</span>
	{/if}

	{#if error}
		<span class="error-msg">{error}</span>
	{/if}
</div>

<style>
	.star-rating {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
	}

	.star-rating.loading {
		opacity: 0.5;
	}

	.star-rating.submitting {
		pointer-events: none;
	}

	.stars {
		display: flex;
		gap: 0.15rem;
	}

	.star {
		background: none;
		border: none;
		padding: 0;
		cursor: pointer;
		color: var(--border-primary);
		transition: all 0.15s ease;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.star:hover {
		transform: scale(1.1);
	}

	.star:disabled {
		cursor: default;
	}

	.star.filled {
		color: #fbbf24;
	}

	.star.user-rated {
		color: #f59e0b;
	}

	.medium .star svg {
		width: 1.25rem;
		height: 1.25rem;
	}

	.small .star svg {
		width: 0.9rem;
		height: 0.9rem;
	}

	.rating-info {
		font-family: 'IBM Plex Mono', monospace;
		display: flex;
		align-items: center;
		gap: 0.25rem;
	}

	.medium .rating-info {
		font-size: 0.85rem;
	}

	.small .rating-info {
		font-size: 0.7rem;
	}

	.avg {
		font-weight: 600;
		color: var(--text-primary);
	}

	.count {
		color: var(--civic-gray);
	}

	.no-ratings {
		color: var(--civic-gray);
		font-style: italic;
	}

	.error-msg {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.7rem;
		color: #ef4444;
		margin-left: 0.5rem;
	}
</style>
