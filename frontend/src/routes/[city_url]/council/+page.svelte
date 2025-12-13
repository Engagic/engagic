<script lang="ts">
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import { getCityCouncilMembers, searchMeetings } from '$lib/api';
	import type { CouncilMember } from '$lib/api/types';
	import { isSearchSuccess } from '$lib/api/types';
	import Footer from '$lib/components/Footer.svelte';
	import { logger } from '$lib/services/logger';

	// Route param is always defined on this page
	const city_banana = $page.params.city_url as string;

	let councilMembers = $state<CouncilMember[]>([]);
	let cityName = $state<string>('');
	let stateName = $state<string>('');
	let loading = $state(true);
	let error = $state<string | null>(null);

	// Computed stats
	const activeMembers = $derived(councilMembers.filter(m => m.status === 'active'));
	const totalVotes = $derived(councilMembers.reduce((sum, m) => sum + m.vote_count, 0));
	const totalSponsorships = $derived(councilMembers.reduce((sum, m) => sum + m.sponsorship_count, 0));

	onMount(async () => {
		try {
			// Fetch council members and city info in parallel
			const [councilResponse, searchResponse] = await Promise.all([
				getCityCouncilMembers(city_banana),
				searchMeetings(city_banana)
			]);

			councilMembers = councilResponse.council_members || [];
			cityName = councilResponse.city_name || '';
			stateName = councilResponse.state || '';

			// If we got city info from search, use that too
			if (isSearchSuccess(searchResponse)) {
				cityName = searchResponse.city_name;
				stateName = searchResponse.state;
			}
		} catch (e) {
			logger.error('Failed to load council members', {}, e instanceof Error ? e : undefined);
			error = 'Unable to load council roster. This city may not have voting data yet.';
		} finally {
			loading = false;
		}
	});

	function formatDate(dateStr: string): string {
		if (!dateStr) return '';
		const date = new Date(dateStr);
		return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
	}
</script>

<svelte:head>
	<title>City Council - {cityName || city_banana} - engagic</title>
	<meta name="description" content="City council roster and voting records for {cityName}" />
</svelte:head>

<div class="container">
	<div class="top-nav">
		<a href="/{city_banana}" class="back-link" data-sveltekit-preload-data="hover">
			← {cityName || 'Back to City'}
		</a>
		<a href="/" class="compact-logo" aria-label="Return to engagic homepage" data-sveltekit-preload-data="hover">
			<img src="/icon-64.png" alt="engagic" class="logo-icon" />
		</a>
	</div>

	<div class="page-header">
		<h1 class="page-title">City Council</h1>
		{#if cityName}
			<p class="page-subtitle">{cityName}, {stateName}</p>
		{/if}
	</div>

	{#if loading}
		<div class="loading-state">Loading council roster...</div>
	{:else if error}
		<div class="error-state">
			<p>{error}</p>
			<a href="/{city_banana}" class="back-cta">Return to city page</a>
		</div>
	{:else if councilMembers.length === 0}
		<div class="empty-state">
			<p>No council member data available for this city yet.</p>
			<p class="empty-hint">Voting and council data is being added as we process more meetings.</p>
		</div>
	{:else}
		<div class="stats-bar">
			<div class="stat">
				<span class="stat-value">{activeMembers.length}</span>
				<span class="stat-label">Active Members</span>
			</div>
			<div class="stat">
				<span class="stat-value">{totalVotes.toLocaleString()}</span>
				<span class="stat-label">Votes Recorded</span>
			</div>
			<div class="stat">
				<span class="stat-value">{totalSponsorships.toLocaleString()}</span>
				<span class="stat-label">Sponsorships</span>
			</div>
		</div>

		<div class="council-roster">
			{#each councilMembers as member (member.id)}
				<a
					href="/{city_banana}/council/{member.id}"
					class="council-member-card"
					class:inactive={member.status !== 'active'}
					data-sveltekit-preload-data="tap"
				>
					<div class="member-info">
						<div class="member-header">
							<span class="member-name">{member.name}</span>
							{#if member.status !== 'active'}
								<span class="status-badge former">Former</span>
							{/if}
						</div>
						{#if member.title || member.district}
							<div class="member-role">
								{#if member.title}{member.title}{/if}
								{#if member.title && member.district} - {/if}
								{#if member.district}District {member.district}{/if}
							</div>
						{/if}
						<div class="member-activity">
							<span>Active: {formatDate(member.first_seen)} - {member.status === 'active' ? 'Present' : formatDate(member.last_seen)}</span>
						</div>
					</div>
					<div class="member-stats">
						<div class="member-stat">
							<span class="stat-num">{member.vote_count}</span>
							<span class="stat-name">votes</span>
						</div>
						<div class="member-stat">
							<span class="stat-num">{member.sponsorship_count}</span>
							<span class="stat-name">sponsored</span>
						</div>
					</div>
					<div class="member-arrow">→</div>
				</a>
			{/each}
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

	.council-roster {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.council-member-card {
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

	.council-member-card:hover {
		border-left-color: var(--civic-accent);
		transform: translateX(4px);
		box-shadow: 0 4px 12px var(--shadow-sm);
	}

	.council-member-card.inactive {
		border-left-color: var(--civic-gray);
		opacity: 0.7;
	}

	.member-info {
		flex: 1;
		min-width: 0;
	}

	.member-header {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-bottom: 0.25rem;
	}

	.member-name {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1rem;
		font-weight: 600;
		color: var(--text-primary);
	}

	.status-badge.former {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.65rem;
		padding: 0.15rem 0.5rem;
		background: var(--surface-secondary);
		color: var(--civic-gray);
		border: 1px solid var(--border-primary);
		border-radius: 10px;
		text-transform: uppercase;
	}

	.member-role {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8rem;
		color: var(--civic-gray);
	}

	.member-activity {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.7rem;
		color: var(--text-secondary);
		margin-top: 0.25rem;
	}

	.member-stats {
		display: flex;
		gap: 1.5rem;
	}

	.member-stat {
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

	.member-arrow {
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

		.council-member-card {
			flex-wrap: wrap;
			padding: 0.75rem 1rem;
		}

		.member-stats {
			width: 100%;
			justify-content: flex-start;
			gap: 1rem;
			margin-top: 0.5rem;
		}
	}
</style>
