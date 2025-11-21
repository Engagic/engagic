<script lang="ts">
	import { page } from '$app/stores';
	import { browser } from '$app/environment';

	interface Props {
		pageTitle: string;
		homeLink: string;
		contentWide?: boolean;
	}

	let { pageTitle, homeLink, contentWide = false }: Props = $props();

	let viewportWidth = $state(0);
	let isMobileView = $derived(viewportWidth <= 768);
	let isAtHomeRoute = $derived($page.url.pathname === homeLink);

	// Mobile: show navigation list only when at home route
	// Desktop: always show sidebar
	let shouldShowNavigation = $derived(!isMobileView || isAtHomeRoute);
	let shouldShowContent = $derived(!isMobileView || !isAtHomeRoute);
</script>

<svelte:window bind:innerWidth={viewportWidth} />

<div class="navigation-shell">
	<a
		href="/"
		class="home-logo-link"
		class:mobile-repositioned={isMobileView && !isAtHomeRoute}
		aria-label="Return to engagic homepage"
	>
		<img src="/icon-64.png" alt="engagic" class="logo-image" />
	</a>

	<div class="shell-sidebar">
		{#if isMobileView && !isAtHomeRoute}
			<a href={homeLink} class="mobile-back-button" aria-label="Go back">
				←
			</a>
		{/if}

		<div class="sidebar-header">
			<h2 class="page-title-heading">{pageTitle}</h2>
		</div>

		{#if shouldShowNavigation}
			<nav class="sidebar-navigation" aria-label="Page navigation">
				<slot name="navigation" />
			</nav>
		{/if}
	</div>

	{#if shouldShowContent}
		<main class="shell-content" class:wide={contentWide}>
			<slot name="content" />
		</main>
	{/if}
</div>

<style>
	.navigation-shell {
		--sidebar-width: 320px;
		--shell-padding: 32px;

		display: grid;
		width: 100%;
		height: 100vh;
		position: fixed;
		top: 0;
		left: 0;
		grid-template-columns: var(--sidebar-width) 1fr;
		overflow: hidden;
	}

	.home-logo-link {
		position: fixed;
		top: var(--shell-padding);
		left: var(--shell-padding);
		z-index: 100;
		transition: transform var(--transition-fast);
		text-decoration: none;
	}

	.home-logo-link:hover {
		transform: scale(1.05);
	}

	.logo-image {
		width: 48px;
		height: 48px;
		border-radius: var(--radius-md);
		box-shadow: 0 2px 12px var(--shadow-md);
		display: block;
	}

	.shell-sidebar {
		display: flex;
		flex-direction: column;
		width: var(--sidebar-width);
		padding: var(--shell-padding);
		padding-bottom: var(--space-xl);
		gap: var(--space-md);
		overflow-y: auto;
	}

	.sidebar-header {
		margin-top: 64px;
	}

	.page-title-heading {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.5rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
	}

	.sidebar-navigation {
		display: flex;
		flex-direction: column;
		gap: var(--space-sm);
		padding-bottom: var(--space-md);
	}

	.shell-content {
		display: flex;
		flex-direction: column;
		width: 100%;
		height: 100%;
		padding: var(--shell-padding);
		overflow-y: auto;
		overflow-x: hidden;
	}

	.shell-content > :global(*) {
		max-width: 1200px;
	}

	.shell-content.wide > :global(*) {
		max-width: 1400px;
	}

	.mobile-back-button {
		display: none;
	}

	/* Mobile Responsive */
	@media screen and (max-width: 768px) {
		.navigation-shell {
			display: flex;
			flex-direction: column;
			grid-template-columns: 1fr;
			padding: 0;
			position: relative;
			height: auto;
			min-height: 100vh;
		}

		.home-logo-link {
			position: fixed;
			top: var(--space-md);
			left: var(--space-md);
			z-index: 100;
		}

		.home-logo-link.mobile-repositioned {
			left: auto;
			right: var(--space-md);
		}

		.logo-image {
			width: 40px;
			height: 40px;
			border-radius: 10px;
		}

		.shell-sidebar {
			width: 100%;
			padding: var(--space-md);
			gap: var(--space-sm);
		}

		.sidebar-header {
			margin-top: 0;
			text-align: center;
		}

		.page-title-heading {
			font-size: 1.2rem;
		}

		.sidebar-navigation {
			padding: var(--space-md);
			padding-bottom: var(--space-xl);
		}

		.shell-content {
			padding: var(--space-md);
			padding-top: 0;
		}

		.shell-content > :global(*) {
			max-width: 100%;
		}

		.mobile-back-button {
			display: flex;
			align-items: center;
			color: var(--text-secondary);
			font-size: 1.5rem;
			padding: var(--space-xs);
			position: absolute;
			left: var(--space-xs);
			top: var(--space-md);
			cursor: pointer;
			transition: all var(--transition-fast);
			text-decoration: none;
			background: none;
			border: none;
		}

		.mobile-back-button:hover {
			color: var(--text-primary);
			background: var(--surface-hover);
			border-radius: var(--radius-sm);
		}
	}
</style>
