<script lang="ts">
	import { page } from '$app/state';
	import Footer from '$lib/components/Footer.svelte';
</script>

<svelte:head>
	<title>{page.status} - engagic</title>
</svelte:head>

<div class="container">
	<div class="main-content">
		<a href="/" class="compact-logo">engagic</a>

		<div class="error-container">
			<h1 class="error-code">{page.status}</h1>

			{#if page.status === 404}
				<h2 class="error-title">Page Not Found</h2>
				<p class="error-message">
					{page.error?.message || 'The page you are looking for does not exist.'}
				</p>
			{:else if page.status >= 500}
				<h2 class="error-title">Server Error</h2>
				<p class="error-message">
					{page.error?.message || 'Something went wrong on our end. Please try again later.'}
				</p>
			{:else}
				<h2 class="error-title">Something Went Wrong</h2>
				<p class="error-message">
					{page.error?.message || 'An unexpected error occurred.'}
				</p>
			{/if}

			<div class="error-actions">
				<a href="/" class="btn-primary">Back to Search</a>
			</div>
		</div>
	</div>

	<Footer />
</div>

<style>
	.container {
		width: var(--width-meetings);
		max-width: 100%;
		margin: 0 auto;
		min-height: 100vh;
		display: flex;
		flex-direction: column;
		position: relative;
	}

	.main-content {
		flex: 1;
	}

	.compact-logo {
		position: absolute;
		top: 1rem;
		right: 1rem;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.1rem;
		font-weight: 700;
		color: var(--civic-blue);
		text-decoration: none;
		z-index: 10;
	}

	.compact-logo:hover {
		opacity: 0.8;
	}

	.error-container {
		text-align: center;
		padding: 4rem 2rem;
		max-width: 600px;
		margin: 0 auto;
	}

	.error-code {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 6rem;
		font-weight: 700;
		color: var(--civic-blue);
		margin: 0;
		line-height: 1;
	}

	.error-title {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.75rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 1rem 0;
	}

	.error-message {
		font-family: system-ui, -apple-system, sans-serif;
		font-size: 1.1rem;
		color: var(--text-secondary);
		margin: 1rem 0;
		line-height: 1.6;
	}

	.error-actions {
		margin-top: 2rem;
	}

	.btn-primary {
		display: inline-block;
		padding: 0.75rem 1.5rem;
		background: var(--civic-blue);
		color: white;
		text-decoration: none;
		border-radius: var(--radius-md);
		font-family: 'IBM Plex Mono', monospace;
		font-weight: 500;
		transition: opacity var(--transition-fast);
	}

	.btn-primary:hover {
		opacity: 0.9;
	}

	@media (max-width: 640px) {
		.compact-logo {
			font-size: 0.95rem;
			right: 0.75rem;
		}

		.error-container {
			padding: 3rem 1rem;
		}

		.error-code {
			font-size: 4rem;
		}

		.error-title {
			font-size: 1.5rem;
		}

		.error-message {
			font-size: 1rem;
		}
	}
</style>
