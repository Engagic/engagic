<script>
  import { onMount, onDestroy } from 'svelte';
  import { topojson } from 'topojson-client';
  
  export let cities = [];
  export let onCityClick = () => {};
  
  let canvas;
  let ctx;
  let width;
  let height;
  
  // Transform state
  let scale = 1;
  let translateX = 0;
  let translateY = 0;
  
  // Mouse state for panning
  let isPanning = false;
  let lastX = 0;
  let lastY = 0;
  
  // Map data
  let usTopology = null;
  let cityBoundaries = new Map();
  let hoveredCity = null;
  
  // Projection
  function project(lon, lat) {
    // Albers USA projection (simplified)
    const x = (lon + 125) * 10 * scale + translateX;
    const y = (50 - lat) * 14 * scale + translateY;
    return [x, y];
  }
  
  async function loadMapData() {
    // For now, we'll use simplified US + states outline
    // In production, you'd load this from your own hosted TopoJSON file
    const response = await fetch('https://cdn.jsdelivr.net/npm/us-atlas@3/states-10m.json');
    usTopology = await response.json();
    
    // Process cities into boundaries
    cities.forEach(city => {
      if (city.bounds) {
        cityBoundaries.set(city.city_banana, {
          ...city,
          bounds: city.bounds
        });
      }
    });
    
    render();
  }
  
  function render() {
    if (!ctx || !usTopology) return;
    
    // Clear canvas
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, width, height);
    
    // Set up for drawing
    ctx.save();
    
    // Draw state boundaries
    ctx.strokeStyle = '#000000';
    ctx.lineWidth = 1;
    ctx.fillStyle = 'none';
    
    const states = topojson.feature(usTopology, usTopology.objects.states);
    states.features.forEach(state => {
      drawFeature(state.geometry);
    });
    
    // Draw nation outline
    ctx.lineWidth = 2;
    const nation = topojson.mesh(usTopology, usTopology.objects.nation);
    drawFeature(nation);
    
    // Draw city coverage areas
    cityBoundaries.forEach((city, cityBanana) => {
      ctx.fillStyle = hoveredCity === cityBanana ? 'rgba(0, 0, 0, 0.8)' : 'rgba(0, 0, 0, 0.6)';
      ctx.strokeStyle = '#000000';
      ctx.lineWidth = 1;
      
      // Draw bounds as polygon
      const [west, south, east, north] = city.bounds;
      
      ctx.beginPath();
      const sw = project(west, south);
      const se = project(east, south);
      const ne = project(east, north);
      const nw = project(west, north);
      
      ctx.moveTo(sw[0], sw[1]);
      ctx.lineTo(se[0], se[1]);
      ctx.lineTo(ne[0], ne[1]);
      ctx.lineTo(nw[0], nw[1]);
      ctx.closePath();
      
      ctx.fill();
      ctx.stroke();
    });
    
    ctx.restore();
  }
  
  function drawFeature(geometry) {
    if (geometry.type === 'Polygon') {
      drawPolygon(geometry.coordinates);
    } else if (geometry.type === 'MultiPolygon') {
      geometry.coordinates.forEach(polygon => drawPolygon(polygon));
    } else if (geometry.type === 'LineString') {
      drawLineString(geometry.coordinates);
    } else if (geometry.type === 'MultiLineString') {
      geometry.coordinates.forEach(line => drawLineString(line));
    }
  }
  
  function drawPolygon(coordinates) {
    ctx.beginPath();
    coordinates.forEach((ring, i) => {
      ring.forEach((coord, j) => {
        const [x, y] = project(coord[0], coord[1]);
        if (j === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
      });
      ctx.closePath();
    });
    ctx.stroke();
  }
  
  function drawLineString(coordinates) {
    ctx.beginPath();
    coordinates.forEach((coord, i) => {
      const [x, y] = project(coord[0], coord[1]);
      if (i === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    });
    ctx.stroke();
  }
  
  // Pan and zoom handlers
  function handleWheel(e) {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    const mouseX = e.offsetX;
    const mouseY = e.offsetY;
    
    // Zoom around mouse position
    translateX = mouseX - (mouseX - translateX) * delta;
    translateY = mouseY - (mouseY - translateY) * delta;
    scale *= delta;
    
    render();
  }
  
  function handleMouseDown(e) {
    isPanning = true;
    lastX = e.offsetX;
    lastY = e.offsetY;
  }
  
  function handleMouseMove(e) {
    if (isPanning) {
      const dx = e.offsetX - lastX;
      const dy = e.offsetY - lastY;
      translateX += dx;
      translateY += dy;
      lastX = e.offsetX;
      lastY = e.offsetY;
      render();
    } else {
      // Check hover
      const mouseX = e.offsetX;
      const mouseY = e.offsetY;
      let foundCity = null;
      
      cityBoundaries.forEach((city, cityBanana) => {
        const [west, south, east, north] = city.bounds;
        const sw = project(west, south);
        const ne = project(east, north);
        
        if (mouseX >= sw[0] && mouseX <= ne[0] && 
            mouseY >= ne[1] && mouseY <= sw[1]) {
          foundCity = cityBanana;
        }
      });
      
      if (foundCity !== hoveredCity) {
        hoveredCity = foundCity;
        canvas.style.cursor = foundCity ? 'pointer' : 'default';
        render();
      }
    }
  }
  
  function handleMouseUp() {
    isPanning = false;
  }
  
  function handleClick(e) {
    if (hoveredCity) {
      const city = cityBoundaries.get(hoveredCity);
      onCityClick(city);
    }
  }
  
  function handleResize() {
    width = canvas.clientWidth;
    height = canvas.clientHeight;
    canvas.width = width;
    canvas.height = height;
    
    // Center the map
    translateX = width / 2 - 500 * scale;
    translateY = height / 2 - 300 * scale;
    
    render();
  }
  
  onMount(() => {
    ctx = canvas.getContext('2d');
    width = canvas.clientWidth;
    height = canvas.clientHeight;
    canvas.width = width;
    canvas.height = height;
    
    // Initial position
    scale = 0.8;
    translateX = width / 2 - 500 * scale;
    translateY = height / 2 - 300 * scale;
    
    // Load data and render
    loadMapData();
    
    // Event listeners
    canvas.addEventListener('wheel', handleWheel);
    canvas.addEventListener('mousedown', handleMouseDown);
    canvas.addEventListener('mousemove', handleMouseMove);
    canvas.addEventListener('mouseup', handleMouseUp);
    canvas.addEventListener('mouseleave', handleMouseUp);
    canvas.addEventListener('click', handleClick);
    window.addEventListener('resize', handleResize);
  });
  
  onDestroy(() => {
    canvas?.removeEventListener('wheel', handleWheel);
    canvas?.removeEventListener('mousedown', handleMouseDown);
    canvas?.removeEventListener('mousemove', handleMouseMove);
    canvas?.removeEventListener('mouseup', handleMouseUp);
    canvas?.removeEventListener('mouseleave', handleMouseUp);
    canvas?.removeEventListener('click', handleClick);
    window?.removeEventListener('resize', handleResize);
  });
</script>

<div class="map-container">
  <canvas bind:this={canvas}></canvas>
  
  {#if hoveredCity}
    {@const city = cityBoundaries.get(hoveredCity)}
    <div class="tooltip" style="position: absolute; top: 20px; right: 20px;">
      <strong>{city.name}, {city.state}</strong><br>
      {city.meetingCount} meetings
    </div>
  {/if}
</div>

<style>
  .map-container {
    width: 100%;
    height: 700px;
    position: relative;
    background: #ffffff;
  }
  
  canvas {
    width: 100%;
    height: 100%;
    display: block;
  }
  
  .tooltip {
    background: white;
    border: 2px solid black;
    padding: 12px;
    font-family: -apple-system, sans-serif;
    font-size: 14px;
    pointer-events: none;
  }
</style>