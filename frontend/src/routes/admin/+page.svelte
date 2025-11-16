<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { config } from '$lib/api/config';

	const API_BASE = config.apiBaseUrl;

	// Auth state
	let adminToken = '';
	let isAuthenticated = false;
	let authError = '';

	// Metrics data
	let metrics: any = null;
	let loading = true;
	let error = '';
	let lastUpdate = '';

	// Time range
	let timeRange = '1h'; // 1h, 6h, 24h, 7d, 30d

	onMount(() => {
		// Check for stored token
		const stored = localStorage.getItem('engagic_admin_token');
		if (stored) {
			adminToken = stored;
			isAuthenticated = true;
			loadMetrics();
			// Auto-refresh every 30 seconds
			const interval = setInterval(loadMetrics, 30000);
			return () => clearInterval(interval);
		}
	});

	async function authenticate() {
		authError = '';
		try {
			// Test token by querying live metrics
			const response = await fetch(`${API_BASE}/api/admin/live-metrics`, {
				headers: {
					Authorization: `Bearer ${adminToken}`
				}
			});

			if (response.ok) {
				localStorage.setItem('engagic_admin_token', adminToken);
				isAuthenticated = true;
				loadMetrics();
			} else {
				authError = 'Invalid admin token';
			}
		} catch (e) {
			authError = 'Failed to connect to API';
		}
	}

	function logout() {
		localStorage.removeItem('engagic_admin_token');
		isAuthenticated = false;
		adminToken = '';
		metrics = null;
	}

	async function loadMetrics() {
		loading = true;
		error = '';

		try {
			const response = await fetch(`${API_BASE}/api/admin/live-metrics`, {
				headers: {
					Authorization: `Bearer ${adminToken}`
				}
			});

			if (!response.ok) {
				throw new Error('Failed to load metrics');
			}

			const data = await response.json();
			metrics = data.metrics;
			lastUpdate = new Date(data.timestamp * 1000).toLocaleTimeString();
		} catch (e: any) {
			error = e.message;
		} finally {
			loading = false;
		}
	}

	// Helper to get metric value
	function getMetricValue(name: string, labels: Record<string, string> = {}): number {
		if (!metrics || !metrics[name]) return 0;

		const samples = metrics[name].samples;
		if (labels && Object.keys(labels).length > 0) {
			// Find sample matching labels
			const sample = samples.find((s: any) =>
				Object.entries(labels).every(([k, v]) => s.labels[k] === v)
			);
			return sample?.value || 0;
		}

		// Sum all samples
		return samples.reduce((sum: number, s: any) => sum + (s.value || 0), 0);
	}

	// Helper to get all label values
	function getMetricsByLabel(name: string, labelKey: string): Array<{ label: string; value: number }> {
		if (!metrics || !metrics[name]) return [];

		const grouped: Record<string, number> = {};
		for (const sample of metrics[name].samples) {
			const labelValue = sample.labels[labelKey] || 'unknown';
			grouped[labelValue] = (grouped[labelValue] || 0) + sample.value;
		}

		return Object.entries(grouped)
			.map(([label, value]) => ({ label, value }))
			.sort((a, b) => b.value - a.value);
	}

	// Derived metrics (Note: Prometheus strips _total suffix from counter names)
	$: totalRequests = metrics ? getMetricValue('engagic_api_requests') : 0;
	$: totalSearches = metrics ? getMetricValue('engagic_page_views', { page_type: 'search' }) : 0;
	$: totalCityViews = metrics ? getMetricValue('engagic_page_views', { page_type: 'city' }) : 0;
	$: totalMatterViews = metrics ? getMetricValue('engagic_page_views', { page_type: 'matter' }) : 0;
	$: totalMeetingViews = metrics ? getMetricValue('engagic_page_views', { page_type: 'meeting' }) : 0;

	$: searchByType = metrics ? getMetricsByLabel('engagic_search_queries', 'query_type') : [];
	$: requestsByEndpoint = metrics ? getMetricsByLabel('engagic_api_requests', 'endpoint') : [];

	$: queuePending = metrics ? getMetricValue('engagic_queue_size', { status: 'pending' }) : 0;
	$: queueProcessing = metrics ? getMetricValue('engagic_queue_size', { status: 'processing' }) : 0;
	$: queueCompleted = metrics ? getMetricValue('engagic_queue_size', { status: 'completed' }) : 0;
	$: queueFailed = metrics ? getMetricValue('engagic_queue_size', { status: 'failed' }) : 0;

	$: llmCalls = metrics ? getMetricValue('engagic_llm_api_calls') : 0;
	$: llmCost = metrics ? getMetricValue('engagic_llm_api_cost_dollars') : 0;
</script>

<svelte:head>
	<title>Admin Dashboard - Engagic</title>
</svelte:head>

<div class="admin-container">
	{#if !isAuthenticated}
		<!-- Auth Form -->
		<div class="auth-form">
			<h1>Admin Dashboard</h1>
			<p>Enter admin token to access metrics</p>

			<input
				type="password"
				bind:value={adminToken}
				placeholder="Admin token"
				on:keydown={(e) => e.key === 'Enter' && authenticate()}
			/>

			<button on:click={authenticate}>Authenticate</button>

			{#if authError}
				<div class="error">{authError}</div>
			{/if}
		</div>
	{:else}
		<!-- Dashboard -->
		<div class="dashboard">
			<div class="dashboard-header">
				<div>
					<h1>Admin Dashboard</h1>
					<p class="last-update">Last update: {lastUpdate}</p>
				</div>
				<div class="header-actions">
					<button on:click={loadMetrics} disabled={loading}>
						{loading ? 'Loading...' : 'Refresh'}
					</button>
					<button on:click={logout} class="logout-btn">Logout</button>
				</div>
			</div>

			{#if error}
				<div class="error">{error}</div>
			{/if}

			{#if metrics}
				<!-- User Behavior -->
				<section class="metrics-section">
					<h2>User Behavior</h2>
					<div class="metrics-grid">
						<div class="metric-card">
							<div class="metric-value">{totalSearches.toLocaleString()}</div>
							<div class="metric-label">Total Searches</div>
						</div>
						<div class="metric-card">
							<div class="metric-value">{totalCityViews.toLocaleString()}</div>
							<div class="metric-label">City Page Views</div>
						</div>
						<div class="metric-card">
							<div class="metric-value">{totalMatterViews.toLocaleString()}</div>
							<div class="metric-label">Matter Page Views</div>
						</div>
						<div class="metric-card">
							<div class="metric-value">{totalMeetingViews.toLocaleString()}</div>
							<div class="metric-label">Meeting Page Views</div>
						</div>
					</div>

					<div class="breakdown">
						<h3>Search Type Breakdown</h3>
						<div class="breakdown-list">
							{#each searchByType as item}
								<div class="breakdown-item">
									<span class="breakdown-label">{item.label}</span>
									<span class="breakdown-value">{item.value.toLocaleString()}</span>
								</div>
							{/each}
						</div>
					</div>
				</section>

				<!-- API Performance -->
				<section class="metrics-section">
					<h2>API Performance</h2>
					<div class="metrics-grid">
						<div class="metric-card">
							<div class="metric-value">{totalRequests.toLocaleString()}</div>
							<div class="metric-label">Total Requests</div>
						</div>
					</div>

					<div class="breakdown">
						<h3>Top Endpoints</h3>
						<div class="breakdown-list">
							{#each requestsByEndpoint.slice(0, 10) as item}
								<div class="breakdown-item">
									<span class="breakdown-label mono">{item.label}</span>
									<span class="breakdown-value">{item.value.toLocaleString()}</span>
								</div>
							{/each}
						</div>
					</div>
				</section>

				<!-- Processing Queue -->
				<section class="metrics-section">
					<h2>Processing Queue</h2>
					<div class="metrics-grid">
						<div class="metric-card">
							<div class="metric-value">{queuePending.toLocaleString()}</div>
							<div class="metric-label">Pending</div>
						</div>
						<div class="metric-card">
							<div class="metric-value">{queueProcessing.toLocaleString()}</div>
							<div class="metric-label">Processing</div>
						</div>
						<div class="metric-card success">
							<div class="metric-value">{queueCompleted.toLocaleString()}</div>
							<div class="metric-label">Completed</div>
						</div>
						<div class="metric-card error">
							<div class="metric-value">{queueFailed.toLocaleString()}</div>
							<div class="metric-label">Failed</div>
						</div>
					</div>
				</section>

				<!-- LLM Usage -->
				<section class="metrics-section">
					<h2>LLM Usage</h2>
					<div class="metrics-grid">
						<div class="metric-card">
							<div class="metric-value">{llmCalls.toLocaleString()}</div>
							<div class="metric-label">Total API Calls</div>
						</div>
						<div class="metric-card">
							<div class="metric-value">${llmCost.toFixed(2)}</div>
							<div class="metric-label">Total Cost</div>
						</div>
					</div>
				</section>
			{/if}
		</div>
	{/if}
</div>

<style>
	.admin-container {
		min-height: 100vh;
		background: #fafafa;
		padding: 2rem;
	}

	.auth-form {
		max-width: 400px;
		margin: 100px auto;
		background: white;
		padding: 2rem;
		border-radius: 8px;
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
	}

	.auth-form h1 {
		margin: 0 0 0.5rem 0;
		font-size: 1.5rem;
	}

	.auth-form p {
		margin: 0 0 1.5rem 0;
		color: #666;
		font-size: 0.9rem;
	}

	.auth-form input {
		width: 100%;
		padding: 0.75rem;
		border: 1px solid #ddd;
		border-radius: 4px;
		font-size: 1rem;
		margin-bottom: 1rem;
		box-sizing: border-box;
	}

	.auth-form button {
		width: 100%;
		padding: 0.75rem;
		background: #2563eb;
		color: white;
		border: none;
		border-radius: 4px;
		font-size: 1rem;
		cursor: pointer;
	}

	.auth-form button:hover {
		background: #1d4ed8;
	}

	.dashboard {
		max-width: 1400px;
		margin: 0 auto;
	}

	.dashboard-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 2rem;
	}

	.dashboard-header h1 {
		margin: 0 0 0.5rem 0;
		font-size: 2rem;
	}

	.last-update {
		margin: 0;
		color: #666;
		font-size: 0.9rem;
	}

	.header-actions {
		display: flex;
		gap: 0.5rem;
	}

	.header-actions button {
		padding: 0.5rem 1rem;
		background: white;
		border: 1px solid #ddd;
		border-radius: 4px;
		cursor: pointer;
		font-size: 0.9rem;
	}

	.header-actions button:hover {
		background: #f5f5f5;
	}

	.header-actions button:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.logout-btn {
		color: #dc2626 !important;
	}

	.metrics-section {
		background: white;
		padding: 1.5rem;
		border-radius: 8px;
		margin-bottom: 1.5rem;
		box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
	}

	.metrics-section h2 {
		margin: 0 0 1rem 0;
		font-size: 1.25rem;
		color: #111;
	}

	.metrics-section h3 {
		margin: 1.5rem 0 0.75rem 0;
		font-size: 1rem;
		color: #666;
	}

	.metrics-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
		gap: 1rem;
	}

	.metric-card {
		background: #f9fafb;
		padding: 1.5rem;
		border-radius: 6px;
		border-left: 4px solid #2563eb;
	}

	.metric-card.success {
		border-left-color: #16a34a;
	}

	.metric-card.error {
		border-left-color: #dc2626;
	}

	.metric-value {
		font-size: 2rem;
		font-weight: 600;
		margin-bottom: 0.25rem;
		color: #111;
	}

	.metric-label {
		font-size: 0.875rem;
		color: #666;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.breakdown-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.breakdown-item {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 0.75rem;
		background: #f9fafb;
		border-radius: 4px;
	}

	.breakdown-label {
		color: #374151;
		font-size: 0.9rem;
	}

	.breakdown-label.mono {
		font-family: 'SF Mono', 'Monaco', 'Inconsolata', monospace;
		font-size: 0.85rem;
	}

	.breakdown-value {
		font-weight: 600;
		color: #111;
	}

	.error {
		background: #fee2e2;
		color: #991b1b;
		padding: 1rem;
		border-radius: 4px;
		margin-top: 1rem;
	}
</style>
