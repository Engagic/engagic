<script>
  import { onMount, onDestroy } from 'svelte';
  import * as topojson from 'topojson-client';
  import { geoPath, geoAlbersUsa } from 'd3-geo';
  
  export let cities = [];
  export let onCityClick = () => {};
  
  let canvas;
  let ctx;
  let width = 1000;
  let height = 600;
  
  // Map state
  let scale = 1;
  let translateX = 0;
  let translateY = 0;
  let projection;
  let path;
  
  // Interaction state
  let isDragging = false;
  let lastX = 0;
  let lastY = 0;
  let hoveredCity = null;
  
  // Simplified US topology (embedded for true self-containment)
  // This is a highly simplified version - in production you'd use full resolution
  const US_TOPOLOGY = {
    "type": "Topology",
    "arcs": [
      // Simplified US outline - this would be much more detailed in production
      // For now using a basic rectangular approximation
      [[-125,49],[-125,25],[-80,25],[-80,49],[-125,49]]
    ],
    "objects": {
      "states": {
        "type": "GeometryCollection",
        "geometries": [
          {"type": "Polygon", "arcs": [[0]]}
        ]
      }
    }
  };
  
  function setupProjection() {
    projection = geoAlbersUsa()
      .scale(1300 * scale)
      .translate([width / 2 + translateX, height / 2 + translateY]);
    
    path = geoPath(projection).context(ctx);
  }
  
  function render() {
    if (!ctx) return;
    
    // Clear canvas
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, width, height);
    
    setupProjection();
    
    // Draw states outline
    ctx.strokeStyle = '#000000';
    ctx.lineWidth = 2;
    ctx.fillStyle = 'none';
    
    const states = topojson.feature(US_TOPOLOGY, US_TOPOLOGY.objects.states);
    ctx.beginPath();
    path(states);
    ctx.stroke();
    
    // Draw city coverage areas
    cities.forEach(city => {
      if (!city.bounds) return;
      
      const [west, south, east, north] = city.bounds;
      
      // Convert bounds to polygon
      const polygon = {
        type: 'Feature',
        geometry: {
          type: 'Polygon',
          coordinates: [[
            [west, south],
            [east, south],
            [east, north],
            [west, north],
            [west, south]
          ]]
        }
      };
      
      // Check if city is hovered
      const isHovered = hoveredCity === city.city_banana;
      
      ctx.fillStyle = isHovered ? 'rgba(0, 0, 0, 0.8)' : 'rgba(0, 0, 0, 0.6)';
      ctx.strokeStyle = '#000000';
      ctx.lineWidth = 1;
      
      ctx.beginPath();
      path(polygon);
      ctx.fill();
      ctx.stroke();
    });
  }
  
  // Mouse handlers
  function handleMouseDown(e) {
    isDragging = true;
    lastX = e.offsetX;
    lastY = e.offsetY;
    canvas.style.cursor = 'grabbing';
  }
  
  function handleMouseMove(e) {
    const x = e.offsetX;
    const y = e.offsetY;
    
    if (isDragging) {
      translateX += x - lastX;
      translateY += y - lastY;
      lastX = x;
      lastY = y;
      render();
    } else {
      // Check for city hover
      let foundCity = null;
      
      // Convert mouse position to geo coordinates
      if (projection && projection.invert) {
        const coords = projection.invert([x, y]);
        if (coords) {
          const [lng, lat] = coords;
          
          // Check each city's bounds
          cities.forEach(city => {
            if (city.bounds) {
              const [west, south, east, north] = city.bounds;
              if (lng >= west && lng <= east && lat >= south && lat <= north) {
                foundCity = city.city_banana;
              }
            }
          });
        }
      }
      
      if (foundCity !== hoveredCity) {
        hoveredCity = foundCity;
        canvas.style.cursor = foundCity ? 'pointer' : 'grab';
        render();
      }
    }
  }
  
  function handleMouseUp() {
    isDragging = false;
    canvas.style.cursor = hoveredCity ? 'pointer' : 'grab';
  }
  
  function handleWheel(e) {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    
    scale *= delta;
    scale = Math.max(0.5, Math.min(5, scale));
    
    render();
  }
  
  function handleClick(e) {
    if (hoveredCity) {
      const city = cities.find(c => c.city_banana === hoveredCity);
      if (city) onCityClick(city);
    }
  }
  
  onMount(async () => {
    ctx = canvas.getContext('2d');
    canvas.width = width;
    canvas.height = height;
    
    // For production, load real US topology data
    try {
      const response = await fetch('https://cdn.jsdelivr.net/npm/us-atlas@3/states-albers-10m.json');
      const realTopology = await response.json();
      
      // Use real data if available
      US_TOPOLOGY.arcs = realTopology.arcs;
      US_TOPOLOGY.objects = realTopology.objects;
    } catch (e) {
      console.log('Using embedded simplified geometry');
    }
    
    canvas.style.cursor = 'grab';
    render();
  });
  
  onDestroy(() => {
    // Cleanup listeners if needed
  });
</script>

<div class="map-wrapper">
  <canvas
    bind:this={canvas}
    on:mousedown={handleMouseDown}
    on:mousemove={handleMouseMove}
    on:mouseup={handleMouseUp}
    on:mouseleave={handleMouseUp}
    on:wheel={handleWheel}
    on:click={handleClick}
  />
  
  {#if hoveredCity}
    {@const city = cities.find(c => c.city_banana === hoveredCity)}
    {#if city}
      <div class="info-box">
        <strong>{city.name}, {city.state}</strong><br>
        {city.meetingCount} meetings • {city.zipcodeCount || 1} zipcodes
      </div>
    {/if}
  {/if}
</div>

<style>
  .map-wrapper {
    width: 100%;
    height: 700px;
    position: relative;
    background: #ffffff;
    overflow: hidden;
  }
  
  canvas {
    display: block;
    width: 100%;
    height: 100%;
    image-rendering: crisp-edges;
  }
  
  .info-box {
    position: absolute;
    top: 20px;
    right: 20px;
    background: white;
    border: 2px solid black;
    padding: 12px 16px;
    font-family: -apple-system, sans-serif;
    font-size: 14px;
    pointer-events: none;
  }
</style>