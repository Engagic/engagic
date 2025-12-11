<script lang="ts">
	import { onMount } from 'svelte';
	import { config } from '$lib/api/config';

	let stats: any = null;
	let loading = true;
	let error = '';

	onMount(() => {
		loadStats();
		const interval = setInterval(loadStats, 30000);
		return () => clearInterval(interval);
	});

	async function loadStats() {
		try {
			const res = await fetch(`${config.apiBaseUrl}/api/funnel`);
			if (!res.ok) throw new Error('Failed to load');
			stats = await res.json();
		} catch (e) {
			error = 'Failed to load stats';
		} finally {
			loading = false;
		}
	}

	function pct(a: number, b: number): string {
		if (b === 0) return '-';
		return Math.round((a / b) * 100) + '%';
	}
</script>

<svelte:head>
	<title>User Funnel - Engagic</title>
</svelte:head>

<div class="funnel-page">
	<h1>User Behavior</h1>
	<p class="subtitle">What people do on engagic (since last deploy)</p>

	{#if loading}
		<p>Loading...</p>
	{:else if error}
		<p class="error">{error}</p>
	{:else if stats}
		<section class="section">
			<h2>Search Funnel</h2>
			<div class="funnel">
				<div class="funnel-step">
					<div class="step-value">{stats.search.success + stats.search.not_found + stats.search.ambiguous}</div>
					<div class="step-label">Searches</div>
				</div>
				<div class="funnel-arrow">-></div>
				<div class="funnel-step good">
					<div class="step-value">{stats.search.success}</div>
					<div class="step-label">Found City</div>
					<div class="step-pct">{pct(stats.search.success, stats.search.success + stats.search.not_found + stats.search.ambiguous)}</div>
				</div>
				<div class="funnel-step warn">
					<div class="step-value">{stats.search.not_found}</div>
					<div class="step-label">No Data</div>
				</div>
				<div class="funnel-step">
					<div class="step-value">{stats.search.ambiguous}</div>
					<div class="step-label">Multiple Cities</div>
				</div>
			</div>
		</section>

		<section class="section">
			<h2>Engagement</h2>
			<div class="stats-grid">
				<div class="stat">
					<div class="stat-value">{stats.pages.meeting}</div>
					<div class="stat-label">Meeting Views</div>
				</div>
				<div class="stat">
					<div class="stat-value">{stats.engagement.item_expand}</div>
					<div class="stat-label">Items Expanded</div>
				</div>
				<div class="stat">
					<div class="stat-value">{stats.engagement.matter_view}</div>
					<div class="stat-label">Matter Views</div>
				</div>
				<div class="stat">
					<div class="stat-value">{stats.engagement.flyer_click}</div>
					<div class="stat-label">Flyers Generated</div>
				</div>
				<div class="stat">
					<div class="stat-value">{stats.pages.deliberate}</div>
					<div class="stat-label">Deliberate Views</div>
				</div>
			</div>
		</section>

		<section class="section">
			<h2>Signup Funnel</h2>
			<div class="funnel">
				<div class="funnel-step">
					<div class="step-value">{stats.pages.signup}</div>
					<div class="step-label">Signup Page Views</div>
				</div>
				<div class="funnel-arrow">-></div>
				<div class="funnel-step good">
					<div class="step-value">{stats.engagement.signup_complete}</div>
					<div class="step-label">Signups</div>
					<div class="step-pct">{pct(stats.engagement.signup_complete, stats.pages.signup)} conversion</div>
				</div>
			</div>
		</section>

		<p class="note">
			Unique visitors: Check <a href="https://dash.cloudflare.com" target="_blank">Cloudflare Web Analytics</a>
		</p>
	{/if}
</div>

<style>
	.funnel-page {
		max-width: 900px;
		margin: 0 auto;
		padding: 2rem;
		font-family: system-ui, -apple-system, sans-serif;
	}

	h1 {
		margin: 0 0 0.25rem 0;
		font-size: 1.75rem;
	}

	.subtitle {
		color: #666;
		margin: 0 0 2rem 0;
	}

	.section {
		background: #f9fafb;
		padding: 1.5rem;
		border-radius: 8px;
		margin-bottom: 1.5rem;
	}

	h2 {
		margin: 0 0 1rem 0;
		font-size: 1.1rem;
		color: #374151;
	}

	.funnel {
		display: flex;
		align-items: center;
		gap: 1rem;
		flex-wrap: wrap;
	}

	.funnel-step {
		background: white;
		padding: 1rem 1.5rem;
		border-radius: 6px;
		border-left: 3px solid #9ca3af;
		min-width: 120px;
	}

	.funnel-step.good {
		border-left-color: #22c55e;
	}

	.funnel-step.warn {
		border-left-color: #f59e0b;
	}

	.funnel-arrow {
		color: #9ca3af;
		font-size: 1.5rem;
	}

	.step-value {
		font-size: 1.75rem;
		font-weight: 600;
	}

	.step-label {
		font-size: 0.85rem;
		color: #666;
	}

	.step-pct {
		font-size: 0.75rem;
		color: #22c55e;
		margin-top: 0.25rem;
	}

	.stats-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
		gap: 1rem;
	}

	.stat {
		background: white;
		padding: 1rem;
		border-radius: 6px;
		text-align: center;
	}

	.stat-value {
		font-size: 1.5rem;
		font-weight: 600;
	}

	.stat-label {
		font-size: 0.8rem;
		color: #666;
	}

	.note {
		color: #666;
		font-size: 0.85rem;
		margin-top: 2rem;
	}

	.note a {
		color: #2563eb;
	}

	.error {
		color: #dc2626;
	}
</style>
