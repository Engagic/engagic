<script>
	import '../app.css';
	import { navigating } from '$app/stores';
	import { themeState } from '$lib/stores/theme.svelte';
	import ThemeToggle from '$lib/components/ThemeToggle.svelte';
	import { onMount } from 'svelte';

	onMount(() => {
		document.documentElement.classList.add(themeState.effectiveTheme);
	});
</script>

<svelte:head>
	{@html `<script>
		(function() {
			const theme = localStorage.getItem('theme') || 'system';
			const effectiveTheme = theme === 'system'
				? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
				: theme;
			document.documentElement.classList.add(effectiveTheme);
			document.documentElement.setAttribute('data-theme', effectiveTheme);
		})();
	</script>`}
</svelte:head>

{#if $navigating}
	<div class="navigation-loading"></div>
{/if}

<a href="#main-content" class="skip-to-main">Skip to main content</a>

<main id="main-content">
	<slot />
</main>

<ThemeToggle />