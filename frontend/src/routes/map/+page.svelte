<script>
  import ProfessionalMap from '$lib/components/ProfessionalMap.svelte';
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  
  let cities = [];
  let loading = true;
  let error = null;
  
  onMount(async () => {
    try {
      const response = await fetch('https://api.engagic.org/api/cities/coverage');
      const result = await response.json();
      
      if (result.success) {
        cities = result.data.cities;
      } else {
        error = result.error || 'Failed to load coverage data';
      }
    } catch (err) {
      console.error('Error loading cities:', err);
      error = 'Failed to load city data';
    } finally {
      loading = false;
    }
  });
  
  function handleCityClick(city) {
    // Generate city URL from city_banana
    goto(`/${city.city_banana}`);
  }
</script>

<svelte:head>
  <title>Coverage Map - Engagic</title>
</svelte:head>

<main>
  <div class="header">
    <h1>Geographic Coverage</h1>
    <p>Shaded areas represent administrative boundaries with active municipal data</p>
  </div>
  
  {#if loading}
    <div class="loading">Loading map data...</div>
  {:else if error}
    <div class="error">{error}</div>
  {:else}
    <ProfessionalMap {cities} onCityClick={handleCityClick} />
  {/if}
</main>

<style>
  main {
    min-height: 100vh;
    background: white;
    padding: 0;
    margin: 0;
  }
  
  .header {
    text-align: center;
    padding: 2rem;
    border-bottom: 2px solid black;
  }
  
  h1 {
    font-size: 2rem;
    margin: 0 0 0.5rem 0;
    font-weight: bold;
  }
  
  p {
    margin: 0;
    color: #666;
  }
  
  .loading, .error {
    text-align: center;
    padding: 4rem;
    font-size: 1.2rem;
  }
  
  .error {
    color: red;
  }
</style>