<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		title: string;
		description: string;
		url: string;
		type?: string;
		image?: string;
		extra?: Snippet;
	}

	const {
		title,
		description,
		url,
		type = 'website',
		image = 'https://engagic.org/icon-512.png',
		extra
	}: Props = $props();
</script>

<svelte:head>
	<title>{title}</title>
	<meta name="description" content="{description}" />
	<link rel="canonical" href="{url}" />

	<meta property="og:title" content="{title}" />
	<meta property="og:description" content="{description}" />
	<meta property="og:type" content="{type}" />
	<meta property="og:url" content="{url}" />
	<meta property="og:image" content="{image}" />
	<meta property="og:site_name" content="engagic" />

	<meta name="twitter:card" content="summary" />
	<meta name="twitter:title" content="{title}" />
	<meta name="twitter:description" content="{description}" />
	<meta name="twitter:image" content="{image}" />

	{#if extra}
		{@render extra()}
	{/if}
</svelte:head>
