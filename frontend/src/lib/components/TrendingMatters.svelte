<script lang="ts">
	import { onMount } from 'svelte';
	import { getTrendingMatters } from '$lib/api';
	import type { TrendingMatter } from '$lib/api/types';
	import StatusBadge from './StatusBadge.svelte';

	interface Props {
		limit?: number;
	}

	let { limit = 5 }: Props = $props();

	let trending = $state<TrendingMatter[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	onMount(async () => {
		try {
			const response = await getTrendingMatters(limit);
			trending = response.trending;
		} catch (e) {
			console.debug('Trending not available:', e);
			error = 'Unable to load trending matters';
		} finally {
			loading = false;
		}
	});

	function truncateTitle(title: string, maxLength: number = 80): string {
		if (title.length <= maxLength) return title;
		return title.substring(0, maxLength).trim() + '...';
	}
</script>

{#if !loading && trending.length > 0}
	<section class="trending-section">
		<div class="trending-header">
			<h2 class="trending-title">Trending This Week</h2>
			<span class="trending-subtitle">Most engaged legislative matters</span>
		</div>

		<div class="trending-list">
			{#each trending as matter, index}
				<a
					href="/matter/{matter.matter_id}"
					class="trending-item"
					data-sveltekit-preload-data="tap"
				>
					<span class="trending-rank">{index + 1}</span>
					<div class="trending-content">
						<div class="trending-item-header">
							{#if matter.city_name}
								<span class="trending-city">{matter.city_name}</span>
							{/if}
							{#if matter.status}
								<StatusBadge status={matter.status} size="small" />
							{/if}
						</div>
						<span class="trending-item-title">{truncateTitle(matter.title)}</span>
						<div class="trending-meta">
							<span class="engagement-count">{matter.engagement} engagements</span>
							<span class="user-count">{matter.unique_users} people</span>
						</div>
					</div>
				</a>
			{/each}
		</div>
	</section>
{/if}

<style>
	.trending-section {
		margin: 2rem 0;
		padding: 1.5rem;
		background: var(--surface-primary);
		border: 1px solid var(--border-primary);
		border-radius: 12px;
		box-shadow: 0 2px 8px var(--shadow-sm);
	}

	.trending-header {
		margin-bottom: 1.25rem;
		padding-bottom: 0.75rem;
		border-bottom: 1px solid var(--border-primary);
	}

	.trending-title {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1rem;
		font-weight: 700;
		color: var(--text-primary);
		margin: 0;
	}

	.trending-subtitle {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		color: var(--civic-gray);
		text-transform: uppercase;
		letter-spacing: 0.5px;
	}

	.trending-list {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.trending-item {
		display: flex;
		align-items: flex-start;
		gap: 1rem;
		padding: 0.75rem;
		background: var(--surface-secondary);
		border: 1px solid var(--border-primary);
		border-radius: 8px;
		text-decoration: none;
		transition: all 0.2s ease;
	}

	.trending-item:hover {
		border-color: var(--civic-blue);
		transform: translateX(4px);
		box-shadow: 0 2px 8px var(--shadow-sm);
	}

	.trending-rank {
		flex-shrink: 0;
		width: 1.75rem;
		height: 1.75rem;
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--civic-blue);
		color: white;
		border-radius: 50%;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8rem;
		font-weight: 700;
	}

	.trending-content {
		flex: 1;
		min-width: 0;
	}

	.trending-item-header {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-bottom: 0.35rem;
		flex-wrap: wrap;
	}

	.trending-city {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.7rem;
		font-weight: 600;
		color: var(--civic-blue);
		text-transform: uppercase;
		letter-spacing: 0.5px;
	}

	.trending-item-title {
		display: block;
		font-family: Georgia, 'Times New Roman', serif;
		font-size: 0.95rem;
		font-weight: 500;
		color: var(--text-primary);
		line-height: 1.4;
		margin-bottom: 0.35rem;
	}

	.trending-meta {
		display: flex;
		gap: 0.75rem;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.7rem;
		color: var(--civic-gray);
	}

	.engagement-count,
	.user-count {
		display: flex;
		align-items: center;
		gap: 0.25rem;
	}

	@media (max-width: 640px) {
		.trending-section {
			padding: 1rem;
			margin: 1.5rem 0;
		}

		.trending-item {
			padding: 0.6rem;
			gap: 0.75rem;
		}

		.trending-rank {
			width: 1.5rem;
			height: 1.5rem;
			font-size: 0.7rem;
		}

		.trending-item-title {
			font-size: 0.9rem;
		}

		.trending-meta {
			font-size: 0.65rem;
		}
	}
</style>
