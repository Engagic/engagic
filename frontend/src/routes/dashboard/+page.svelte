<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { authState } from '$lib/stores/auth.svelte';
	import { getDashboard, type Digest, type DigestMatch } from '$lib/api/dashboard';

	let loading = $state(true);
	let error = $state<string | null>(null);

	let stats = $state({
		active_digests: 0,
		total_matches: 0,
		matches_this_week: 0,
		cities_tracked: 0
	});

	let digests = $state<Digest[]>([]);
	let recentMatches = $state<DigestMatch[]>([]);

	onMount(async () => {
		// Check auth
		if (!authState.isAuthenticated) {
			goto('/login');
			return;
		}

		try {
			const data = await getDashboard(authState.accessToken!);
			stats = data.stats;
			digests = data.digests;
			recentMatches = data.recent_matches;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load dashboard';
		} finally {
			loading = false;
		}
	});

	async function handleLogout() {
		await authState.logout();
		goto('/');
	}

	function formatDate(dateStr: string): string {
		const date = new Date(dateStr);
		return date.toLocaleDateString('en-US', {
			month: 'short',
			day: 'numeric',
			year: 'numeric'
		});
	}

	function formatTime(dateStr: string): string {
		const date = new Date(dateStr);
		const now = new Date();
		const diffMs = now.getTime() - date.getTime();
		const diffMins = Math.floor(diffMs / 60000);
		const diffHours = Math.floor(diffMins / 60);
		const diffDays = Math.floor(diffHours / 24);

		if (diffMins < 60) return `${diffMins}m ago`;
		if (diffHours < 24) return `${diffHours}h ago`;
		if (diffDays < 7) return `${diffDays}d ago`;
		return formatDate(dateStr);
	}
</script>

<svelte:head>
	<title>Dashboard - Engagic</title>
</svelte:head>

<div class="page">
	<div class="container">
		<header class="header">
			<div class="header-content">
				<h1>Dashboard</h1>
				<div class="header-actions">
					<span class="user-email">{authState.user?.email}</span>
					<button onclick={handleLogout} class="btn-logout">Log Out</button>
				</div>
			</div>
		</header>

		{#if loading}
			<div class="loading">
				<div class="spinner"></div>
				<p>Loading dashboard...</p>
			</div>
		{:else if error}
			<div class="error">
				<p>{error}</p>
			</div>
		{:else}
			<!-- Stats -->
			<div class="stats-grid">
				<div class="stat-card">
					<div class="stat-value">{stats.active_digests}</div>
					<div class="stat-label">Active Digests</div>
				</div>
				<div class="stat-card">
					<div class="stat-value">{stats.matches_this_week}</div>
					<div class="stat-label">Matches This Week</div>
				</div>
				<div class="stat-card">
					<div class="stat-value">{stats.cities_tracked}</div>
					<div class="stat-label">Cities Tracked</div>
				</div>
				<div class="stat-card">
					<div class="stat-value">{stats.total_matches}</div>
					<div class="stat-label">Total Matches</div>
				</div>
			</div>

			<!-- Digests Configuration -->
			<section class="section">
				<h2>Your Digests</h2>
				{#if digests.length > 0}
					{#each digests as digest}
						<div class="digest-card">
							<div class="digest-header">
								<h3>{digest.name}</h3>
								<span class="digest-frequency">{digest.frequency}</span>
							</div>
							<div class="digest-details">
								<div class="digest-section">
									<strong>Cities:</strong>
									{#if digest.cities.length > 0}
										<span>{digest.cities.join(', ')}</span>
									{:else}
										<span class="empty">None yet</span>
									{/if}
								</div>
								<div class="digest-section">
									<strong>Keywords:</strong>
									{#if digest.criteria.keywords.length > 0}
										<div class="keywords">
											{#each digest.criteria.keywords as keyword}
												<span class="keyword-tag">{keyword}</span>
											{/each}
										</div>
									{:else}
										<span class="empty">None yet</span>
									{/if}
								</div>
							</div>
						</div>
					{/each}
				{:else}
					<p class="empty-state">No digests configured yet</p>
				{/if}
			</section>

			<!-- Recent Activity -->
			<section class="section">
				<h2>Recent Matches</h2>
				{#if recentMatches.length > 0}
					<div class="activity-feed">
						{#each recentMatches as match}
							<div class="match-card">
								<div class="match-header">
									<h3>{match.city_name || match.city_banana}</h3>
									<span class="match-time">{formatTime(match.created_at)}</span>
								</div>
								<p class="match-meeting">{match.meeting_title}</p>
								{#if match.item_title}
									<p class="match-item">{match.item_title}</p>
								{/if}
								<div class="match-meta">
									<span class="match-type">{match.match_type}</span>
									{#if match.matched_criteria.keyword}
										<span class="matched-keyword">"{match.matched_criteria.keyword}"</span>
									{/if}
								</div>
							</div>
						{/each}
					</div>
				{:else}
					<p class="empty-state">No matches yet. Add cities and keywords to start getting digests!</p>
				{/if}
			</section>
		{/if}
	</div>
</div>

<style>
	.page {
		min-height: 100vh;
		background: var(--color-bg-primary);
		padding: 2rem;
	}

	.container {
		max-width: 1200px;
		margin: 0 auto;
	}

	.header {
		margin-bottom: 2rem;
		padding-bottom: 1rem;
		border-bottom: 1px solid var(--color-border);
	}

	.header-content {
		display: flex;
		justify-content: space-between;
		align-items: center;
		flex-wrap: wrap;
		gap: 1rem;
	}

	h1 {
		font-size: 2rem;
		font-weight: bold;
		color: var(--color-text-primary);
		margin: 0;
	}

	.header-actions {
		display: flex;
		align-items: center;
		gap: 1rem;
	}

	.user-email {
		font-size: 0.875rem;
		color: var(--color-text-secondary);
	}

	.btn-logout {
		padding: 0.5rem 1rem;
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--color-text-secondary);
		background: transparent;
		border: 1px solid var(--color-border);
		border-radius: 6px;
		cursor: pointer;
		transition: all 0.2s;
	}

	.btn-logout:hover {
		background: var(--color-bg-secondary);
		border-color: var(--color-text-tertiary);
	}

	.loading,
	.error {
		text-align: center;
		padding: 3rem;
	}

	.spinner {
		width: 48px;
		height: 48px;
		margin: 0 auto 1rem;
		border: 4px solid var(--color-border);
		border-top-color: var(--color-primary);
		border-radius: 50%;
		animation: spin 1s linear infinite;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	.stats-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
		gap: 1rem;
		margin-bottom: 2rem;
	}

	.stat-card {
		background: var(--color-bg-primary);
		border: 1px solid var(--color-border);
		border-radius: 8px;
		padding: 1.5rem;
		text-align: center;
	}

	.stat-value {
		font-size: 2.5rem;
		font-weight: bold;
		color: var(--color-primary);
		margin-bottom: 0.5rem;
	}

	.stat-label {
		font-size: 0.875rem;
		color: var(--color-text-secondary);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.section {
		margin-bottom: 2rem;
	}

	h2 {
		font-size: 1.5rem;
		font-weight: bold;
		color: var(--color-text-primary);
		margin: 0 0 1rem 0;
	}

	.digest-card {
		background: var(--color-bg-primary);
		border: 1px solid var(--color-border);
		border-radius: 8px;
		padding: 1.5rem;
		margin-bottom: 1rem;
	}

	.digest-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 1rem;
	}

	h3 {
		font-size: 1.125rem;
		font-weight: 600;
		color: var(--color-text-primary);
		margin: 0;
	}

	.digest-frequency {
		font-size: 0.8125rem;
		padding: 0.25rem 0.75rem;
		background: var(--color-bg-secondary);
		border: 1px solid var(--color-border);
		border-radius: 12px;
		color: var(--color-text-secondary);
		text-transform: capitalize;
	}

	.digest-details {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.digest-section {
		font-size: 0.875rem;
	}

	.digest-section strong {
		color: var(--color-text-primary);
		margin-right: 0.5rem;
	}

	.keywords {
		display: inline-flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin-left: 0.5rem;
	}

	.keyword-tag {
		padding: 0.25rem 0.75rem;
		background: var(--color-primary-light);
		color: var(--color-primary);
		border-radius: 12px;
		font-size: 0.8125rem;
		font-weight: 500;
	}

	.empty {
		color: var(--color-text-tertiary);
		font-style: italic;
	}

	.empty-state {
		text-align: center;
		padding: 2rem;
		color: var(--color-text-tertiary);
		font-style: italic;
	}

	.activity-feed {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.match-card {
		background: var(--color-bg-primary);
		border: 1px solid var(--color-border);
		border-radius: 8px;
		padding: 1.25rem;
	}

	.match-header {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		margin-bottom: 0.5rem;
	}

	.match-time {
		font-size: 0.8125rem;
		color: var(--color-text-tertiary);
	}

	.match-meeting {
		font-size: 0.9375rem;
		color: var(--color-text-secondary);
		margin: 0.5rem 0;
	}

	.match-item {
		font-size: 0.875rem;
		color: var(--color-text-tertiary);
		margin: 0.25rem 0;
	}

	.match-meta {
		display: flex;
		gap: 0.75rem;
		margin-top: 0.75rem;
	}

	.match-type {
		padding: 0.25rem 0.75rem;
		background: var(--color-bg-secondary);
		border: 1px solid var(--color-border);
		border-radius: 12px;
		font-size: 0.75rem;
		color: var(--color-text-secondary);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.matched-keyword {
		padding: 0.25rem 0.75rem;
		background: var(--color-primary-light);
		border-radius: 12px;
		font-size: 0.75rem;
		color: var(--color-primary);
		font-weight: 500;
	}

	@media (max-width: 768px) {
		.page {
			padding: 1rem;
		}

		.stats-grid {
			grid-template-columns: repeat(2, 1fr);
		}

		.digest-header {
			flex-direction: column;
			align-items: flex-start;
			gap: 0.5rem;
		}
	}
</style>
