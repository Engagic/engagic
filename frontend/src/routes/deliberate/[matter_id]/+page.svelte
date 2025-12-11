<script lang="ts">
	import { authState } from '$lib/stores/auth.svelte';
	import { createDeliberation } from '$lib/api/deliberation';
	import DeliberationPanel from '$lib/components/deliberation/DeliberationPanel.svelte';
	import Footer from '$lib/components/Footer.svelte';
	import { logger } from '$lib/services/logger';
	import { onMount } from 'svelte';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	onMount(() => {
		logger.trackEvent('deliberate_view', { matter_id: data.matterId });
	});

	const matter = $derived(data.matter);
	let deliberation = $state(data.deliberation.deliberation);
	let creating = $state(false);
	let createError = $state<string | null>(null);

	async function startDiscussion() {
		if (!authState.isAuthenticated || !authState.accessToken) {
			createError = 'Sign in to start a discussion';
			return;
		}

		creating = true;
		createError = null;

		try {
			const result = await createDeliberation(
				data.matterId,
				matter.title,
				authState.accessToken
			);
			deliberation = result.deliberation;
		} catch (err) {
			console.error('Failed to create deliberation:', err);
			createError = 'Failed to start discussion. Please try again.';
		} finally {
			creating = false;
		}
	}
</script>

<svelte:head>
	<title>Discuss: {matter.title} | Engagic</title>
	<meta name="description" content="Join the community discussion about {matter.matter_file}" />
</svelte:head>

<div class="deliberate-page">
	<header class="page-header">
		<a href="/matter/{data.matterId}" class="back-link">
			View Legislative Details
		</a>
		<h1 class="matter-title">{matter.title}</h1>
		{#if matter.matter_file}
			<span class="matter-file">{matter.matter_file}</span>
		{/if}
	</header>

	<main class="deliberation-container">
		{#if deliberation}
			<DeliberationPanel
				deliberationId={deliberation.id}
				matterId={data.matterId}
				topic={deliberation.topic ?? matter.title}
			/>
		{:else}
			<div class="no-deliberation">
				<div class="empty-state">
					<h2>No discussion yet</h2>
					<p>Be the first to start a community discussion about this matter.</p>

					{#if authState.isAuthenticated}
						<button
							class="start-btn"
							onclick={startDiscussion}
							disabled={creating}
						>
							{creating ? 'Starting...' : 'Start Discussion'}
						</button>
					{:else}
						<p class="auth-prompt">
							<a href="/login?redirect=/deliberate/{data.matterId}">Sign in</a> to start a discussion
						</p>
					{/if}

					{#if createError}
						<p class="error-message">{createError}</p>
					{/if}
				</div>
			</div>
		{/if}
	</main>

	<Footer />
</div>

<style>
	.deliberate-page {
		min-height: 100vh;
		display: flex;
		flex-direction: column;
		background: var(--surface-secondary);
	}

	.page-header {
		background: var(--surface-primary);
		border-bottom: 1px solid var(--border-primary);
		padding: 1.5rem 2rem;
	}

	.back-link {
		display: inline-block;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8rem;
		font-weight: 600;
		color: var(--civic-blue);
		text-decoration: none;
		margin-bottom: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.5px;
	}

	.back-link:hover {
		text-decoration: underline;
	}

	.matter-title {
		font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
		font-size: 1.5rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0 0 0.5rem 0;
		line-height: 1.3;
	}

	.matter-file {
		display: inline-block;
		padding: 0.25rem 0.75rem;
		background: linear-gradient(135deg, var(--badge-matter-bg-start) 0%, var(--badge-matter-bg-end) 100%);
		color: var(--badge-matter-text);
		border: 1.5px solid var(--badge-matter-border);
		border-radius: 12px;
		font-size: 0.75rem;
		font-weight: 700;
		font-family: 'IBM Plex Mono', monospace;
		letter-spacing: 0.5px;
	}

	.deliberation-container {
		flex: 1;
		max-width: 800px;
		margin: 0 auto;
		padding: 2rem;
		width: 100%;
	}

	.no-deliberation {
		background: var(--surface-primary);
		border: 1px solid var(--border-primary);
		border-radius: 12px;
		padding: 3rem 2rem;
	}

	.empty-state {
		text-align: center;
	}

	.empty-state h2 {
		font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
		font-size: 1.25rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0 0 0.5rem 0;
	}

	.empty-state p {
		font-family: Georgia, 'Times New Roman', serif;
		font-size: 1rem;
		color: var(--text-secondary);
		margin: 0 0 1.5rem 0;
	}

	.start-btn {
		padding: 0.875rem 2rem;
		background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%);
		color: white;
		border: none;
		border-radius: 8px;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
		font-weight: 700;
		cursor: pointer;
		transition: all 0.2s ease;
		text-transform: uppercase;
		letter-spacing: 0.5px;
		box-shadow: 0 2px 8px rgba(139, 92, 246, 0.3);
	}

	.start-btn:hover:not(:disabled) {
		background: linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%);
		box-shadow: 0 4px 12px rgba(139, 92, 246, 0.4);
		transform: translateY(-1px);
	}

	.start-btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.auth-prompt {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
	}

	.auth-prompt a {
		color: var(--civic-blue);
		font-weight: 600;
	}

	.error-message {
		color: var(--civic-red);
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
		margin-top: 1rem;
	}

	@media (max-width: 640px) {
		.page-header {
			padding: 1rem 1.25rem;
		}

		.matter-title {
			font-size: 1.25rem;
		}

		.deliberation-container {
			padding: 1rem;
		}

		.no-deliberation {
			padding: 2rem 1.25rem;
		}
	}
</style>
