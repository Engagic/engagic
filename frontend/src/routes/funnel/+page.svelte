<script lang="ts">
	import { onMount } from 'svelte';
	import { config } from '$lib/api/config';
	import { logger } from '$lib/services/logger';

	interface JourneyEvent {
		event: string;
		url: string | null;
		properties: Record<string, unknown> | null;
		at: string;
	}

	interface Journey {
		ip_hash: string;
		events: JourneyEvent[];
		count: number;
	}

	interface Pattern {
		path: string;
		count: number;
	}

	interface Dropoff {
		event: string;
		url: string | null;
		count: number;
	}

	// Auth state
	let adminToken = $state('');
	let isAuthenticated = $state(false);
	let authError = $state('');

	let journeys: Journey[] = $state([]);
	let patterns: Pattern[] = $state([]);
	let dropoffs: Dropoff[] = $state([]);
	let uniqueUsers = $state(0);
	let hours = $state(24);
	let loading = $state(true);
	let error = $state('');
	let activeTab: 'journeys' | 'patterns' | 'dropoffs' = $state('journeys');

	let refreshInterval: ReturnType<typeof setInterval> | null = null;

	onMount(() => {
		const stored = localStorage.getItem('engagic_admin_token');
		if (stored) {
			adminToken = stored;
			verifyAndLoad();
		} else {
			loading = false;
		}
		return () => {
			if (refreshInterval) clearInterval(refreshInterval);
		};
	});

	async function verifyAndLoad() {
		loading = true;
		authError = '';
		try {
			const res = await fetch(`${config.apiBaseUrl}/api/funnel/journeys?hours=1&limit=1`, {
				headers: { Authorization: `Bearer ${adminToken}` }
			});
			if (res.ok) {
				localStorage.setItem('engagic_admin_token', adminToken);
				isAuthenticated = true;
				await loadAll();
				refreshInterval = setInterval(loadAll, 60000);
			} else {
				authError = 'Invalid admin token';
				localStorage.removeItem('engagic_admin_token');
				loading = false;
			}
		} catch (e) {
			authError = 'Failed to connect to API';
			loading = false;
		}
	}

	function logout() {
		localStorage.removeItem('engagic_admin_token');
		isAuthenticated = false;
		adminToken = '';
		journeys = [];
		patterns = [];
		dropoffs = [];
		uniqueUsers = 0;
		if (refreshInterval) {
			clearInterval(refreshInterval);
			refreshInterval = null;
		}
	}

	async function loadAll() {
		loading = true;
		error = '';
		try {
			const headers = { Authorization: `Bearer ${adminToken}` };
			const [journeysRes, patternsRes, dropoffsRes] = await Promise.all([
				fetch(`${config.apiBaseUrl}/api/funnel/journeys?hours=${hours}&limit=50`, { headers }),
				fetch(`${config.apiBaseUrl}/api/funnel/patterns?hours=${hours}`, { headers }),
				fetch(`${config.apiBaseUrl}/api/funnel/dropoffs?hours=${hours}`, { headers })
			]);

			if (!journeysRes.ok || !patternsRes.ok || !dropoffsRes.ok) {
				throw new Error('Failed to load data');
			}

			const journeysData = await journeysRes.json();
			const patternsData = await patternsRes.json();
			const dropoffsData = await dropoffsRes.json();

			journeys = journeysData.journeys;
			uniqueUsers = journeysData.unique_users;
			patterns = patternsData.patterns;
			dropoffs = dropoffsData.dropoffs;
		} catch (e) {
			error = 'Failed to load analytics data';
			logger.error('Failed to load analytics data', {}, e instanceof Error ? e : undefined);
		} finally {
			loading = false;
		}
	}

	function formatTime(isoString: string): string {
		const date = new Date(isoString);
		return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
	}

	function truncateHash(hash: string): string {
		return hash.slice(0, 8);
	}

	function getEventColor(event: string): string {
		if (event === 'page_view') return '#3b82f6';
		if (event.includes('search')) return '#8b5cf6';
		if (event.includes('click')) return '#22c55e';
		if (event.includes('view')) return '#f59e0b';
		return '#6b7280';
	}
</script>

<svelte:head>
	<title>User Journeys - Engagic</title>
</svelte:head>

<div class="journey-page">
	{#if !isAuthenticated}
		<div class="auth-container">
			<h1>User Journeys</h1>
			<p class="subtitle">Enter admin token to access analytics</p>
			<form class="auth-form" onsubmit={(e) => { e.preventDefault(); verifyAndLoad(); }}>
				<input
					type="password"
					bind:value={adminToken}
					placeholder="Admin token"
					class="token-input"
				/>
				<button type="submit" disabled={loading || !adminToken}>
					{loading ? 'Verifying...' : 'Login'}
				</button>
			</form>
			{#if authError}
				<p class="auth-error">{authError}</p>
			{/if}
		</div>
	{:else}
		<header class="page-header">
			<div class="header-top">
				<h1>User Journeys</h1>
				<button class="logout-btn" onclick={logout}>Logout</button>
			</div>
			<p class="subtitle">Individual visitor flows and behavior patterns</p>
			<div class="controls">
				<select bind:value={hours} onchange={() => loadAll()}>
					<option value={1}>Last hour</option>
					<option value={6}>Last 6 hours</option>
					<option value={24}>Last 24 hours</option>
					<option value={48}>Last 48 hours</option>
					<option value={168}>Last 7 days</option>
				</select>
				<span class="user-count">{uniqueUsers} unique users</span>
			</div>
		</header>

	<nav class="tabs">
		<button class:active={activeTab === 'journeys'} onclick={() => (activeTab = 'journeys')}>
			Journeys
		</button>
		<button class:active={activeTab === 'patterns'} onclick={() => (activeTab = 'patterns')}>
			Patterns
		</button>
		<button class:active={activeTab === 'dropoffs'} onclick={() => (activeTab = 'dropoffs')}>
			Drop-offs
		</button>
	</nav>

	{#if loading}
		<div class="loading">Loading...</div>
	{:else if error}
		<div class="error">{error}</div>
	{:else}
		{#if activeTab === 'journeys'}
			<section class="journeys-section">
				{#if journeys.length === 0}
					<p class="empty">No journeys recorded yet. Events will appear as users interact.</p>
				{:else}
					{#each journeys as journey (journey.ip_hash)}
						<div class="journey-card">
							<div class="journey-header">
								<span class="user-hash">{truncateHash(journey.ip_hash)}</span>
								<span class="event-count">{journey.count} events</span>
							</div>
							<div class="event-timeline">
								{#each journey.events as event, i (i)}
									<div class="event-item">
										<span class="event-dot" style="background-color: {getEventColor(event.event)}"></span>
										<span class="event-name">{event.event}</span>
										{#if event.url}
											<span class="event-url">{event.url}</span>
										{/if}
										<span class="event-time">{formatTime(event.at)}</span>
									</div>
								{/each}
							</div>
						</div>
					{/each}
				{/if}
			</section>
		{:else if activeTab === 'patterns'}
			<section class="patterns-section">
				{#if patterns.length === 0}
					<p class="empty">No patterns detected yet.</p>
				{:else}
					<div class="patterns-list">
						{#each patterns as pattern, i (pattern.path)}
							<div class="pattern-row">
								<span class="pattern-rank">#{i + 1}</span>
								<span class="pattern-path">{pattern.path}</span>
								<span class="pattern-count">{pattern.count} users</span>
							</div>
						{/each}
					</div>
				{/if}
			</section>
		{:else if activeTab === 'dropoffs'}
			<section class="dropoffs-section">
				<p class="section-desc">Where users leave (last event in their session)</p>
				{#if dropoffs.length === 0}
					<p class="empty">No drop-off data yet.</p>
				{:else}
					<div class="dropoffs-list">
						{#each dropoffs as dropoff, i (dropoff.event + dropoff.url)}
							<div class="dropoff-row">
								<span class="dropoff-rank">#{i + 1}</span>
								<span class="dropoff-event">{dropoff.event}</span>
								{#if dropoff.url}
									<span class="dropoff-url">{dropoff.url}</span>
								{/if}
								<span class="dropoff-count">{dropoff.count} users</span>
							</div>
						{/each}
					</div>
				{/if}
			</section>
		{/if}
	{/if}
	{/if}
</div>

<style>
	.journey-page {
		max-width: 1000px;
		margin: 0 auto;
		padding: 2rem;
		font-family: system-ui, -apple-system, sans-serif;
	}

	.auth-container {
		max-width: 400px;
		margin: 4rem auto;
		text-align: center;
	}

	.auth-form {
		display: flex;
		gap: 0.5rem;
		margin-top: 1.5rem;
	}

	.token-input {
		flex: 1;
		padding: 0.75rem 1rem;
		border: 1px solid #d1d5db;
		border-radius: 6px;
		font-size: 0.9rem;
	}

	.auth-form button {
		padding: 0.75rem 1.5rem;
		background: #3b82f6;
		color: white;
		border: none;
		border-radius: 6px;
		font-size: 0.9rem;
		cursor: pointer;
	}

	.auth-form button:disabled {
		background: #93c5fd;
		cursor: not-allowed;
	}

	.auth-error {
		color: #dc2626;
		margin-top: 1rem;
		font-size: 0.9rem;
	}

	.header-top {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.logout-btn {
		padding: 0.4rem 0.8rem;
		background: none;
		border: 1px solid #d1d5db;
		border-radius: 4px;
		font-size: 0.8rem;
		color: #6b7280;
		cursor: pointer;
	}

	.logout-btn:hover {
		background: #f3f4f6;
	}

	.page-header {
		margin-bottom: 2rem;
	}

	h1 {
		margin: 0 0 0.25rem 0;
		font-size: 1.75rem;
	}

	.subtitle {
		color: #666;
		margin: 0 0 1rem 0;
	}

	.controls {
		display: flex;
		gap: 1rem;
		align-items: center;
	}

	select {
		padding: 0.5rem 1rem;
		border: 1px solid var(--civic-border);
		border-radius: 6px;
		font-size: 0.9rem;
		color: var(--text-primary);
		background: var(--surface-primary);
	}

	.user-count {
		font-size: 0.9rem;
		color: #6b7280;
	}

	.tabs {
		display: flex;
		gap: 0.5rem;
		margin-bottom: 1.5rem;
		border-bottom: 1px solid #e5e7eb;
		padding-bottom: 0.5rem;
	}

	.tabs button {
		padding: 0.5rem 1rem;
		border: none;
		background: none;
		font-size: 0.9rem;
		color: #6b7280;
		cursor: pointer;
		border-radius: 4px;
	}

	.tabs button:hover {
		background: #f3f4f6;
	}

	.tabs button.active {
		background: #3b82f6;
		color: white;
	}

	.loading,
	.error,
	.empty {
		text-align: center;
		padding: 3rem;
		color: #6b7280;
	}

	.error {
		color: #dc2626;
	}

	.journey-card {
		background: #f9fafb;
		border-radius: 8px;
		padding: 1rem;
		margin-bottom: 1rem;
	}

	.journey-header {
		display: flex;
		justify-content: space-between;
		margin-bottom: 0.75rem;
		padding-bottom: 0.5rem;
		border-bottom: 1px solid #e5e7eb;
	}

	.user-hash {
		font-family: monospace;
		font-size: 0.85rem;
		background: #e5e7eb;
		padding: 0.2rem 0.5rem;
		border-radius: 4px;
	}

	.event-count {
		font-size: 0.85rem;
		color: #6b7280;
	}

	.event-timeline {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.event-item {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		font-size: 0.85rem;
	}

	.event-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		flex-shrink: 0;
	}

	.event-name {
		font-weight: 500;
		min-width: 120px;
	}

	.event-url {
		color: #6b7280;
		flex: 1;
	}

	.event-time {
		color: #9ca3af;
		font-size: 0.8rem;
	}

	.section-desc {
		color: #6b7280;
		font-size: 0.9rem;
		margin-bottom: 1rem;
	}

	.patterns-list,
	.dropoffs-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.pattern-row,
	.dropoff-row {
		display: flex;
		align-items: center;
		gap: 1rem;
		padding: 0.75rem 1rem;
		background: #f9fafb;
		border-radius: 6px;
	}

	.pattern-rank,
	.dropoff-rank {
		font-weight: 600;
		color: #9ca3af;
		width: 2rem;
	}

	.pattern-path {
		flex: 1;
		font-family: monospace;
		font-size: 0.85rem;
		color: #374151;
	}

	.pattern-count,
	.dropoff-count {
		font-size: 0.85rem;
		color: #6b7280;
		background: #e5e7eb;
		padding: 0.2rem 0.5rem;
		border-radius: 4px;
	}

	.dropoff-event {
		font-weight: 500;
		min-width: 120px;
	}

	.dropoff-url {
		flex: 1;
		color: #6b7280;
	}
</style>
