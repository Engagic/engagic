<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { authState } from '$lib/stores/auth.svelte';
	import { getDashboard } from '$lib/api/dashboard';

	let loading = $state(true);
	let error = $state('');

	onMount(async () => {
		const token = $page.url.searchParams.get('token');

		if (!token) {
			error = 'No verification token provided';
			loading = false;
			return;
		}

		try {
			await authState.verifyAndLogin(token);

			// Fetch subscribed cities from dashboard
			if (authState.accessToken) {
				try {
					const dashboard = await getDashboard(authState.accessToken);
					const cities: string[] = [];
					for (const digest of dashboard.digests) {
						cities.push(...digest.cities);
					}
					authState.setSubscribedCities(cities);
				} catch {
					// Non-fatal: continue without subscribed cities
				}
			}

			// Redirect to dashboard on success
			await goto('/dashboard');
		} catch (err) {
			error = err instanceof Error ? err.message : 'Verification failed';
			loading = false;
		}
	});
</script>

<svelte:head>
	<title>Verifying... - Engagic</title>
</svelte:head>

<div class="page">
	<div class="container">
		<div class="card">
			{#if loading}
				<div class="loading-state">
					<div class="spinner" aria-hidden="true"></div>
					<h1>Verifying your account...</h1>
					<p>Please wait while we log you in</p>
				</div>
			{:else if error}
				<div class="error-state">
					<div class="icon-error" aria-hidden="true">✗</div>
					<h1>Verification Failed</h1>
					<p class="error-message">{error}</p>
					<div class="actions">
						<a href="/login" class="btn-primary">Try Again</a>
						<a href="/signup" class="btn-secondary">Sign Up</a>
					</div>
				</div>
			{/if}
		</div>
	</div>
</div>

<style>
	.page {
		min-height: 100vh;
		background: linear-gradient(135deg, var(--bg-gradient-start) 0%, var(--bg-gradient-end) 100%);
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 2rem;
	}

	.container {
		width: 100%;
		max-width: 480px;
	}

	.card {
		background: var(--civic-white);
		border: 1px solid var(--civic-border);
		border-radius: 12px;
		padding: 2.5rem;
		box-shadow: 0 8px 16px rgba(0, 0, 0, 0.15);
		text-align: center;
	}

	.loading-state,
	.error-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 1.5rem;
	}

	.spinner {
		width: 48px;
		height: 48px;
		border: 4px solid var(--civic-border);
		border-top-color: var(--civic-blue);
		border-radius: 50%;
		animation: spin 1s linear infinite;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	.icon-error {
		width: 64px;
		height: 64px;
		background: #fee2e2;
		border: 1px solid #ef4444;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 2rem;
		color: #ef4444;
		font-weight: bold;
	}

	h1 {
		font-size: 1.875rem;
		font-weight: bold;
		margin: 0;
		color: var(--civic-dark);
		letter-spacing: -0.02em;
	}

	p {
		font-size: 1rem;
		color: var(--civic-gray);
		margin: 0;
		line-height: 1.5;
	}

	.error-message {
		color: #ef4444;
		font-weight: 500;
	}

	.actions {
		display: flex;
		gap: 1rem;
		margin-top: 1rem;
	}

	.btn-primary,
	.btn-secondary {
		padding: 0.75rem 1.5rem;
		font-size: 0.875rem;
		font-weight: 600;
		border-radius: 8px;
		cursor: pointer;
		transition: all 0.2s;
		font-family: system-ui, -apple-system, sans-serif;
		text-decoration: none;
		display: inline-block;
	}

	.btn-primary {
		background: var(--civic-blue);
		color: white;
		border: none;
	}

	.btn-primary:hover {
		background: var(--civic-accent);
		transform: translateY(-2px);
		box-shadow: 0 4px 12px rgba(139, 92, 246, 0.3);
	}

	.btn-secondary {
		background: transparent;
		color: var(--civic-blue);
		border: 1px solid var(--civic-blue);
	}

	.btn-secondary:hover {
		background: rgba(79, 70, 229, 0.1);
	}

	@media (max-width: 640px) {
		.page {
			padding: 1rem;
		}

		.card {
			padding: 1.5rem;
		}

		h1 {
			font-size: 1.5rem;
		}

		.actions {
			flex-direction: column;
			width: 100%;
		}

		.btn-primary,
		.btn-secondary {
			width: 100%;
			text-align: center;
		}
	}
</style>
