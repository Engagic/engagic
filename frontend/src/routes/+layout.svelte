<script>
	import '../app.css';
	import { navigating } from '$app/stores';
</script>

{#if $navigating}
	<div class="navigation-loading"></div>
{/if}

<a href="#main-content" class="skip-to-main">Skip to main content</a>

<main id="main-content">
	<slot />
</main>