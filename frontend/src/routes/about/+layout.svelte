<script lang="ts">
	import PageNav from '$lib/components/navigation/PageNav.svelte';
	import PageNavSection from '$lib/components/navigation/PageNavSection.svelte';
	import PageNavTab from '$lib/components/navigation/PageNavTab.svelte';
	import Footer from '$lib/components/Footer.svelte';
</script>

<PageNav pageName="about" homeNavPath="/about" homeTitle="About Engagic" wideContent={true}>
	<svelte:fragment slot="navigation">
		<PageNavTab
			path="/about/general"
			title="What is Engagic?"
			iconColor="blue"
		/>
		<PageNavTab
			path="/about/metrics"
			title="Impact Metrics"
			iconColor="green"
		/>
		<PageNavTab
			path="/about/community"
			title="Community & Support"
			iconColor="purple"
		/>
		<PageNavTab
			path="/about/terms"
			title="Terms of Service"
			iconColor="orange"
		/>
	</svelte:fragment>

	<div slot="content">
		<slot />
		<Footer />
	</div>
</PageNav>
