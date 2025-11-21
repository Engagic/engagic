<script lang="ts">
	import { getAnalytics, type AnalyticsData } from '$lib/api/index';
	import { onMount } from 'svelte';
	import { fade, fly } from 'svelte/transition';
	import Footer from '$lib/components/Footer.svelte';

	let analytics: AnalyticsData | null = $state(null);
	let loading = $state(true);
	let errorMessage = $state('');
	let mounted = $state(false);

	onMount(async () => {
		mounted = true;
		try {
			analytics = await getAnalytics();
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
</script>

<svelte:head>
	<title>About Engagic - Making Democracy Accessible</title>
	<meta name="description" content="Learn about Engagic's mission to make local government meetings accessible through AI-powered summaries" />
</svelte:head>

<div class="page">
	<a href="/" class="home-logo">
		<img src="/icon-64.png" alt="engagic" />
	</a>

	{#if mounted}
		<div class="hero" in:fade={{ duration: 400 }}>
			<h1>About Engagic</h1>
			<p class="tagline">Making democracy accessible, one meeting at a time</p>
		</div>

		<div class="content">
			<section class="mission" in:fly={{ y: 20, duration: 400, delay: 100 }}>
				<h2>What We Do</h2>
				<div class="mission-text">
					<p>We automatically find and summarize your local government meetings using AI.</p>
					<p>No more digging through 50-page PDFs to see what your city council is up to. Just search your zip code or city and get the important stuff in plain English.</p>
					<p>Democracy works better when everyone can participate. But government meetings are often hard to find, harder to understand, and buried in bureaucratic language. We're changing that.</p>
				</div>
			</section>

			{#if !loading && analytics}
				<section class="metrics" in:fly={{ y: 20, duration: 400, delay: 200 }}>
					<h2>Our Impact</h2>
					<div class="metrics-grid">
						<div class="metric-card">
							<div class="metric-value">{formatNumber(analytics.real_metrics.frequently_updated_cities)}</div>
							<div class="metric-label">Active Cities</div>
							<div class="metric-desc">With 7+ summarized meetings</div>
						</div>

						<div class="metric-card">
							<div class="metric-value">{formatNumber(analytics.real_metrics.meetings_tracked)}</div>
							<div class="metric-label">Meetings Tracked</div>
							<div class="metric-desc">City council sessions monitored</div>
						</div>

						<div class="metric-card">
							<div class="metric-value">{formatNumber(analytics.real_metrics.matters_tracked)}</div>
							<div class="metric-label">Legislative Matters</div>
							<div class="metric-desc">{formatNumber(analytics.real_metrics.agenda_items_processed)} agenda items</div>
						</div>

						<div class="metric-card">
							<div class="metric-value">{formatNumber(analytics.real_metrics.unique_item_summaries)}</div>
							<div class="metric-label">AI Summaries</div>
							<div class="metric-desc">Unique item analyses</div>
						</div>
					</div>
				</section>
			{:else if loading}
				<section class="metrics" in:fade>
					<h2>Our Impact</h2>
					<div class="loading">Loading metrics...</div>
				</section>
			{/if}

			<section class="how" in:fly={{ y: 20, duration: 400, delay: 300 }}>
				<h2>How It Works</h2>
				<div class="steps">
					<div class="step">
						<div class="step-icon">1</div>
						<h3>We Monitor</h3>
						<p>Our system continuously checks city websites for new meeting agendas and packets</p>
					</div>

					<div class="step">
						<div class="step-icon">2</div>
						<h3>AI Processes</h3>
						<p>Advanced AI reads through dense government documents and extracts what matters</p>
					</div>

					<div class="step">
						<div class="step-icon">3</div>
						<h3>You Get Clarity</h3>
						<p>Clean, readable summaries that highlight budget items, public hearings, and key decisions</p>
					</div>
				</div>
			</section>

			<section class="principles" in:fly={{ y: 20, duration: 400, delay: 400 }}>
				<h2>Our Principles</h2>
				<div class="principles-grid">
					<div class="principle-card">
						<div class="principle-icon">🔓</div>
						<h3>Open Source</h3>
						<p>All our code is publicly available and auditable. Democracy should be transparent.</p>
					</div>

					<div class="principle-card">
						<div class="principle-icon">⚖️</div>
						<h3>No Agenda</h3>
						<p>We don't editorialize or take political positions. We just make information accessible.</p>
					</div>

					<div class="principle-card">
						<div class="principle-icon">🔒</div>
						<h3>Privacy First</h3>
						<p>We don't track users or collect personal data. Civic engagement shouldn't require surveillance.</p>
					</div>
				</div>
			</section>
		</div>

		<Footer />
	{/if}
</div>

<style>
	.page {
		min-height: 100vh;
		background: linear-gradient(135deg, #f5f7fa 0%, #e9ecef 100%);
	}

	.home-logo {
		position: fixed;
		top: 2rem;
		left: 2rem;
		z-index: 100;
		transition: transform 0.2s ease;
	}

	.home-logo:hover {
		transform: scale(1.05);
	}

	.home-logo img {
		width: 48px;
		height: 48px;
		border-radius: 12px;
		box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
	}

	.hero {
		text-align: center;
		padding: 8rem 2rem 4rem;
	}

	.hero h1 {
		font-family: 'IBM Plex Mono', monospace;
		font-size: clamp(2.5rem, 5vw, 4rem);
		font-weight: 700;
		background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
		-webkit-background-clip: text;
		-webkit-text-fill-color: transparent;
		background-clip: text;
		margin-bottom: 1rem;
	}

	.tagline {
		font-size: clamp(1rem, 2vw, 1.25rem);
		color: #64748b;
		font-weight: 500;
	}

	.content {
		max-width: 1100px;
		margin: 0 auto;
		padding: 0 2rem 4rem;
	}

	section {
		margin-bottom: 6rem;
	}

	h2 {
		font-family: 'IBM Plex Mono', monospace;
		font-size: clamp(1.75rem, 3vw, 2.5rem);
		font-weight: 700;
		color: #1e293b;
		text-align: center;
		margin-bottom: 3rem;
	}

	/* Mission Section */
	.mission-text {
		max-width: 700px;
		margin: 0 auto;
		text-align: center;
	}

	.mission-text p {
		font-size: 1.125rem;
		line-height: 1.8;
		color: #475569;
		margin-bottom: 1.5rem;
	}

	/* Metrics Section */
	.metrics-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
		gap: 1.5rem;
	}

	.metric-card {
		background: white;
		padding: 2rem;
		border-radius: 16px;
		box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
		text-align: center;
		transition: all 0.3s ease;
		border: 1px solid rgba(0, 0, 0, 0.05);
	}

	.metric-card:hover {
		transform: translateY(-4px);
		box-shadow: 0 12px 24px rgba(79, 70, 229, 0.15);
		border-color: rgba(79, 70, 229, 0.2);
	}

	.metric-value {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 3rem;
		font-weight: 700;
		background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
		-webkit-background-clip: text;
		-webkit-text-fill-color: transparent;
		background-clip: text;
		margin-bottom: 0.5rem;
	}

	.metric-label {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.125rem;
		font-weight: 600;
		color: #1e293b;
		margin-bottom: 0.5rem;
	}

	.metric-desc {
		font-size: 0.875rem;
		color: #64748b;
	}

	.loading {
		text-align: center;
		color: #64748b;
		padding: 3rem;
	}

	/* How It Works Section */
	.steps {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
		gap: 2rem;
		max-width: 900px;
		margin: 0 auto;
	}

	.step {
		text-align: center;
		padding: 2rem;
		background: white;
		border-radius: 16px;
		box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
		transition: all 0.3s ease;
	}

	.step:hover {
		transform: translateY(-4px);
		box-shadow: 0 12px 24px rgba(79, 70, 229, 0.15);
	}

	.step-icon {
		width: 64px;
		height: 64px;
		margin: 0 auto 1.5rem;
		background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
		color: white;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.75rem;
		font-weight: 700;
		box-shadow: 0 4px 12px rgba(79, 70, 229, 0.3);
	}

	.step h3 {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.25rem;
		font-weight: 600;
		color: #1e293b;
		margin-bottom: 0.75rem;
	}

	.step p {
		color: #64748b;
		line-height: 1.7;
	}

	/* Principles Section */
	.principles-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
		gap: 2rem;
	}

	.principle-card {
		text-align: center;
		padding: 2.5rem 2rem;
		background: white;
		border-radius: 16px;
		box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
		transition: all 0.3s ease;
	}

	.principle-card:hover {
		transform: translateY(-4px);
		box-shadow: 0 12px 24px rgba(79, 70, 229, 0.15);
	}

	.principle-icon {
		font-size: 3rem;
		margin-bottom: 1rem;
	}

	.principle-card h3 {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.25rem;
		font-weight: 600;
		color: #1e293b;
		margin-bottom: 0.75rem;
	}

	.principle-card p {
		color: #64748b;
		line-height: 1.7;
	}

	@media (max-width: 768px) {
		.home-logo {
			top: 1rem;
			left: 1rem;
		}

		.home-logo img {
			width: 40px;
			height: 40px;
		}

		.hero {
			padding: 6rem 1.5rem 3rem;
		}

		.content {
			padding: 0 1.5rem 3rem;
		}

		section {
			margin-bottom: 4rem;
		}

		.metrics-grid {
			grid-template-columns: repeat(2, 1fr);
			gap: 1rem;
		}

		.metric-card {
			padding: 1.5rem 1rem;
		}

		.metric-value {
			font-size: 2rem;
		}

		.steps {
			grid-template-columns: 1fr;
		}

		.principles-grid {
			grid-template-columns: 1fr;
		}
	}
</style>
