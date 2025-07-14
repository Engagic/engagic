<script>
  import { onMount, onDestroy } from 'svelte';
  import maplibregl from 'maplibre-gl';
  import 'maplibre-gl/dist/maplibre-gl.css';
  
  export let cities = [];
  export let onCityClick = () => {};
  
  let mapContainer;
  let map;
  
  onMount(() => {
    console.log('Simple map initializing with', cities.length, 'cities');
    
    // Use a simple style with just a background color
    map = new maplibregl.Map({
      container: mapContainer,
      style: {
        version: 8,
        sources: {},
        layers: [
          {
            id: 'background',
            type: 'background',
            paint: {
              'background-color': '#e8f4fd'
            }
          }
        ]
      },
      center: [-98.5795, 39.8283],
      zoom: 4
    });
    
    map.on('load', () => {
      console.log('Simple map loaded');
      
      // Add US states outline for context (using public GeoJSON)
      map.addSource('states', {
        type: 'geojson',
        data: 'https://raw.githubusercontent.com/PublicaMundi/MappingAPI/master/data/geojson/us-states.json'
      });
      
      map.addLayer({
        id: 'states-outline',
        type: 'line',
        source: 'states',
        paint: {
          'line-color': '#627BC1',
          'line-width': 1,
          'line-opacity': 0.5
        }
      });
      
      // Add cities
      if (cities.length > 0) {
        map.addSource('cities', {
          type: 'geojson',
          data: {
            type: 'FeatureCollection',
            features: cities.map((city, idx) => ({
              type: 'Feature',
              id: idx,
              properties: {
                name: city.name,
                state: city.state,
                meetingCount: city.meetingCount || 0
              },
              geometry: {
                type: 'Point',
                coordinates: [city.lng, city.lat]
              }
            }))
          }
        });
        
        // Add city points
        map.addLayer({
          id: 'city-points',
          type: 'circle',
          source: 'cities',
          paint: {
            'circle-radius': 6,
            'circle-color': '#ff4444',
            'circle-stroke-width': 2,
            'circle-stroke-color': '#ffffff'
          }
        });
        
        // Add city labels
        map.addLayer({
          id: 'city-labels',
          type: 'symbol',
          source: 'cities',
          layout: {
            'text-field': '{name}',
            'text-size': 12,
            'text-offset': [0, 1.5],
            'text-anchor': 'top'
          },
          paint: {
            'text-color': '#000000',
            'text-halo-color': '#ffffff',
            'text-halo-width': 2
          }
        });
      }
      
      // Add controls
      map.addControl(new maplibregl.NavigationControl(), 'top-right');
    });
    
    map.on('error', (e) => {
      console.error('Map error:', e);
    });
  });
  
  onDestroy(() => {
    if (map) map.remove();
  });
</script>

<div class="map-container" bind:this={mapContainer}></div>

<style>
  .map-container {
    width: 100%;
    height: 600px;
    position: relative;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
  }
</style>