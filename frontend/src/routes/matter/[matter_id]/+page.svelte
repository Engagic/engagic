<script lang="ts">
	import { page } from '$app/stores';
	import MatterTimeline from '$lib/components/MatterTimeline.svelte';
	import Footer from '$lib/components/Footer.svelte';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	const matter = $derived(data.timeline.matter);
	const timeline = $derived(data.timeline.timeline);
	const firstAppearance = $derived(timeline[0]);
	const latestAppearance = $derived(timeline[timeline.length - 1]);

	function formatDate(dateStr: string): string {
		if (!dateStr) return '';
		const date = new Date(dateStr);
		return date.toLocaleDateString('en-US', {
			month: 'long',
			day: 'numeric',
			year: 'numeric'
		});
	}

	function parseTopics(topicsJson: string | null): string[] {
		if (!topicsJson) return [];
		try {
			return JSON.parse(topicsJson);
		} catch {
			return [];
		}
	}

	const topics = $derived(parseTopics(matter.canonical_topics));
</script>

<svelte:head>
	<title>{matter.matter_file ? `${matter.matter_file} - ` : ''}{matter.title} - engagic</title>
	<meta name="description" content="Track legislative matter across meetings: {matter.title}" />
</svelte:head>

<div class="matter-page">
	<div class="matter-container">
		<div class="breadcrumb">
			<a href="/" class="breadcrumb-link">← Back to Search</a>
			{#if firstAppearance}
				<span class="breadcrumb-separator">•</span>
				<a href="/{firstAppearance.banana}" class="breadcrumb-link">{firstAppearance.city_name}</a>
			{/if}
		</div>

		<div class="matter-header">
			<div class="header-badges">
				{#if matter.matter_file}
					<div class="matter-badge primary">{matter.matter_file}</div>
				{/if}
				{#if matter.matter_type}
					<div class="matter-badge type">{matter.matter_type}</div>
				{/if}
				<div class="matter-badge count">
					{data.timeline.appearance_count} appearance{data.timeline.appearance_count === 1 ? '' : 's'}
				</div>
			</div>

			<h1 class="matter-title">{matter.title}</h1>

			<div class="matter-meta">
				{#if firstAppearance}
					<div class="meta-item">
						<span class="meta-label">City:</span>
						<span class="meta-value">{firstAppearance.city_name}, {firstAppearance.state}</span>
					</div>
				{/if}
				<div class="meta-item">
					<span class="meta-label">First Seen:</span>
					<span class="meta-value">{formatDate(matter.first_seen)}</span>
				</div>
				<div class="meta-item">
					<span class="meta-label">Latest Activity:</span>
					<span class="meta-value">{formatDate(matter.last_seen)}</span>
				</div>
			</div>

			{#if topics.length > 0}
				<div class="matter-topics">
					{#each topics as topic}
						<span class="topic-tag">{topic}</span>
					{/each}
				</div>
			{/if}
		</div>

		{#if matter.canonical_summary}
			<div class="matter-summary-section">
				<h2 class="section-title">Summary</h2>
				<div class="matter-summary">
					{@html matter.canonical_summary}
				</div>
			</div>
		{/if}

		{#if matter.sponsors}
			<div class="sponsors-section">
				<h2 class="section-title">Sponsors</h2>
				<div class="sponsors-list">{matter.sponsors}</div>
			</div>
		{/if}

		<div class="timeline-section">
			<h2 class="section-title">Legislative Journey</h2>
			<MatterTimeline matterId={data.matterId} matterFile={matter.matter_file} />
		</div>
	</div>

	<Footer />
</div>

<style>
	.matter-page {
		width: 100%;
		min-height: 100vh;
		display: flex;
		flex-direction: column;
		padding: 2rem 1rem;
	}

	.matter-container {
		width: 100%;
		max-width: 1000px;
		margin: 0 auto;
	}

	.breadcrumb {
		margin-bottom: 1.5rem;
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.breadcrumb-link {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
		color: var(--text-link);
		text-decoration: none;
		transition: color 0.2s ease;
		font-weight: 500;
	}

	.breadcrumb-link:hover {
		color: var(--civic-accent);
		text-decoration: underline;
	}

	.breadcrumb-separator {
		color: var(--civic-gray);
	}

	.matter-header {
		background: var(--surface-primary);
		border: 2px solid var(--border-primary);
		border-radius: 16px;
		padding: 2rem;
		margin-bottom: 2rem;
		box-shadow: 0 2px 8px var(--shadow-sm);
	}

	.header-badges {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
		margin-bottom: 1.5rem;
	}

	.matter-badge {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8rem;
		font-weight: 700;
		padding: 0.4rem 0.8rem;
		border-radius: 8px;
		border: 1px solid;
	}

	.matter-badge.primary {
		background: var(--badge-blue-bg);
		border-color: var(--badge-blue-border);
		color: var(--badge-blue-text);
	}

	.matter-badge.type {
		background: var(--surface-secondary);
		border-color: var(--border-primary);
		color: var(--text-secondary);
	}

	.matter-badge.count {
		background: var(--badge-green-bg);
		border-color: var(--badge-green-border);
		color: var(--badge-green-text);
	}

	.matter-title {
		font-family: Georgia, 'Times New Roman', Times, serif;
		font-size: 2rem;
		font-weight: 700;
		color: var(--text-primary);
		line-height: 1.3;
		margin: 0 0 1.5rem 0;
	}

	.matter-meta {
		display: flex;
		flex-wrap: wrap;
		gap: 1.5rem;
		margin-bottom: 1rem;
	}

	.meta-item {
		display: flex;
		gap: 0.5rem;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
	}

	.meta-label {
		color: var(--civic-gray);
		font-weight: 600;
	}

	.meta-value {
		color: var(--text-primary);
	}

	.matter-topics {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin-top: 1rem;
	}

	.topic-tag {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		font-weight: 600;
		padding: 0.3rem 0.7rem;
		background: var(--civic-blue);
		color: var(--civic-white);
		border-radius: 6px;
		transition: all 0.2s ease;
	}

	.topic-tag:hover {
		background: var(--civic-accent);
		transform: translateY(-1px);
	}

	.matter-summary-section,
	.sponsors-section,
	.timeline-section {
		background: var(--surface-primary);
		border: 1px solid var(--border-primary);
		border-radius: 12px;
		padding: 1.5rem;
		margin-bottom: 1.5rem;
		box-shadow: 0 1px 3px var(--shadow-sm);
	}

	.section-title {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.5px;
		color: var(--civic-gray);
		margin: 0 0 1rem 0;
	}

	.matter-summary {
		font-family: Georgia, 'Times New Roman', Times, serif;
		font-size: 1rem;
		line-height: 1.7;
		color: var(--text-primary);
	}

	.matter-summary :global(h2) {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
		font-weight: 600;
		text-transform: uppercase;
		color: var(--civic-gray);
		margin: 1.5rem 0 0.75rem 0;
	}

	.matter-summary :global(p) {
		margin: 0.75rem 0;
	}

	.matter-summary :global(strong) {
		font-weight: 700;
		color: var(--text-primary);
	}

	.sponsors-list {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
		color: var(--text-primary);
		line-height: 1.6;
	}

	@media (max-width: 768px) {
		.matter-page {
			padding: 1rem 0.5rem;
		}

		.matter-header {
			padding: 1.5rem;
		}

		.matter-title {
			font-size: 1.5rem;
		}

		.matter-meta {
			flex-direction: column;
			gap: 0.75rem;
		}

		.matter-summary-section,
		.sponsors-section,
		.timeline-section {
			padding: 1.25rem;
		}
	}
</style>
