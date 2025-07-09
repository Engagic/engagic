<script lang="ts">
	import { searchMeetings, type SearchResult, type CityOption } from '$lib/api';
	import { generateCityUrl } from '$lib/utils';

	let searchQuery = $state('');
	let searchResults: SearchResult | null = $state(null);
	let loading = $state(false);
	let error = $state('');

	async function handleSearch() {
		if (!searchQuery.trim()) return;

		loading = true;
		error = '';
		searchResults = null;

		try {
			const result = await searchMeetings(searchQuery.trim());
			searchResults = result;
			
			// If successful and has city info, navigate to city page
			if (result.success && result.city_name && result.state) {
				const cityUrl = generateCityUrl(result.city_name, result.state);
				window.location.href = `/${cityUrl}`;
			}
		} catch (err) {
			error = err instanceof Error ? err.message : 'Search failed';
		} finally {
			loading = false;
		}
	}

	async function handleCityOptionClick(cityOption: CityOption) {
		const cityUrl = generateCityUrl(cityOption.city_name, cityOption.state);
		window.location.href = `/${cityUrl}`;
	}

	function handleKeydown(event: KeyboardEvent) {
		if (event.key === 'Enter') {
			handleSearch();
		}
	}
</script>

<svelte:head>
	<title>engagic - civic engagement made simple</title>
	<meta name="description" content="Find your local government meetings and agendas" />
</svelte:head>

<div class="container">
	<header class="header">
		<a href="/" class="logo">engagic</a>
		<p class="tagline">civic engagement made simple</p>
	</header>

	<div class="search-section">
		<input 
			type="text" 
			class="search-input"
			bind:value={searchQuery}
			onkeydown={handleKeydown}
			placeholder="Enter zipcode or city, state (e.g. 94301 or Palo Alto, CA)"
			disabled={loading}
		/>
		<button 
			class="search-button" 
			onclick={handleSearch}
			disabled={loading || !searchQuery.trim()}
		>
			{loading ? 'Searching...' : 'Search'}
		</button>
	</div>

	{#if error}
		<div class="error-message">
			{error}
		</div>
	{/if}

	{#if searchResults}
		<div class="results-section">
			{#if searchResults.ambiguous && searchResults.city_options}
				<div class="ambiguous-cities">
					<div class="ambiguous-message">
						{searchResults.message}
					</div>
					<div class="city-options">
						{#each searchResults.city_options as cityOption}
							<button 
								class="city-option" 
								onclick={() => handleCityOptionClick(cityOption)}
							>
								{cityOption.display_name}
							</button>
						{/each}
					</div>
				</div>
			{:else if !searchResults.success}
				<div class="error-message">
					{searchResults.message || 'Search failed'}
				</div>
			{/if}
		</div>
	{:else if loading}
		<div class="loading">
			Searching for meetings...
		</div>
	{/if}
</div>