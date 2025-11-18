<script lang="ts">
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { browser } from '$app/environment';

	export let pageName: 'about' | 'settings' = 'about';
	export let homeNavPath: string;
	export let homeTitle: string;
	export let contentPadding: boolean = false;
	export let wideContent: boolean = false;

	let screenWidth: number = 0;

	$: isMobile = screenWidth <= 750;
	$: isHome = $page.url.pathname === homeNavPath;

	function getDefaultNavPage(name: string): string {
		if (name === 'about') return '/about/general';
		if (name === 'settings') return '/settings/general';
		return homeNavPath;
	}

	$: {
		if (browser && !isMobile && isHome) {
			goto(getDefaultNavPage(pageName), { replaceState: true });
		}
	}
</script>

<svelte:window bind:innerWidth={screenWidth} />

<div id="{pageName}-page" class="page-nav-root">
	{#if !isMobile}
		<a href="/" class="home-link" aria-label="Return to engagic homepage">
			<img src="/icon-64.png" alt="engagic" class="logo-icon" />
		</a>
	{/if}

	<div class="page-nav-sidebar-container">
		{#if isMobile && !isHome}
			<a href={homeNavPath} class="back-button">
				←
			</a>
		{/if}

		<div class="page-nav-header">
			<h2 class="page-title">{homeTitle}</h2>
		</div>

		<nav
			class="page-nav-sidebar"
			class:visible-mobile={isMobile && isHome}
			aria-label="Page navigation"
		>
			<slot name="navigation" />
		</nav>
	</div>

	{#if !isMobile || !isHome}
		<main
			class="page-nav-content"
			class:padding={contentPadding}
			class:wide={wideContent}
		>
			<slot name="content" />
		</main>
	{/if}
</div>

<style>
	.page-nav-root {
		--nav-width: 320px;
		--nav-padding: 32px;
		display: grid;
		width: 100%;
		height: 100vh;
		position: fixed;
		top: 0;
		left: 0;
		grid-template-columns: var(--nav-width) 1fr;
		overflow: hidden;
		padding-left: var(--nav-padding);
	}

	.home-link {
		position: fixed;
		top: var(--nav-padding);
		left: var(--nav-padding);
		z-index: 100;
		transition: transform var(--transition-fast);
	}

	.home-link:hover {
		transform: scale(1.05);
	}

	.logo-icon {
		width: 48px;
		height: 48px;
		border-radius: var(--radius-md);
		box-shadow: 0 2px 12px var(--shadow-md);
	}

	.page-nav-sidebar-container {
		display: flex;
		flex-direction: column;
		width: var(--nav-width);
		padding-top: var(--nav-padding);
		padding-bottom: var(--space-xl);
		gap: var(--space-md);
		overflow: visible;
	}

	.page-nav-sidebar {
		display: flex;
		flex-direction: column;
		gap: var(--space-sm);
		padding-bottom: var(--space-md);
		overflow: visible;
	}

	.page-nav-header {
		margin-top: 64px;
	}

	.page-title {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.5rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
	}

	.page-nav-content {
		display: flex;
		flex-direction: column;
		width: 100%;
		height: 100%;
		padding: var(--nav-padding);
		padding-left: calc(var(--nav-padding) * 2);
		overflow-y: auto;
		overflow-x: hidden;
	}

	.page-nav-content > :global(*) {
		max-width: 800px;
	}

	.page-nav-content.wide > :global(*) {
		max-width: 1000px;
	}

	.back-button {
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
	}

	.back-button:hover {
		color: var(--text-primary);
		background: var(--surface-hover);
		border-radius: var(--radius-sm);
	}

	@media screen and (max-width: 750px) {
		.page-nav-root {
			display: flex;
			flex-direction: column;
			grid-template-columns: 1fr;
			padding: 0;
			position: relative;
			height: auto;
			min-height: 100vh;
		}

		.page-nav-sidebar-container {
			width: 100%;
			padding: var(--space-md);
			gap: var(--space-sm);
		}

		.page-nav-header {
			margin-top: 0;
			text-align: center;
		}

		.page-title {
			font-size: 1.2rem;
		}

		.page-nav-sidebar {
			padding: var(--space-md);
			padding-bottom: var(--space-xl);
			display: none;
		}

		.page-nav-sidebar.visible-mobile {
			display: flex;
		}

		.page-nav-content {
			padding: var(--space-md) 0;
			padding-top: 0;
			max-width: unset;
		}

		.page-nav-content.padding {
			padding: var(--space-md);
		}
	}
</style>
