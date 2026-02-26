<script lang="ts">
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import { getCityCommittees, searchMeetings } from '$lib/api';
	import SeoHead from '$lib/components/SeoHead.svelte';
	import type { Committee } from '$lib/api/types';
	import { isSearchSuccess } from '$lib/api/types';
	import Footer from '$lib/components/Footer.svelte';
	import { logger } from '$lib/services/logger';

	const city_banana = $page.params.city_url as string;

	let committees = $state<Committee[]>([]);
	let cityName = $state<string>('');
	let stateName = $state<string>('');
	let loading = $state(true);
	let error = $state<string | null>(null);

	const activeCommittees = $derived(committees.filter(c => c.status === 'active'));
	const inactiveCommittees = $derived(committees.filter(c => c.status !== 'active'));
	const totalMembers = $derived(committees.reduce((sum, c) => sum + (c.member_count || 0), 0));

	onMount(async () => {
		try {
			const [committeesResponse, searchResponse] = await Promise.all([
				getCityCommittees(city_banana),
				searchMeetings(city_banana)
			]);

			committees = committeesResponse.committees || [];
			cityName = committeesResponse.city_name || '';
			stateName = committeesResponse.state || '';

			if (isSearchSuccess(searchResponse)) {
				cityName = searchResponse.city_name;
				stateName = searchResponse.state;
			}
		} catch (e) {
			logger.error('Failed to load committees', {}, e instanceof Error ? e : undefined);
			error = 'Unable to load committees. This city may not have committee data yet.';
		} finally {
			loading = false;
		}
	});
</script>

<SeoHead
	title="Committees - {cityName || city_banana} - engagic"
	description="Legislative committees for {cityName}"
	url="https://engagic.org/{city_banana}/committees"
/>

<div class="container">
	<div class="top-nav">
		<a href="/{city_banana}" class="back-link" data-sveltekit-preload-data="hover">
			&larr; {cityName || 'Back to City'}
		</a>
		<a href="/" class="compact-logo" aria-label="Return to engagic homepage" data-sveltekit-preload-data="hover">
			<img src="/icon-64.png" alt="engagic" class="logo-icon" />
		</a>
	</div>

	<div class="page-header">
		<h1 class="page-title">Committees</h1>
		{#if cityName}
			<p class="page-subtitle">{cityName}, {stateName}</p>
		{/if}
	</div>

	{#if loading}
		<div class="loading-state">Loading committees...</div>
	{:else if error}
		<div class="error-state">
			<p>{error}</p>
			<a href="/{city_banana}" class="back-cta">Return to city page</a>
		</div>
	{:else if committees.length === 0}
		<div class="empty-state">
			<p>No committee data available for this city yet.</p>
			<p class="empty-hint">Committee data is being added as we process more meetings.</p>
		</div>
	{:else}
		<div class="stats-bar">
			<div class="stat">
				<span class="stat-value">{activeCommittees.length}</span>
				<span class="stat-label">Active Committees</span>
			</div>
			<div class="stat">
				<span class="stat-value">{totalMembers}</span>
				<span class="stat-label">Total Seats</span>
			</div>
		</div>

		<div class="committees-list">
			{#each activeCommittees as committee (committee.id)}
				<a
					href="/{city_banana}/committees/{committee.id}"
					class="committee-card"
					data-sveltekit-preload-data="tap"
				>
					<div class="committee-info">
						<span class="committee-name">{committee.name}</span>
						{#if committee.description}
							<span class="committee-description">{committee.description}</span>
						{/if}
					</div>
					<div class="committee-stats">
						<div class="committee-stat">
							<span class="stat-num">{committee.member_count || 0}</span>
							<span class="stat-name">members</span>
						</div>
					</div>
					<div class="committee-arrow">&rarr;</div>
				</a>
			{/each}

			{#if inactiveCommittees.length > 0}
				<h3 class="section-divider">Inactive Committees</h3>
				{#each inactiveCommittees as committee (committee.id)}
					<a
						href="/{city_banana}/committees/{committee.id}"
						class="committee-card inactive"
						data-sveltekit-preload-data="tap"
					>
						<div class="committee-info">
							<span class="committee-name">{committee.name}</span>
							<span class="status-badge">Inactive</span>
						</div>
						<div class="committee-stats">
							<div class="committee-stat">
								<span class="stat-num">{committee.member_count || 0}</span>
								<span class="stat-name">members</span>
							</div>
						</div>
						<div class="committee-arrow">&rarr;</div>
					</a>
				{/each}
			{/if}
		</div>
	{/if}

	<Footer />
</div>

<style>
	.container {
		width: var(--width-detail);
		padding: 2rem 1rem;
		margin: 0 auto;
	}

	.top-nav {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 1.5rem;
	}

	.back-link {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
		color: var(--civic-blue);
		text-decoration: none;
		font-weight: 500;
	}

	.back-link:hover {
		color: var(--civic-accent);
		text-decoration: underline;
	}

	.compact-logo {
		transition: transform 0.2s ease;
	}

	.compact-logo:hover {
		transform: scale(1.05);
	}

	.logo-icon {
		width: 48px;
		height: 48px;
		border-radius: 12px;
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
	}

	.page-header {
		margin-bottom: 2rem;
	}

	.page-title {
		font-family: Georgia, 'Times New Roman', serif;
		font-size: 2rem;
		font-weight: 700;
		color: var(--text-primary);
		margin: 0;
	}

	.page-subtitle {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1rem;
		color: var(--civic-gray);
		margin: 0.5rem 0 0;
	}

	.loading-state,
	.error-state,
	.empty-state {
		text-align: center;
		padding: 3rem;
		background: var(--surface-secondary);
		border-radius: 12px;
		border: 1px solid var(--border-primary);
	}

	.loading-state {
		font-family: 'IBM Plex Mono', monospace;
		color: var(--civic-gray);
	}

	.error-state p,
	.empty-state p {
		font-family: 'IBM Plex Mono', monospace;
		color: var(--text-primary);
		margin: 0 0 1rem;
	}

	.empty-hint {
		font-size: 0.9rem;
		color: var(--civic-gray);
	}

	.back-cta {
		display: inline-block;
		margin-top: 1rem;
		padding: 0.5rem 1rem;
		background: var(--civic-blue);
		color: white;
		border-radius: 6px;
		text-decoration: none;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
	}

	.stats-bar {
		display: flex;
		gap: 2rem;
		padding: 1.25rem;
		background: var(--surface-primary);
		border: 1px solid var(--border-primary);
		border-radius: 12px;
		margin-bottom: 1.5rem;
		justify-content: center;
	}

	.stat {
		text-align: center;
	}

	.stat-value {
		display: block;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.5rem;
		font-weight: 700;
		color: var(--civic-blue);
	}

	.stat-label {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		color: var(--civic-gray);
		text-transform: uppercase;
		letter-spacing: 0.5px;
	}

	.committees-list {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.section-divider {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
		font-weight: 600;
		color: var(--civic-gray);
		margin: 1.5rem 0 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.5px;
	}

	.committee-card {
		display: flex;
		align-items: center;
		gap: 1rem;
		padding: 1rem 1.25rem;
		background: var(--surface-primary);
		border: 1px solid var(--border-primary);
		border-left: 4px solid var(--civic-blue);
		border-radius: 8px;
		text-decoration: none;
		transition: all 0.2s ease;
	}

	.committee-card:hover {
		border-left-color: var(--civic-accent);
		transform: translateX(4px);
		box-shadow: 0 4px 12px var(--shadow-sm);
	}

	.committee-card.inactive {
		border-left-color: var(--civic-gray);
		opacity: 0.7;
	}

	.committee-info {
		flex: 1;
		min-width: 0;
	}

	.committee-name {
		display: block;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1rem;
		font-weight: 600;
		color: var(--text-primary);
		margin-bottom: 0.25rem;
	}

	.committee-description {
		display: block;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8rem;
		color: var(--civic-gray);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.status-badge {
		display: inline-block;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.65rem;
		padding: 0.15rem 0.5rem;
		background: var(--surface-secondary);
		color: var(--civic-gray);
		border: 1px solid var(--border-primary);
		border-radius: 10px;
		text-transform: uppercase;
		margin-top: 0.25rem;
	}

	.committee-stats {
		display: flex;
		gap: 1.5rem;
	}

	.committee-stat {
		text-align: center;
	}

	.stat-num {
		display: block;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.1rem;
		font-weight: 700;
		color: var(--text-primary);
	}

	.stat-name {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.65rem;
		color: var(--civic-gray);
		text-transform: uppercase;
	}

	.committee-arrow {
		flex-shrink: 0;
		font-size: 1.2rem;
		color: var(--civic-blue);
	}

	@media (max-width: 640px) {
		.container {
			padding: 1rem;
		}

		.page-title {
			font-size: 1.5rem;
		}

		.stats-bar {
			gap: 1rem;
			padding: 1rem;
		}

		.stat-value {
			font-size: 1.25rem;
		}

		.committee-card {
			flex-wrap: wrap;
			padding: 0.75rem 1rem;
		}

		.committee-stats {
			width: 100%;
			justify-content: flex-start;
			gap: 1rem;
			margin-top: 0.5rem;
		}
	}
</style>
