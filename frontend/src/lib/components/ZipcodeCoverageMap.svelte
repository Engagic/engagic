<script>
  import { onMount, onDestroy } from 'svelte';
  import maplibregl from 'maplibre-gl';
  import 'maplibre-gl/dist/maplibre-gl.css';
  
  export let cities = [];
  export let onCityClick = () => {};
  
  let mapContainer;
  let map;
  let hoveredZipId = null;
  
  const INITIAL_VIEW = {
    center: [-98.5795, 39.8283],
    zoom: 4,
    pitch: 0,
    bearing: 0
  };
  
  onMount(() => {
    map = new maplibregl.Map({
      container: mapContainer,
      style: 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json',
      ...INITIAL_VIEW,
      maxZoom: 12,
      minZoom: 3.5
    });
    
    map.on('load', async () => {
      // Add US states boundaries
      map.addSource('states', {
        type: 'geojson',
        data: 'https://raw.githubusercontent.com/PublicaMundi/MappingAPI/master/data/geojson/us-states.json'
      });
      
      map.addLayer({
        id: 'state-boundaries',
        type: 'line',
        source: 'states',
        paint: {
          'line-color': '#000000',
          'line-width': 1,
          'line-opacity': 0.5
        }
      });
      
      // Collect all unique zipcodes from cities
      const zipcodes = new Set();
      cities.forEach(city => {
        if (city.zipcode) {
          zipcodes.add(city.zipcode);
        }
      });
      
      // Create city boundary polygons from bounds
      const cityFeatures = cities.map((city, idx) => ({
        type: 'Feature',
        id: idx,
        properties: {
          city: city.name,
          state: city.state,
          meetingCount: city.meetingCount,
          population: city.population,
          zipcodeCount: city.zipcodeCount,
          city_banana: city.city_banana
        },
        geometry: city.bounds ? {
          type: 'Polygon',
          coordinates: [[
            [city.bounds[0], city.bounds[1]], // SW
            [city.bounds[2], city.bounds[1]], // SE
            [city.bounds[2], city.bounds[3]], // NE
            [city.bounds[0], city.bounds[3]], // NW
            [city.bounds[0], city.bounds[1]]  // Close polygon
          ]]
        } : {
          type: 'Point',
          coordinates: [city.lng, city.lat]
        }
      }));
      
      map.addSource('city-coverage', {
        type: 'geojson',
        data: {
          type: 'FeatureCollection',
          features: cityFeatures
        }
      });
      
      // Add city boundary fill
      map.addLayer({
        id: 'coverage-fill',
        type: 'fill',
        source: 'city-coverage',
        filter: ['==', ['geometry-type'], 'Polygon'],
        paint: {
          'fill-color': 'rgba(0, 0, 0, 0.7)',
          'fill-opacity': [
            'case',
            ['boolean', ['feature-state', 'hover'], false],
            0.8,
            0.6
          ]
        }
      });
      
      // Add city boundary outlines
      map.addLayer({
        id: 'coverage-outline',
        type: 'line',
        source: 'city-coverage',
        filter: ['==', ['geometry-type'], 'Polygon'],
        paint: {
          'line-color': '#000000',
          'line-width': 1,
          'line-opacity': 0.8
        }
      });
      
      // Add city center points
      map.addLayer({
        id: 'city-points',
        type: 'circle',
        source: 'city-coverage',
        paint: {
          'circle-radius': 4,
          'circle-color': '#ffffff',
          'circle-stroke-color': '#000000',
          'circle-stroke-width': 2,
          'circle-opacity': [
            'case',
            ['==', ['geometry-type'], 'Point'],
            1,
            0
          ]
        }
      });
      
      // Add labels for cities at higher zoom
      map.addLayer({
        id: 'city-labels',
        type: 'symbol',
        source: 'city-coverage',
        minzoom: 6,
        layout: {
          'text-field': ['get', 'city'],
          'text-font': ['Arial Unicode MS Regular'],
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
      
      // Hover effects with popup
      let popup = new maplibregl.Popup({
        closeButton: false,
        closeOnClick: false,
        offset: 15
      });
      
      map.on('mouseenter', 'coverage-fill', (e) => {
        map.getCanvas().style.cursor = 'pointer';
        
        if (e.features.length > 0) {
          if (hoveredZipId !== null) {
            map.setFeatureState(
              { source: 'city-coverage', id: hoveredZipId },
              { hover: false }
            );
          }
          hoveredZipId = e.features[0].id;
          map.setFeatureState(
            { source: 'city-coverage', id: hoveredZipId },
            { hover: true }
          );
          
          // Show popup with city info and meeting count
          let coordinates = e.features[0].geometry.coordinates.slice();
          const properties = e.features[0].properties;
          
          // For polygons, use the center of the bounds
          if (e.features[0].geometry.type === 'Polygon') {
            const bounds = new maplibregl.LngLatBounds();
            e.features[0].geometry.coordinates[0].forEach(coord => {
              bounds.extend(coord);
            });
            coordinates = bounds.getCenter();
          }
          
          popup.setLngLat(coordinates)
            .setHTML(`
              <div style="font-family: -apple-system, sans-serif; padding: 8px;">
                <strong>${properties.city}, ${properties.state}</strong><br>
                <span style="color: #666; font-size: 14px;">${properties.meetingCount} meetings available</span><br>
                <span style="color: #999; font-size: 12px;">${properties.zipcodeCount || 1} zipcodes covered</span>
              </div>
            `)
            .addTo(map);
        }
      });
      
      map.on('mouseleave', 'coverage-fill', () => {
        map.getCanvas().style.cursor = '';
        if (hoveredZipId !== null) {
          map.setFeatureState(
            { source: 'city-coverage', id: hoveredZipId },
            { hover: false }
          );
        }
        hoveredZipId = null;
        popup.remove();
      });
      
      // Click handler
      map.on('click', 'coverage-fill', (e) => {
        const properties = e.features[0].properties;
        onCityClick({
          name: properties.city,
          state: properties.state,
          city_banana: properties.city_banana
        });
      });
      
      // Add navigation controls
      map.addControl(new maplibregl.NavigationControl(), 'top-right');
      
      // Add scale
      map.addControl(new maplibregl.ScaleControl(), 'bottom-left');
    });
  });
  
  onDestroy(() => {
    if (map) map.remove();
  });
</script>

<div class="map-container" bind:this={mapContainer}>
  <div class="map-overlay">
    <h3>Geographic Coverage</h3>
    <p>Shaded areas represent zipcode boundaries with active municipal data</p>
  </div>
</div>

<style>
  .map-container {
    width: 100%;
    height: 700px;
    position: relative;
    background: #f8f8f8;
  }
  
  .map-overlay {
    position: absolute;
    top: 20px;
    left: 20px;
    background: rgba(255, 255, 255, 0.95);
    padding: 16px 20px;
    border: 1px solid #000;
    z-index: 1;
    max-width: 300px;
  }
  
  .map-overlay h3 {
    margin: 0 0 8px 0;
    font-size: 16px;
    font-weight: 600;
  }
  
  .map-overlay p {
    margin: 0;
    font-size: 13px;
    color: #666;
    line-height: 1.4;
  }
  
  :global(.maplibregl-ctrl-group) {
    background: #fff;
    border: 1px solid #000;
    box-shadow: none;
    border-radius: 0;
  }
  
  :global(.maplibregl-ctrl button) {
    background-color: #fff;
    border-radius: 0;
  }
  
  :global(.maplibregl-ctrl button:hover) {
    background-color: #f0f0f0;
  }
</style>