<script>
  import { onMount, onDestroy } from 'svelte';
  import maplibregl from 'maplibre-gl';
  import 'maplibre-gl/dist/maplibre-gl.css';
  
  export let cities = [];
  export let onCityClick = () => {};
  
  let mapContainer;
  let map;
  let hoveredCityId = null;
  let mapLoaded = false;
  
  const INITIAL_VIEW = {
    center: [-98.5795, 39.8283], // Center of USA
    zoom: 3.5,
    pitch: 0,
    bearing: 0
  };
  
  // Update map when cities data changes
  $: if (map && mapLoaded && cities.length > 0) {
    console.log('Updating cities data on map...');
    const source = map.getSource('cities');
    if (source) {
      source.setData({
        type: 'FeatureCollection',
        features: cities.map((city, idx) => ({
          type: 'Feature',
          id: idx,
          properties: {
            name: city.name,
            state: city.state,
            meetingCount: city.meetingCount || 0,
            population: city.population || 0,
            coverageType: city.vendor || 'unknown',
            city_banana: city.city_banana || null
          },
          geometry: {
            type: 'Point',
            coordinates: [city.lng, city.lat]
          }
        }))
      });
    }
  }
  
  onMount(() => {
    console.log('CoverageMap mounted with cities:', cities);
    console.log('Number of cities:', cities.length);
    
    map = new maplibregl.Map({
      container: mapContainer,
      style: {
        version: 8,
        sources: {
          'carto-dark': {
            type: 'raster',
            tiles: [
              'https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
              'https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
              'https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png'
            ],
            tileSize: 256,
            attribution: '© CARTO'
          }
        },
        layers: [
          {
            id: 'base-tiles',
            type: 'raster',
            source: 'carto-dark',
            minzoom: 0,
            maxzoom: 19,
            paint: {
              'raster-opacity': 1,
              'raster-contrast': 0.2,
              'raster-brightness-min': 0,
              'raster-hue-rotate': 180,
              'raster-saturation': -1
            }
          }
        ],
        glyphs: 'https://fonts.openmaptiles.org/{fontstack}/{range}.pbf'
      },
      ...INITIAL_VIEW,
      maxZoom: 12,
      minZoom: 3
    });
    
    map.on('load', () => {
      console.log('Map loaded, adding city data...');
      console.log('Cities to add:', cities.length);
      mapLoaded = true;
      
      // Add city data source
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
              meetingCount: city.meetingCount || 0,
              population: city.population || 0,
              coverageType: city.vendor || 'unknown',
              city_banana: city.city_banana || null
            },
            geometry: {
              type: 'Point',
              coordinates: [city.lng, city.lat]
            }
          }))
        },
        cluster: true,
        clusterMaxZoom: 7,
        clusterRadius: 50,
        clusterProperties: {
          totalMeetings: ['+', ['get', 'meetingCount']]
        }
      });
      
      // Clustered circles
      map.addLayer({
        id: 'clusters',
        type: 'circle',
        source: 'cities',
        filter: ['has', 'point_count'],
        paint: {
          'circle-color': [
            'interpolate',
            ['linear'],
            ['get', 'point_count'],
            10, '#00ff41',
            100, '#00ffff',
            500, '#ff00ff'
          ],
          'circle-radius': [
            'interpolate',
            ['linear'],
            ['get', 'point_count'],
            10, 20,
            100, 30,
            500, 40
          ],
          'circle-blur': 1,
          'circle-opacity': 0.9,
          'circle-stroke-width': 2,
          'circle-stroke-color': '#00ff41',
          'circle-stroke-opacity': 0.8
        }
      });
      
      // Cluster counts
      map.addLayer({
        id: 'cluster-count',
        type: 'symbol',
        source: 'cities',
        filter: ['has', 'point_count'],
        layout: {
          'text-field': '{point_count_abbreviated}',
          'text-font': ['Arial Unicode MS Bold'],
          'text-size': 14
        },
        paint: {
          'text-color': '#00ff41',
          'text-halo-color': '#000000',
          'text-halo-width': 2
        }
      });
      
      // Individual city points
      map.addLayer({
        id: 'unclustered-point',
        type: 'circle',
        source: 'cities',
        filter: ['!', ['has', 'point_count']],
        paint: {
          'circle-color': [
            'case',
            ['>', ['get', 'meetingCount'], 20], '#ff0080',
            ['>', ['get', 'meetingCount'], 10], '#ff00ff',
            ['>', ['get', 'meetingCount'], 5], '#00ffff',
            ['>', ['get', 'meetingCount'], 0], '#00ff41',
            '#404040'
          ],
          'circle-radius': [
            'interpolate',
            ['linear'],
            ['zoom'],
            3, 3,
            8, 8,
            12, 12
          ],
          'circle-stroke-width': 1,
          'circle-stroke-color': [
            'case',
            ['>', ['get', 'meetingCount'], 20], '#ff0080',
            ['>', ['get', 'meetingCount'], 10], '#ff00ff',
            ['>', ['get', 'meetingCount'], 5], '#00ffff',
            ['>', ['get', 'meetingCount'], 0], '#00ff41',
            '#404040'
          ],
          'circle-stroke-opacity': 0.8,
          'circle-opacity': [
            'case',
            ['boolean', ['feature-state', 'hover'], false],
            1,
            0.7
          ]
        }
      });
      
      // City labels (only at high zoom)
      map.addLayer({
        id: 'city-labels',
        type: 'symbol',
        source: 'cities',
        filter: ['!', ['has', 'point_count']],
        minzoom: 8,
        layout: {
          'text-field': [
            'format',
            ['get', 'name'], { 'font-scale': 1.2 },
            '\n', {},
            ['concat', ['to-string', ['get', 'meetingCount']], ' meetings'], { 'font-scale': 0.8 }
          ],
          'text-font': ['Arial Unicode MS Bold'],
          'text-size': 12,
          'text-offset': [0, 1.5],
          'text-anchor': 'top'
        },
        paint: {
          'text-color': '#00ff41',
          'text-halo-color': '#000000',
          'text-halo-width': 1,
          'text-halo-blur': 1
        }
      });
      
      // Coverage heatmap layer
      if (cities.length > 0) {
        const bounds = new maplibregl.LngLatBounds();
        cities.forEach(city => bounds.extend([city.lng, city.lat]));
        
        // Add heatmap for coverage density
        map.addLayer({
          id: 'coverage-heat',
          type: 'heatmap',
          source: 'cities',
          maxzoom: 9,
          paint: {
            'heatmap-weight': [
              'interpolate',
              ['linear'],
              ['get', 'meetingCount'],
              0, 0.1,
              10, 0.5,
              50, 1
            ],
            'heatmap-intensity': [
              'interpolate',
              ['linear'],
              ['zoom'],
              0, 1,
              9, 3
            ],
            'heatmap-color': [
              'interpolate',
              ['linear'],
              ['heatmap-density'],
              0, 'rgba(0,0,0,0)',
              0.2, 'rgba(0,255,65,0.1)',
              0.4, 'rgba(0,255,255,0.2)',
              0.6, 'rgba(255,0,255,0.3)',
              0.8, 'rgba(255,0,128,0.4)',
              1, 'rgba(255,0,128,0.6)'
            ],
            'heatmap-radius': [
              'interpolate',
              ['linear'],
              ['zoom'],
              0, 2,
              9, 20
            ],
            'heatmap-opacity': 0.6
          }
        }, 'clusters');
      }
      
      // Hover interactions
      let popup = new maplibregl.Popup({
        closeButton: false,
        closeOnClick: false,
        offset: 15
      });
      
      map.on('mouseenter', 'unclustered-point', (e) => {
        map.getCanvas().style.cursor = 'pointer';
        
        if (e.features.length > 0) {
          if (hoveredCityId !== null) {
            map.setFeatureState(
              { source: 'cities', id: hoveredCityId },
              { hover: false }
            );
          }
          hoveredCityId = e.features[0].id;
          map.setFeatureState(
            { source: 'cities', id: hoveredCityId },
            { hover: true }
          );
          
          const coordinates = e.features[0].geometry.coordinates.slice();
          const properties = e.features[0].properties;
          
          popup.setLngLat(coordinates)
            .setHTML(`
              <div class="popup-content">
                <h3>${properties.name}, ${properties.state}</h3>
                <p><strong>${properties.meetingCount}</strong> upcoming meetings</p>
                ${properties.population ? `<p>Population: ${properties.population.toLocaleString()}</p>` : ''}
                <p class="click-hint">Click to view meetings →</p>
              </div>
            `)
            .addTo(map);
        }
      });
      
      map.on('mouseleave', 'unclustered-point', () => {
        map.getCanvas().style.cursor = '';
        if (hoveredCityId !== null) {
          map.setFeatureState(
            { source: 'cities', id: hoveredCityId },
            { hover: false }
          );
        }
        hoveredCityId = null;
        popup.remove();
      });
      
      // Click handler
      map.on('click', 'unclustered-point', (e) => {
        const properties = e.features[0].properties;
        onCityClick({
          name: properties.name,
          state: properties.state,
          coordinates: e.features[0].geometry.coordinates,
          city_banana: properties.city_banana
        });
      });
      
      // Click on clusters to zoom
      map.on('click', 'clusters', (e) => {
        const features = map.queryRenderedFeatures(e.point, {
          layers: ['clusters']
        });
        const clusterId = features[0].properties.cluster_id;
        map.getSource('cities').getClusterExpansionZoom(
          clusterId,
          (err, zoom) => {
            if (err) return;
            
            map.easeTo({
              center: features[0].geometry.coordinates,
              zoom: zoom
            });
          }
        );
      });
      
      // Add navigation controls
      map.addControl(new maplibregl.NavigationControl(), 'top-right');
      
      // Add fullscreen control
      map.addControl(new maplibregl.FullscreenControl(), 'top-right');
      
      // Stats overlay
      const stats = document.createElement('div');
      stats.className = 'map-stats';
      stats.innerHTML = `
        <div class="stat-item">
          <span class="stat-number">${cities.length}</span>
          <span class="stat-label">Cities Covered</span>
        </div>
        <div class="stat-item">
          <span class="stat-number">${cities.reduce((sum, c) => sum + (c.meetingCount || 0), 0)}</span>
          <span class="stat-label">Total Meetings</span>
        </div>
      `;
      mapContainer.appendChild(stats);
    });
    
    // Add error handling
    map.on('error', (e) => {
      console.error('Map error:', e);
      if (e.error) {
        console.error('Error details:', e.error.message);
      }
    });
  });
  
  onDestroy(() => {
    if (map) map.remove();
  });
</script>

<div class="map-container" bind:this={mapContainer}>
  <div class="loading-overlay">
    <div class="loading-spinner"></div>
    <p>Loading coverage map...</p>
  </div>
</div>

<style>
  .map-container {
    width: 100%;
    height: 600px;
    position: relative;
    border-radius: 0;
    overflow: hidden;
    background: #000;
    border: 2px solid #00ff41;
    box-shadow: 
      0 0 20px rgba(0, 255, 65, 0.5),
      inset 0 0 20px rgba(0, 255, 65, 0.1);
  }
  
  .loading-overlay {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(255, 255, 255, 0.9);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    opacity: 0;
    animation: fadeOut 0.3s ease-out 0.5s forwards;
    pointer-events: none;
  }
  
  .loading-spinner {
    width: 40px;
    height: 40px;
    border: 3px solid #f3f3f3;
    border-top: 3px solid #3498db;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }
  
  :global(.map-stats) {
    position: absolute;
    top: 20px;
    left: 20px;
    background: rgba(0, 0, 0, 0.9);
    padding: 20px;
    border: 1px solid #00ff41;
    box-shadow: 
      0 0 10px rgba(0, 255, 65, 0.5),
      inset 0 0 10px rgba(0, 255, 65, 0.1);
    display: flex;
    gap: 30px;
    backdrop-filter: blur(10px);
    font-family: monospace;
  }
  
  :global(.stat-item) {
    display: flex;
    flex-direction: column;
    align-items: center;
  }
  
  :global(.stat-number) {
    font-size: 32px;
    font-weight: normal;
    color: #00ff41;
    text-shadow: 0 0 10px rgba(0, 255, 65, 0.8);
    font-family: monospace;
    letter-spacing: 2px;
  }
  
  :global(.stat-label) {
    font-size: 10px;
    color: #00ff41;
    text-transform: uppercase;
    letter-spacing: 1px;
    opacity: 0.7;
    font-family: monospace;
  }
  
  :global(.maplibregl-popup-content) {
    padding: 0;
    border-radius: 0;
    background: rgba(0, 0, 0, 0.95);
    border: 1px solid #00ff41;
    box-shadow: 0 0 10px rgba(0, 255, 65, 0.5);
  }
  
  :global(.popup-content) {
    padding: 15px;
    min-width: 200px;
    font-family: monospace;
    background: #000;
  }
  
  :global(.popup-content h3) {
    margin: 0 0 10px 0;
    font-size: 14px;
    font-weight: normal;
    color: #00ff41;
    text-transform: uppercase;
    letter-spacing: 1px;
    text-shadow: 0 0 5px rgba(0, 255, 65, 0.8);
  }
  
  :global(.popup-content p) {
    margin: 5px 0;
    font-size: 12px;
    color: #00ffff;
    opacity: 0.9;
  }
  
  :global(.click-hint) {
    font-size: 11px;
    color: #ff00ff;
    margin-top: 10px;
    font-style: normal;
    text-transform: uppercase;
    letter-spacing: 1px;
    animation: pulse 2s infinite;
  }
  
  @keyframes fadeOut {
    to {
      opacity: 0;
    }
  }
  
  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }
  
  @keyframes pulse {
    0% { opacity: 0.6; }
    50% { opacity: 1; }
    100% { opacity: 0.6; }
  }
  
  :global(.maplibregl-ctrl-group) {
    background: rgba(0, 0, 0, 0.9);
    border: 1px solid #00ff41;
    box-shadow: 0 0 10px rgba(0, 255, 65, 0.3);
  }
  
  :global(.maplibregl-ctrl-group button) {
    background: #000;
    color: #00ff41;
    border-color: #00ff41;
  }
  
  :global(.maplibregl-ctrl-group button:hover) {
    background: #00ff41;
    color: #000;
  }
  
  @media (max-width: 768px) {
    .map-container {
      height: 400px;
      border-radius: 0;
    }
    
    :global(.map-stats) {
      top: 10px;
      left: 10px;
      padding: 12px;
      gap: 20px;
    }
    
    :global(.stat-number) {
      font-size: 20px;
    }
    
    :global(.stat-label) {
      font-size: 10px;
    }
  }
</style>