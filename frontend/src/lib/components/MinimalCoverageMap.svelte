<script>
  import { onMount, onDestroy } from 'svelte';
  import maplibregl from 'maplibre-gl';
  import 'maplibre-gl/dist/maplibre-gl.css';
  
  export let cities = [];
  export let onCityClick = () => {};
  
  let mapContainer;
  let map;
  let animationId;
  let cityMarkers = [];
  
  const INITIAL_VIEW = {
    center: [-98.5795, 39.8283], // Center of USA
    zoom: 3.8,
    pitch: 0,
    bearing: 0
  };
  
  // US outline coordinates (simplified)
  const US_OUTLINE = {
    type: 'Feature',
    geometry: {
      type: 'Polygon',
      coordinates: [[
        [-125, 48], [-125, 32], [-117, 32], [-117, 33], [-114, 32],
        [-111, 31], [-108, 31], [-108, 32], [-106, 32], [-104, 33],
        [-103, 36], [-102, 37], [-100, 36], [-98, 35], [-96, 35],
        [-94, 33], [-94, 30], [-93, 29], [-91, 29], [-89, 29],
        [-84, 30], [-82, 28], [-81, 25], [-80, 25], [-80, 31],
        [-75, 35], [-75, 40], [-71, 41], [-70, 42], [-69, 45],
        [-67, 45], [-67, 47], [-69, 47], [-70, 46], [-74, 45],
        [-75, 45], [-79, 43], [-79, 42], [-82, 42], [-82, 46],
        [-84, 46], [-88, 48], [-90, 49], [-95, 49], [-95, 49],
        [-123, 49], [-125, 48]
      ]]
    }
  };
  
  onMount(() => {
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
              'background-color': '#ffffff'
            }
          }
        ]
      },
      ...INITIAL_VIEW,
      maxZoom: 8,
      minZoom: 3
    });
    
    map.on('load', () => {
      // Add US outline
      map.addSource('us-outline', {
        type: 'geojson',
        data: US_OUTLINE
      });
      
      map.addLayer({
        id: 'us-border',
        type: 'line',
        source: 'us-outline',
        paint: {
          'line-color': '#000000',
          'line-width': 2,
          'line-opacity': 1
        }
      });
      
      // Add cities with staggered animation
      cities.forEach((city, index) => {
        setTimeout(() => {
          const el = document.createElement('div');
          el.className = 'city-marker';
          el.style.animationDelay = `${index * 5}ms`;
          
          // Size based on meeting count
          const size = Math.min(Math.max(8, city.meetingCount), 30);
          el.style.width = `${size}px`;
          el.style.height = `${size}px`;
          
          // Click handler
          el.addEventListener('click', () => {
            onCityClick(city);
          });
          
          // Hover effect
          el.addEventListener('mouseenter', () => {
            el.classList.add('hover');
            
            // Show city name
            const label = document.createElement('div');
            label.className = 'city-label';
            label.textContent = `${city.name}, ${city.state}`;
            label.style.bottom = `${size + 5}px`;
            el.appendChild(label);
          });
          
          el.addEventListener('mouseleave', () => {
            el.classList.remove('hover');
            const label = el.querySelector('.city-label');
            if (label) label.remove();
          });
          
          const marker = new maplibregl.Marker({
            element: el,
            anchor: 'center'
          })
          .setLngLat([city.lng, city.lat])
          .addTo(map);
          
          cityMarkers.push(marker);
        }, index * 20); // Stagger appearance
      });
    });
    
    // Pulse animation
    let pulsePhase = 0;
    function animate() {
      pulsePhase += 0.02;
      
      document.querySelectorAll('.city-marker').forEach((marker, i) => {
        const offset = i * 0.1;
        const scale = 1 + Math.sin(pulsePhase + offset) * 0.1;
        marker.style.transform = `translate(-50%, -50%) scale(${scale})`;
      });
      
      animationId = requestAnimationFrame(animate);
    }
    
    setTimeout(() => {
      animate();
    }, cities.length * 20 + 500);
  });
  
  onDestroy(() => {
    if (animationId) cancelAnimationFrame(animationId);
    if (map) map.remove();
  });
</script>

<div class="map-container" bind:this={mapContainer}></div>

<style>
  .map-container {
    width: 100%;
    height: 600px;
    position: relative;
    background: #ffffff;
    overflow: hidden;
  }
  
  :global(.city-marker) {
    background: #000000;
    border-radius: 50%;
    cursor: pointer;
    position: absolute;
    transform: translate(-50%, -50%);
    animation: popIn 0.6s cubic-bezier(0.68, -0.55, 0.265, 1.55) forwards;
    transition: all 0.3s ease;
    opacity: 0;
  }
  
  :global(.city-marker.hover) {
    background: #ff0000;
    box-shadow: 0 0 20px rgba(255, 0, 0, 0.8);
    z-index: 1000;
  }
  
  :global(.city-label) {
    position: absolute;
    left: 50%;
    transform: translateX(-50%);
    background: #000000;
    color: #ffffff;
    padding: 4px 8px;
    font-size: 11px;
    font-family: monospace;
    white-space: nowrap;
    pointer-events: none;
    animation: fadeIn 0.2s ease;
  }
  
  @keyframes popIn {
    0% {
      opacity: 0;
      transform: translate(-50%, -50%) scale(0);
    }
    60% {
      opacity: 1;
      transform: translate(-50%, -50%) scale(1.2);
    }
    100% {
      opacity: 1;
      transform: translate(-50%, -50%) scale(1);
    }
  }
  
  @keyframes fadeIn {
    from { opacity: 0; transform: translateX(-50%) translateY(10px); }
    to { opacity: 1; transform: translateX(-50%) translateY(0); }
  }
  
  :global(.maplibregl-ctrl) {
    display: none !important;
  }
</style>