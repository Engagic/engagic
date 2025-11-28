<script lang="ts">
	import NavigationShell from '$lib/components/navigation/NavigationShell.svelte';
	import NavSection from '$lib/components/navigation/NavSection.svelte';
	import NavTab from '$lib/components/navigation/NavTab.svelte';
</script>

<NavigationShell pageTitle="About" homeLink="/about">
	{#snippet navigation()}
		<NavSection>
			<NavTab path="/about/general" title="What is Engagic?" iconColor="blue" />
			<NavTab path="/about/metrics" title="Impact Metrics" iconColor="green" />
			<NavTab path="/about/community" title="Community & Ecosystem" iconColor="purple" />
			<NavTab path="/about/donate" title="Donate" iconColor="red" />
			<NavTab path="/about/terms" title="Terms of Service" iconColor="orange" />
		</NavSection>
	{/snippet}

	{#snippet content()}
		<slot />
	{/snippet}
</NavigationShell>
