<script>
  import { onMount } from 'svelte';
  import maplibregl from 'maplibre-gl';
  import 'maplibre-gl/dist/maplibre-gl.css';
  
  let mapContainer;
  let debugInfo = {
    mapInitialized: false,
    tilesLoading: false,
    tilesLoaded: false,
    dataLoaded: false,
    layersAdded: false,
    errors: []
  };
  
  onMount(() => {
    console.log('Initializing map...');
    
    try {
      const map = new maplibregl.Map({
        container: mapContainer,
        style: {
          version: 8,
          sources: {
            'osm-tiles': {
              type: 'raster',
              tiles: [
                'https://a.tile.openstreetmap.org/{z}/{x}/{y}.png',
                'https://b.tile.openstreetmap.org/{z}/{x}/{y}.png',
                'https://c.tile.openstreetmap.org/{z}/{x}/{y}.png'
              ],
              tileSize: 256,
              attribution: '© OpenStreetMap contributors'
            }
          },
          layers: [
            {
              id: 'osm-tiles',
              type: 'raster',
              source: 'osm-tiles',
              minzoom: 0,
              maxzoom: 19
            }
          ]
        },
        center: [-98.5795, 39.8283],
        zoom: 4
      });
      
      debugInfo.mapInitialized = true;
      
      // Log tile loading events
      map.on('dataloading', (e) => {
        if (e.sourceId === 'osm-tiles') {
          debugInfo.tilesLoading = true;
          console.log('Tiles loading...');
        }
      });
      
      map.on('data', (e) => {
        if (e.sourceId === 'osm-tiles' && e.isSourceLoaded) {
          debugInfo.tilesLoaded = true;
          console.log('Tiles loaded!');
        }
      });
      
      map.on('load', () => {
        console.log('Map loaded!');
        debugInfo.dataLoaded = true;
        
        // Add a simple test marker
        map.addSource('test-point', {
          type: 'geojson',
          data: {
            type: 'Feature',
            geometry: {
              type: 'Point',
              coordinates: [-98.5795, 39.8283]
            }
          }
        });
        
        map.addLayer({
          id: 'test-point-layer',
          type: 'circle',
          source: 'test-point',
          paint: {
            'circle-radius': 10,
            'circle-color': '#ff0000'
          }
        });
        
        debugInfo.layersAdded = true;
      });
      
      map.on('error', (e) => {
        console.error('Map error:', e);
        debugInfo.errors = [...debugInfo.errors, e.error?.message || 'Unknown error'];
      });
      
    } catch (error) {
      console.error('Failed to initialize map:', error);
      debugInfo.errors = [...debugInfo.errors, error.message];
    }
  });
</script>

<h1>Map Debug Test</h1>

<div class="debug-info">
  <h2>Debug Information:</h2>
  <ul>
    <li>Map Initialized: {debugInfo.mapInitialized ? '✓' : '✗'}</li>
    <li>Tiles Loading: {debugInfo.tilesLoading ? '✓' : '✗'}</li>
    <li>Tiles Loaded: {debugInfo.tilesLoaded ? '✓' : '✗'}</li>
    <li>Map Data Loaded: {debugInfo.dataLoaded ? '✓' : '✗'}</li>
    <li>Layers Added: {debugInfo.layersAdded ? '✓' : '✗'}</li>
  </ul>
  
  {#if debugInfo.errors.length > 0}
    <h3>Errors:</h3>
    <ul class="errors">
      {#each debugInfo.errors as error}
        <li>{error}</li>
      {/each}
    </ul>
  {/if}
</div>

<div class="map-container" bind:this={mapContainer}></div>

<style>
  .map-container {
    width: 100%;
    height: 500px;
    border: 2px solid #333;
    margin-top: 20px;
  }
  
  .debug-info {
    background: #f0f0f0;
    padding: 20px;
    border-radius: 8px;
    margin: 20px 0;
  }
  
  .errors {
    color: red;
  }
  
  h1 {
    margin: 20px;
  }
</style>