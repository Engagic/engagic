<script lang="ts">
	import { getAnalytics, type AnalyticsData } from '$lib/api/index';
	import { onMount } from 'svelte';
	import Footer from '$lib/components/Footer.svelte';

	let analytics: AnalyticsData | null = $state(null);
	let loading = $state(true);
	let errorMessage = $state('');

	onMount(async () => {
		try {
			analytics = await getAnalytics();
			console.log('Analytics loaded:', analytics);
		} catch (err) {
			console.error('Failed to load analytics:', err);
			errorMessage = err instanceof Error ? err.message : 'Failed to load analytics';
		} finally {
			loading = false;
		}
	});

	function formatNumber(num: number): string {
		if (num >= 1000000) {
			return (num / 1000000).toFixed(1) + 'M';
		} else if (num >= 1000) {
			return (num / 1000).toFixed(1) + 'K';
		}
		return num.toLocaleString();
	}

	// Snapshot: Preserve scroll position during navigation
	export const snapshot = {
		capture: () => ({
			scrollY: typeof window !== 'undefined' ? window.scrollY : 0
		}),
		restore: (values: { scrollY: number }) => {
			if (typeof window !== 'undefined' && typeof values.scrollY === 'number') {
				setTimeout(() => window.scrollTo(0, values.scrollY), 0);
			}
		}
	};
</script>

<svelte:head>
	<title>About Engagic - Making Democracy Accessible</title>
	<meta name="description" content="Learn about Engagic's mission to make local government meetings accessible through AI-powered summaries" />
</svelte:head>

<div class="about-container">
	<header class="header">
		<a href="/" class="logo">engagic</a>
		<p class="tagline">civic engagement made simple</p>
	</header>

	<div class="about-header">
		<h1>About Engagic</h1>
		<p class="subtitle">Making Democracy Accessible</p>
		<a href="/" class="back-link">← Back to Search</a>
	</div>

	<section class="mission-section">
		<h2>What We Do</h2>
		<div class="mission-content">
			<p>We automatically find and summarize your local government meetings using AI.</p>
			<p>No more digging through 50-page PDFs to see what your city council is up to. Just search your zip code or city and get the important stuff in plain English.</p>
			<p>Democracy works better when everyone can participate. But government meetings are often hard to find, harder to understand, and buried in bureaucratic language. We're changing that.</p>
		</div>
	</section>

	{#if !loading && analytics}
		<section class="impact-section">
			<h2>Our Impact</h2>
			<div class="impact-grid">
				<div class="impact-card">
					<div class="impact-number">{formatNumber(analytics.real_metrics.cities_covered)}</div>
					<div class="impact-label">Cities Covered</div>
					<div class="impact-desc">Local governments across America</div>
				</div>

				<div class="impact-card">
					<div class="impact-number">{formatNumber(analytics.real_metrics.meetings_tracked)}</div>
					<div class="impact-label">Meetings Tracked</div>
					<div class="impact-desc">City council sessions monitored</div>
				</div>

				<div class="impact-card">
					<div class="impact-number">{formatNumber(analytics.real_metrics.matters_tracked)}</div>
					<div class="impact-label">Legislative Matters</div>
					<div class="impact-desc">Across {formatNumber(analytics.real_metrics.agenda_items_processed)} agenda items</div>
				</div>

				<div class="impact-card">
					<div class="impact-number">{formatNumber(analytics.real_metrics.unique_item_summaries)}</div>
					<div class="impact-label">Unique Summaries</div>
					<div class="impact-desc">Across {formatNumber(analytics.real_metrics.meetings_with_items)} item-level meetings</div>
				</div>
			</div>
		</section>
	{:else if loading}
		<section class="impact-section">
			<h2>Our Impact</h2>
			<div class="loading-placeholder">Loading impact metrics...</div>
		</section>
	{:else if errorMessage}
		<section class="impact-section">
			<h2>Our Impact</h2>
			<div class="loading-placeholder" style="color: #e74c3c;">{errorMessage}</div>
		</section>
	{/if}

	<section class="how-section">
		<h2>How It Works</h2>
		<div class="how-steps">
			<div class="step">
				<div class="step-number">1</div>
				<div class="step-content">
					<h3>We Monitor</h3>
					<p>Our system continuously checks city websites for new meeting agendas and packets</p>
				</div>
			</div>
			
			<div class="step">
				<div class="step-number">2</div>
				<div class="step-content">
					<h3>AI Processes</h3>
					<p>Advanced AI reads through dense government documents and extracts what matters</p>
				</div>
			</div>
			
			<div class="step">
				<div class="step-number">3</div>
				<div class="step-content">
					<h3>You Get Clarity</h3>
					<p>Clean, readable summaries that highlight budget items, public hearings, and key decisions</p>
				</div>
			</div>
		</div>
	</section>

	<section class="principles-section">
		<h2>Our Principles</h2>
		<div class="principles-grid">
			<div class="principle">
				<h3>Open Source</h3>
				<p>All our code is publicly available and auditable. Democracy should be transparent.</p>
			</div>
			
			<div class="principle">
				<h3>No Agenda</h3>
				<p>We don't editorialize or take political positions. We just make information accessible.</p>
			</div>
			
			<div class="principle">
				<h3>Privacy First</h3>
				<p>We don't track users or collect personal data. Civic engagement shouldn't require surveillance.</p>
			</div>
		</div>
	</section>

	<Footer />
</div>

<style>
	.about-container {
		max-width: 1000px;
		margin: 0 auto;
		padding: 4rem 1rem;
		color: var(--civic-dark);
		-webkit-font-smoothing: antialiased;
		-moz-osx-font-smoothing: grayscale;
	}

	.header {
		text-align: center;
		margin-bottom: 2rem;
	}

	.about-header {
		text-align: center;
		margin-bottom: 4rem;
		position: relative;
	}

	.about-header h1 {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 3rem;
		font-weight: 600;
		color: var(--civic-blue);
		margin-bottom: 0.5rem;
	}

	.subtitle {
		font-family: Georgia, 'Times New Roman', Times, serif;
		font-size: 1.25rem;
		color: var(--civic-gray);
		margin-bottom: 2rem;
	}

	.back-link {
		position: absolute;
		top: 0;
		left: 0;
		color: var(--civic-blue);
		text-decoration: none;
		font-weight: 500;
	}

	.back-link:hover {
		text-decoration: underline;
	}

	section {
		margin-bottom: 4rem;
	}

	h2 {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 2rem;
		font-weight: 600;
		color: var(--civic-dark);
		margin-bottom: 2rem;
		text-align: center;
	}

	.mission-content {
		margin: 0 auto;
		text-align: center;
	}

	.mission-content p {
		font-family: Georgia, 'Times New Roman', Times, serif;
		font-size: 1.1rem;
		line-height: 1.8;
		color: var(--civic-gray);
		margin-bottom: 1.5rem;
	}

	.impact-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
		gap: 2rem;
		margin-top: 2rem;
	}

	.impact-card {
		text-align: center;
		padding: 2rem 1rem;
		background: var(--civic-white);
		border-radius: 12px;
		border: 1px solid var(--civic-border);
		box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
	}

	.impact-number {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 3rem;
		font-weight: 600;
		color: var(--civic-blue);
		margin-bottom: 0.5rem;
	}

	.impact-label {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.1rem;
		font-weight: 600;
		color: var(--civic-dark);
		margin-bottom: 0.5rem;
	}

	.impact-desc {
		font-family: Georgia, 'Times New Roman', Times, serif;
		font-size: 0.9rem;
		color: var(--civic-gray);
		line-height: 1.5;
	}

	.loading-placeholder {
		text-align: center;
		color: var(--civic-gray);
		font-style: italic;
		padding: 2rem;
	}

	.how-steps {
		margin: 0 auto;
	}

	.step {
		display: flex;
		gap: 2rem;
		margin-bottom: 3rem;
		align-items: flex-start;
	}

	.step-number {
		width: 60px;
		height: 60px;
		background: var(--civic-blue);
		color: white;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 1.5rem;
		font-weight: 500;
		flex-shrink: 0;
	}

	.step-content h3 {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.3rem;
		font-weight: 600;
		color: var(--civic-dark);
		margin-bottom: 0.5rem;
	}

	.step-content p {
		font-family: Georgia, 'Times New Roman', Times, serif;
		color: var(--civic-gray);
		line-height: 1.7;
	}

	.principles-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
		gap: 2rem;
		margin-top: 2rem;
	}

	.principle {
		text-align: center;
		padding: 2rem;
	}

	.principle h3 {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.3rem;
		font-weight: 600;
		color: var(--civic-blue);
		margin-bottom: 1rem;
	}

	.principle p {
		font-family: Georgia, 'Times New Roman', Times, serif;
		color: var(--civic-gray);
		line-height: 1.7;
	}


	@media (max-width: 640px) {
		.about-container {
			padding: 1rem 0.5rem;
		}

		.about-header h1 {
			font-size: 2rem;
		}

		.back-link {
			position: static;
			display: block;
			margin-bottom: 1rem;
		}

		.impact-grid {
			grid-template-columns: repeat(2, 1fr);
			gap: 1rem;
		}

		.impact-card {
			padding: 1.5rem 0.5rem;
		}

		.impact-number {
			font-size: 2rem;
		}

		.step {
			flex-direction: column;
			text-align: center;
			gap: 1rem;
		}

		.step-number {
			margin: 0 auto;
		}
	}
</style>