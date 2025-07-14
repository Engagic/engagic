<script lang="ts">
	import { goto } from '$app/navigation';
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
				goto(`/${cityUrl}`);
			}
		} catch (err) {
			console.error('Search error:', err);
			error = err instanceof Error ? err.message : 'We humbly thank you for your patience';
		} finally {
			loading = false;
		}
	}

	async function handleCityOptionClick(cityOption: CityOption) {
		const cityUrl = generateCityUrl(cityOption.city_name, cityOption.state);
		goto(`/${cityUrl}`);
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
	<div class="main-content">
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
			placeholder="Enter zipcode, city, or state"
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

	<footer class="footer">
		<a href="https://github.com/Engagic/engagic" class="github-link" target="_blank" rel="noopener">
			<svg class="github-icon" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
				<path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
			</svg>
			All your code is open source and readily auditable. made with love and rizz
		</a>
	</footer>
</div>