<script lang="ts">
	import { page } from '$app/stores';
	import { marked } from 'marked';
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

	function parseAttachments(attachmentsJson: string | null): Array<{ name: string; url: string; type: string }> {
		if (!attachmentsJson) return [];
		try {
			return JSON.parse(attachmentsJson);
		} catch {
			return [];
		}
	}

	const topics = $derived(parseTopics(matter.canonical_topics));
	const attachments = $derived(parseAttachments(matter.attachments));
</script>

<svelte:head>
	<title>{matter.matter_file ? `${matter.matter_file} - ` : ''}{matter.title} - engagic</title>
	<meta name="description" content="Track legislative matter across meetings: {matter.title}" />
</svelte:head>

<div class="matter-page">
	<div class="matter-container">
		<div class="breadcrumb">
			<a href="/" class="breadcrumb-link" data-sveltekit-preload-data="hover">← Back to Search</a>
			{#if firstAppearance}
				<span class="breadcrumb-separator">•</span>
				<a href="/{firstAppearance.banana}" class="breadcrumb-link" data-sveltekit-preload-data="hover">{firstAppearance.city_name}</a>
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
					{@html marked(matter.canonical_summary)}
				</div>
			</div>
		{/if}

		{#if attachments.length > 0}
			<div class="attachments-section">
				<h2 class="section-title">Attachments</h2>
				<div class="attachments-list">
					{#each attachments as attachment}
						<a href={attachment.url} target="_blank" rel="noopener noreferrer" class="attachment-link">
							<span class="attachment-icon">📎</span>
							<span class="attachment-name">{attachment.name}</span>
						</a>
					{/each}
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
			<svelte:boundary onerror={(e) => console.error('Timeline error:', e)}>
				<MatterTimeline timelineData={data.timeline} matterFile={matter.matter_file} />
				{#snippet failed(error)}
					<div class="error-message">
						<p>Unable to load legislative timeline</p>
						<p class="error-detail">{error.message}</p>
					</div>
				{/snippet}
			</svelte:boundary>
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
		font-size: 1.25rem;
		font-weight: 700;
		color: var(--text-primary);
		line-height: 1.4;
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
	.attachments-section,
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
		font-size: 1.05rem;
		line-height: 1.8;
		color: var(--text-primary);
		-webkit-font-smoothing: antialiased;
		-moz-osx-font-smoothing: grayscale;
	}

	.matter-summary :global(h1),
	.matter-summary :global(h2),
	.matter-summary :global(h3),
	.matter-summary :global(h4) {
		font-family: Georgia, 'Times New Roman', Times, serif;
		color: var(--text-primary);
		margin-top: 2.5rem;
		margin-bottom: 1rem;
		line-height: 1.3;
		font-weight: 600;
	}

	.matter-summary :global(h1) { font-size: 1.75rem; }
	.matter-summary :global(h2) { font-size: 1.5rem; }
	.matter-summary :global(h3) { font-size: 1.25rem; }
	.matter-summary :global(h4) { font-size: 1.1rem; }

	.matter-summary :global(h1:first-child),
	.matter-summary :global(h2:first-child),
	.matter-summary :global(h3:first-child),
	.matter-summary :global(h4:first-child) {
		margin-top: 0;
	}

	.matter-summary :global(p) {
		margin: 1.5rem 0;
	}

	.matter-summary :global(ul),
	.matter-summary :global(ol) {
		margin: 1.5rem 0;
		padding-left: 2rem;
	}

	.matter-summary :global(li) {
		margin: 0.5rem 0;
	}

	.matter-summary :global(blockquote) {
		margin: 2rem 0;
		padding-left: 1.5rem;
		border-left: 4px solid var(--text-secondary);
		color: var(--text-secondary);
		font-style: italic;
	}

	.matter-summary :global(code) {
		font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
		font-size: 0.9em;
		background: var(--surface-secondary);
		color: var(--text-primary);
		padding: 0.2rem 0.4rem;
		border-radius: 3px;
	}

	.matter-summary :global(pre) {
		margin: 2rem 0;
		padding: 1.5rem;
		background: var(--surface-secondary);
		border-radius: 8px;
		overflow-x: auto;
	}

	.matter-summary :global(pre code) {
		background: none;
		padding: 0;
	}

	.matter-summary :global(strong) {
		font-weight: 700;
		color: var(--text-primary);
	}

	.matter-summary :global(em) {
		font-style: italic;
	}

	.matter-summary :global(hr) {
		margin: 2.5rem 0;
		border: none;
		border-top: 1px solid var(--border-primary);
	}

	.matter-summary :global(a) {
		color: var(--text-link);
		text-decoration: underline;
		transition: color 0.2s ease;
	}

	.matter-summary :global(a:hover) {
		color: var(--civic-accent);
	}

	.matter-summary :global(img) {
		max-width: 100%;
		height: auto;
		border-radius: 8px;
		margin: 2rem 0;
	}

	.attachments-list {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.attachment-link {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.75rem 1rem;
		background: var(--surface-secondary);
		border: 1px solid var(--border-primary);
		border-radius: 8px;
		text-decoration: none;
		color: var(--text-primary);
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.85rem;
		transition: all 0.2s ease;
	}

	.attachment-link:hover {
		background: var(--civic-blue);
		border-color: var(--civic-blue);
		color: var(--civic-white);
		transform: translateX(4px);
	}

	.attachment-icon {
		font-size: 1.1rem;
		flex-shrink: 0;
	}

	.attachment-name {
		flex: 1;
		font-weight: 500;
	}

	.sponsors-list {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
		color: var(--text-primary);
		line-height: 1.6;
	}

	.error-message {
		padding: 1.5rem;
		background: var(--surface-secondary);
		border: 2px solid #ef4444;
		border-radius: 8px;
		text-align: center;
	}

	.error-message p {
		margin: 0.5rem 0;
		color: var(--text-primary);
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
	}

	.error-detail {
		color: #ef4444;
		font-size: 0.85rem;
	}

	@media (max-width: 768px) {
		.matter-page {
			padding: 1rem 0.5rem;
		}

		.matter-header {
			padding: 1.5rem;
		}

		.matter-title {
			font-size: 1.1rem;
		}

		.matter-meta {
			flex-direction: column;
			gap: 0.75rem;
		}

		.matter-summary-section,
		.attachments-section,
		.sponsors-section,
		.timeline-section {
			padding: 1.25rem;
		}
	}
</style>
