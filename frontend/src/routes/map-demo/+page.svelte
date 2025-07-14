<script>
  import CoverageMap from '$lib/components/CoverageMap.svelte';
  import { onMount } from 'svelte';
  
  let cities = [];
  let selectedCity = null;
  let showMap = false;
  
  // Generate realistic demo data
  onMount(() => {
    // Major US cities with realistic coordinates
    const majorCities = [
      { name: 'New York', state: 'NY', lat: 40.7128, lng: -74.0060, population: 8336817 },
      { name: 'Los Angeles', state: 'CA', lat: 34.0522, lng: -118.2437, population: 3898747 },
      { name: 'Chicago', state: 'IL', lat: 41.8781, lng: -87.6298, population: 2746388 },
      { name: 'Houston', state: 'TX', lat: 29.7604, lng: -95.3698, population: 2304580 },
      { name: 'Phoenix', state: 'AZ', lat: 33.4484, lng: -112.0740, population: 1608139 },
      { name: 'Philadelphia', state: 'PA', lat: 39.9526, lng: -75.1652, population: 1603797 },
      { name: 'San Antonio', state: 'TX', lat: 29.4241, lng: -98.4936, population: 1547253 },
      { name: 'San Diego', state: 'CA', lat: 32.7157, lng: -117.1611, population: 1423851 },
      { name: 'Dallas', state: 'TX', lat: 32.7767, lng: -96.7970, population: 1304379 },
      { name: 'San Jose', state: 'CA', lat: 37.3382, lng: -121.8863, population: 1021795 },
      { name: 'Austin', state: 'TX', lat: 30.2672, lng: -97.7431, population: 978908 },
      { name: 'Jacksonville', state: 'FL', lat: 30.3322, lng: -81.6557, population: 911507 },
      { name: 'Fort Worth', state: 'TX', lat: 32.7555, lng: -97.3308, population: 909585 },
      { name: 'Columbus', state: 'OH', lat: 39.9612, lng: -82.9988, population: 898553 },
      { name: 'Charlotte', state: 'NC', lat: 35.2271, lng: -80.8431, population: 885708 },
      { name: 'San Francisco', state: 'CA', lat: 37.7749, lng: -122.4194, population: 881549 },
      { name: 'Indianapolis', state: 'IN', lat: 39.7684, lng: -86.1581, population: 876384 },
      { name: 'Seattle', state: 'WA', lat: 47.6062, lng: -122.3321, population: 753675 },
      { name: 'Denver', state: 'CO', lat: 39.7392, lng: -104.9903, population: 727211 },
      { name: 'Washington', state: 'DC', lat: 38.9072, lng: -77.0369, population: 705749 },
      { name: 'Boston', state: 'MA', lat: 42.3601, lng: -71.0589, population: 692600 },
      { name: 'El Paso', state: 'TX', lat: 31.7619, lng: -106.4850, population: 681728 },
      { name: 'Nashville', state: 'TN', lat: 36.1627, lng: -86.7816, population: 670820 },
      { name: 'Detroit', state: 'MI', lat: 42.3314, lng: -83.0458, population: 670031 },
      { name: 'Oklahoma City', state: 'OK', lat: 35.4676, lng: -97.5164, population: 655057 },
      { name: 'Portland', state: 'OR', lat: 45.5152, lng: -122.6784, population: 654741 },
      { name: 'Las Vegas', state: 'NV', lat: 36.1699, lng: -115.1398, population: 651319 },
      { name: 'Memphis', state: 'TN', lat: 35.1495, lng: -90.0490, population: 651073 },
      { name: 'Louisville', state: 'KY', lat: 38.2527, lng: -85.7585, population: 617638 },
      { name: 'Baltimore', state: 'MD', lat: 39.2904, lng: -76.6122, population: 602495 }
    ];
    
    // Add more medium-sized cities to reach ~800
    const mediumCities = [
      { name: 'Milwaukee', state: 'WI', lat: 43.0389, lng: -87.9065 },
      { name: 'Albuquerque', state: 'NM', lat: 35.0844, lng: -106.6504 },
      { name: 'Tucson', state: 'AZ', lat: 32.2226, lng: -110.9747 },
      { name: 'Fresno', state: 'CA', lat: 36.7378, lng: -119.7871 },
      { name: 'Sacramento', state: 'CA', lat: 38.5816, lng: -121.4944 },
      { name: 'Mesa', state: 'AZ', lat: 33.4152, lng: -111.8315 },
      { name: 'Kansas City', state: 'MO', lat: 39.0997, lng: -94.5786 },
      { name: 'Atlanta', state: 'GA', lat: 33.7490, lng: -84.3880 },
      { name: 'Omaha', state: 'NE', lat: 41.2565, lng: -95.9345 },
      { name: 'Colorado Springs', state: 'CO', lat: 38.8339, lng: -104.8214 },
      { name: 'Raleigh', state: 'NC', lat: 35.7796, lng: -78.6382 },
      { name: 'Miami', state: 'FL', lat: 25.7617, lng: -80.1918 },
      { name: 'Long Beach', state: 'CA', lat: 33.7701, lng: -118.1937 },
      { name: 'Virginia Beach', state: 'VA', lat: 36.8529, lng: -75.9780 },
      { name: 'Oakland', state: 'CA', lat: 37.8044, lng: -122.2712 },
      { name: 'Minneapolis', state: 'MN', lat: 44.9778, lng: -93.2650 },
      { name: 'Tulsa', state: 'OK', lat: 36.1540, lng: -95.9928 },
      { name: 'Arlington', state: 'TX', lat: 32.7357, lng: -97.1081 },
      { name: 'New Orleans', state: 'LA', lat: 29.9511, lng: -90.0715 },
      { name: 'Wichita', state: 'KS', lat: 37.6872, lng: -97.3301 },
      { name: 'Cleveland', state: 'OH', lat: 41.4993, lng: -81.6944 },
      { name: 'Tampa', state: 'FL', lat: 27.9506, lng: -82.4572 },
      { name: 'Bakersfield', state: 'CA', lat: 35.3733, lng: -119.0187 },
      { name: 'Aurora', state: 'CO', lat: 39.7294, lng: -104.8319 },
      { name: 'Honolulu', state: 'HI', lat: 21.3099, lng: -157.8581 },
      { name: 'Anaheim', state: 'CA', lat: 33.8366, lng: -117.9143 },
      { name: 'Santa Ana', state: 'CA', lat: 33.7455, lng: -117.8677 },
      { name: 'Riverside', state: 'CA', lat: 33.9533, lng: -117.3962 },
      { name: 'Corpus Christi', state: 'TX', lat: 27.8006, lng: -97.3964 },
      { name: 'Lexington', state: 'KY', lat: 38.0406, lng: -84.5037 }
    ];
    
    // Generate ~800 cities with some randomization
    const allCities = [...majorCities, ...mediumCities];
    
    // Add more cities by slightly offsetting existing ones (simulating suburbs)
    const expandedCities = [];
    allCities.forEach(city => {
      expandedCities.push({
        ...city,
        meetingCount: Math.floor(Math.random() * 50) + 1,
        coverageType: Math.random() > 0.2 ? 'full' : 'partial'
      });
      
      // Add 5-10 nearby cities for each major city
      const numSuburbs = Math.floor(Math.random() * 6) + 5;
      for (let i = 0; i < numSuburbs; i++) {
        const offset = 0.1 + Math.random() * 0.3;
        const angle = Math.random() * 2 * Math.PI;
        expandedCities.push({
          name: `${city.name} Area ${i + 1}`,
          state: city.state,
          lat: city.lat + offset * Math.sin(angle),
          lng: city.lng + offset * Math.cos(angle),
          meetingCount: Math.floor(Math.random() * 20) + 1,
          population: Math.floor((city.population || 100000) * (0.1 + Math.random() * 0.3)),
          coverageType: Math.random() > 0.3 ? 'full' : 'partial'
        });
      }
    });
    
    cities = expandedCities.slice(0, 800);
    showMap = true;
  });
  
  function handleCityClick(city) {
    selectedCity = city;
    console.log('City clicked:', city);
  }
</script>

<main>
  <div class="hero">
    <h1>Engagic Coverage Map</h1>
    <p class="subtitle">Bringing transparency to {cities.length} cities across America</p>
    <div class="coverage-stats">
      <div class="stat">
        <span class="stat-value">800+</span>
        <span class="stat-label">Cities Covered</span>
      </div>
      <div class="stat">
        <span class="stat-value">110M+</span>
        <span class="stat-label">Population Reached</span>
      </div>
      <div class="stat">
        <span class="stat-value">33%</span>
        <span class="stat-label">US Coverage</span>
      </div>
    </div>
  </div>
  
  {#if showMap}
    <div class="map-wrapper">
      <CoverageMap {cities} onCityClick={handleCityClick} />
    </div>
  {/if}
  
  {#if selectedCity}
    <div class="selected-city-panel">
      <h3>Selected: {selectedCity.name}, {selectedCity.state}</h3>
      <p>Click would normally navigate to city meetings page</p>
      <button on:click={() => selectedCity = null}>Close</button>
    </div>
  {/if}
  
  <div class="legend">
    <h3>Coverage Legend</h3>
    <div class="legend-items">
      <div class="legend-item">
        <span class="dot" style="background: #44ff44"></span>
        <span>Active meetings available</span>
      </div>
      <div class="legend-item">
        <span class="dot" style="background: #ffaa44"></span>
        <span>5-10 meetings</span>
      </div>
      <div class="legend-item">
        <span class="dot" style="background: #ff8844"></span>
        <span>10-20 meetings</span>
      </div>
      <div class="legend-item">
        <span class="dot" style="background: #ff4444"></span>
        <span>20+ meetings</span>
      </div>
    </div>
  </div>
</main>

<style>
  main {
    max-width: 1400px;
    margin: 0 auto;
    padding: 2rem;
  }
  
  .hero {
    text-align: center;
    margin-bottom: 3rem;
  }
  
  h1 {
    font-size: 3rem;
    margin-bottom: 0.5rem;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }
  
  .subtitle {
    font-size: 1.25rem;
    color: #5a6c7d;
    margin-bottom: 2rem;
  }
  
  .coverage-stats {
    display: flex;
    justify-content: center;
    gap: 4rem;
    margin-bottom: 2rem;
  }
  
  .stat {
    display: flex;
    flex-direction: column;
    align-items: center;
  }
  
  .stat-value {
    font-size: 2.5rem;
    font-weight: bold;
    color: #2c3e50;
  }
  
  .stat-label {
    font-size: 0.875rem;
    color: #7f8c8d;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  
  .map-wrapper {
    margin-bottom: 3rem;
  }
  
  .selected-city-panel {
    position: fixed;
    bottom: 2rem;
    right: 2rem;
    background: white;
    padding: 1.5rem;
    border-radius: 8px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
    max-width: 300px;
  }
  
  .selected-city-panel h3 {
    margin: 0 0 0.5rem 0;
  }
  
  .selected-city-panel button {
    background: #e74c3c;
    color: white;
    border: none;
    padding: 0.5rem 1rem;
    border-radius: 4px;
    cursor: pointer;
    margin-top: 1rem;
  }
  
  .selected-city-panel button:hover {
    background: #c0392b;
  }
  
  .legend {
    background: rgba(255, 255, 255, 0.95);
    padding: 1.5rem;
    border-radius: 8px;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
  }
  
  .legend h3 {
    margin: 0 0 1rem 0;
    font-size: 1.125rem;
  }
  
  .legend-items {
    display: flex;
    gap: 2rem;
    flex-wrap: wrap;
  }
  
  .legend-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  
  .dot {
    width: 16px;
    height: 16px;
    border-radius: 50%;
    border: 2px solid white;
    box-shadow: 0 0 4px rgba(0, 0, 0, 0.2);
  }
  
  @media (max-width: 768px) {
    main {
      padding: 1rem;
    }
    
    h1 {
      font-size: 2rem;
    }
    
    .coverage-stats {
      gap: 2rem;
    }
    
    .stat-value {
      font-size: 1.75rem;
    }
    
    .legend-items {
      flex-direction: column;
      gap: 0.75rem;
    }
  }
</style>