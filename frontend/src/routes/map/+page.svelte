<script>
  import ZipcodeCoverageMap from '$lib/components/ZipcodeCoverageMap.svelte';
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  
  let cities = [];
  let loading = true;
  let error = null;
  let stats = {
    totalCities: 0,
    totalMeetings: 0,
    populationCovered: 0,
    totalZipcodes: 0
  };
  
  onMount(async () => {
    try {
      const response = await fetch('https://api.engagic.org/api/cities/coverage');
      const result = await response.json();
      
      if (result.success) {
        cities = result.data.cities;
        stats = {
          totalCities: result.data.totalCities,
          totalMeetings: result.data.totalMeetings,
          populationCovered: result.data.populationCovered,
          totalZipcodes: result.data.totalZipcodes || 0
        };
      } else {
        error = result.error || 'Failed to load coverage data';
      }
    } catch (err) {
      console.error('Error loading coverage:', err);
      error = 'Network error loading coverage data';
    } finally {
      loading = false;
    }
  });
  
  function handleCityClick(city) {
    // Generate city_banana format: cityname + STATE (no spaces, lowercase city, uppercase state)
    const cityName = city.name.toLowerCase().replace(/[^a-z0-9]/g, '');
    const state = city.state.toUpperCase();
    const cityBanana = `${cityName}${state}`;
    goto(`/${cityBanana}`);
  }
  
  function formatPopulation(num) {
    if (num >= 1000000) {
      return (num / 1000000).toFixed(1) + 'M';
    } else if (num >= 1000) {
      return (num / 1000).toFixed(0) + 'K';
    }
    return num.toString();
  }
</script>

<svelte:head>
  <title>Geographic Coverage - Engagic</title>
  <meta name="description" content="Explore Engagic's coverage across {stats.totalZipcodes} zipcodes in {stats.totalCities} US cities. Find local government meetings in your area." />
</svelte:head>

<main>
  <div class="hero">
    <h1>Geographic Coverage Map</h1>
    <p class="subtitle">Shaded areas represent zipcode boundaries with active municipal data</p>
    
    {#if !loading}
      <div class="coverage-stats">
        <div class="stat">
          <span class="stat-value">{stats.totalZipcodes.toLocaleString()}</span>
          <span class="stat-label">Zipcodes Covered</span>
        </div>
        <div class="stat">
          <span class="stat-value">{stats.totalCities.toLocaleString()}</span>
          <span class="stat-label">Cities</span>
        </div>
        <div class="stat">
          <span class="stat-value">{formatPopulation(stats.populationCovered)}</span>
          <span class="stat-label">Population</span>
        </div>
        <div class="stat">
          <span class="stat-value">{stats.totalMeetings.toLocaleString()}</span>
          <span class="stat-label">Meetings</span>
        </div>
      </div>
    {/if}
  </div>
  
  <div class="map-section">
    {#if loading}
      <div class="loading-state">
        <div class="spinner"></div>
        <p>Loading coverage map...</p>
      </div>
    {:else if error}
      <div class="error-state">
        <p>Error: {error}</p>
        <button on:click={() => location.reload()}>Retry</button>
      </div>
    {:else}
      <ZipcodeCoverageMap {cities} onCityClick={handleCityClick} />
    {/if}
  </div>
  
  <div class="info-section">
    <div class="info-grid">
      <div class="info-card">
        <h3>Real-Time Updates</h3>
        <p>Our system continuously monitors city websites to bring you the latest meeting information as soon as it's published.</p>
      </div>
      <div class="info-card">
        <h3>AI-Powered Summaries</h3>
        <p>Complex agenda packets are automatically summarized using advanced AI, making civic participation accessible to everyone.</p>
      </div>
      <div class="info-card">
        <h3>Growing Coverage</h3>
        <p>We're constantly adding new cities. Can't find yours? Let us know and we'll prioritize adding it to our platform.</p>
      </div>
    </div>
  </div>
  
  <div class="cta-section">
    <h2>Can't find your city?</h2>
    <p>We're expanding coverage every week. Request your city and we'll notify you when it's available.</p>
    <a href="/request-city" class="cta-button">Request Your City</a>
  </div>
</main>

<style>
  main {
    min-height: 100vh;
    background: #ffffff;
    color: #000000;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  }
  
  .hero {
    text-align: center;
    padding: 3rem 2rem 2rem;
    background: #ffffff;
    border-bottom: 2px solid #000000;
  }
  
  h1 {
    font-size: 3rem;
    margin-bottom: 0.5rem;
    color: #000000;
    font-weight: 900;
    letter-spacing: -2px;
  }
  
  .subtitle {
    font-size: 1.125rem;
    color: #666666;
    margin-bottom: 2rem;
    font-weight: 400;
  }
  
  .coverage-stats {
    display: flex;
    justify-content: center;
    gap: 4rem;
    padding: 2rem 0;
  }
  
  .stat {
    display: flex;
    flex-direction: column;
    align-items: center;
  }
  
  .stat-value {
    font-size: 3rem;
    font-weight: 900;
    color: #000000;
    letter-spacing: -1px;
  }
  
  .stat-label {
    font-size: 0.875rem;
    color: #666666;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-top: 0.25rem;
    font-weight: 500;
  }
  
  .map-section {
    padding: 0;
    max-width: 100%;
    margin: 0;
  }
  
  .loading-state, .error-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 600px;
    background: white;
    border-radius: 12px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
  }
  
  .spinner {
    width: 50px;
    height: 50px;
    border: 4px solid #f3f3f3;
    border-top: 4px solid #3498db;
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin-bottom: 1rem;
  }
  
  .error-state button {
    background: #3498db;
    color: white;
    border: none;
    padding: 0.75rem 1.5rem;
    border-radius: 6px;
    cursor: pointer;
    font-size: 1rem;
    margin-top: 1rem;
  }
  
  .error-state button:hover {
    background: #2980b9;
  }
  
  .info-section {
    padding: 4rem 2rem;
    max-width: 1200px;
    margin: 0 auto;
  }
  
  .info-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 2rem;
  }
  
  .info-card {
    background: white;
    padding: 2rem;
    border-radius: 8px;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.05);
  }
  
  .info-card h3 {
    margin: 0 0 1rem 0;
    color: #2c3e50;
    font-size: 1.25rem;
  }
  
  .info-card p {
    margin: 0;
    color: #5a6c7d;
    line-height: 1.6;
  }
  
  .cta-section {
    text-align: center;
    padding: 4rem 2rem;
    background: #2c3e50;
    color: white;
  }
  
  .cta-section h2 {
    margin: 0 0 1rem 0;
    font-size: 2rem;
  }
  
  .cta-section p {
    margin: 0 0 2rem 0;
    font-size: 1.125rem;
    opacity: 0.9;
  }
  
  .cta-button {
    display: inline-block;
    background: #3498db;
    color: white;
    padding: 1rem 2rem;
    border-radius: 6px;
    text-decoration: none;
    font-weight: 600;
    transition: background 0.2s ease;
  }
  
  .cta-button:hover {
    background: #2980b9;
  }
  
  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }
  
  @media (max-width: 768px) {
    h1 {
      font-size: 2rem;
    }
    
    .coverage-stats {
      gap: 2rem;
    }
    
    .stat-value {
      font-size: 1.5rem;
    }
    
    .map-section {
      padding: 1rem;
    }
    
    .info-grid {
      grid-template-columns: 1fr;
      gap: 1.5rem;
    }
    
    .cta-section h2 {
      font-size: 1.5rem;
    }
  }
</style>