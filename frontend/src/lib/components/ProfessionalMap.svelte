<script>
  import { onMount, onDestroy } from 'svelte';
  import * as topojson from 'topojson-client';
  import { geoPath, geoAlbersUsa } from 'd3-geo';
  
  export let cities = [];
  export let onCityClick = () => {};
  
  let canvas;
  let ctx;
  let container;
  
  // Canvas dimensions
  let width = 960;
  let height = 600;
  let dpr = 1; // device pixel ratio
  
  // Map data
  let usData = null;
  let projection;
  let path;
  
  // Transform state
  let transform = {
    x: 0,
    y: 0,
    k: 1
  };
  
  // Animation state
  let animationFrame = null;
  let targetTransform = null;
  let isAnimating = false;
  
  // Interaction state
  let isDragging = false;
  let dragStart = { x: 0, y: 0 };
  let lastTransform = { x: 0, y: 0, k: 1 };
  let hoveredCity = null;
  let mousePos = { x: 0, y: 0 };
  
  // Load map data
  async function loadMapData() {
    console.log('Loading map data...');
    const response = await fetch('/us-10m.json');
    console.log('Response status:', response.status);
    usData = await response.json();
    console.log('Map data loaded, objects:', Object.keys(usData.objects));
    
    // Initialize projection with proper scale for viewport
    const scale = Math.min(width, height) * 1.3;
    projection = geoAlbersUsa()
      .scale(scale)
      .translate([width / 2, height / 2]);
    
    path = geoPath().projection(projection);
    console.log('Projection initialized, scale:', scale);
    
    // Reset transform to center
    transform = { x: 0, y: 0, k: 1 };
    
    render();
  }
  
  // Render the map
  function render() {
    if (!ctx || !usData) {
      console.log('Cannot render - ctx:', !!ctx, 'usData:', !!usData);
      return;
    }
    
    // Clear canvas
    ctx.save();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    
    // Fill white background
    ctx.fillStyle = 'white';
    ctx.fillRect(0, 0, width, height);
    
    // Draw a test rectangle to ensure canvas is working
    ctx.fillStyle = 'red';
    ctx.fillRect(10, 10, 50, 50);
    
    // Apply transform
    ctx.translate(transform.x, transform.y);
    ctx.scale(transform.k, transform.k);
    
    try {
      // Draw nation outline
      console.log('Drawing nation outline...');
      ctx.strokeStyle = '#000';
      ctx.lineWidth = 2 / transform.k;
      ctx.beginPath();
      const nation = topojson.mesh(usData, usData.objects.nation || usData.objects.states, (a, b) => a === b);
      console.log('Nation mesh:', nation);
      path(nation);
      ctx.stroke();
      
      // Draw state boundaries
      console.log('Drawing state boundaries...');
      ctx.strokeStyle = '#000';
      ctx.lineWidth = 1 / transform.k;
      ctx.beginPath();
      const states = topojson.mesh(usData, usData.objects.states, (a, b) => a !== b);
      console.log('States mesh:', states);
      path(states);
      ctx.stroke();
    } catch (e) {
      console.error('Error drawing map:', e);
    }
    
    // Draw city coverage areas (commented out for debugging)
    /*
    cities.forEach(city => {
      if (!city.bounds) return;
      
      const [west, south, east, north] = city.bounds;
      
      // Project bounds
      const sw = projection([west, south]);
      const ne = projection([east, north]);
      
      if (!sw || !ne) return;
      
      // Check if hovered
      const isHovered = hoveredCity === city.city_banana;
      
      // Draw coverage area
      ctx.fillStyle = isHovered ? 'rgba(0, 0, 0, 0.8)' : 'rgba(0, 0, 0, 0.6)';
      ctx.strokeStyle = '#000';
      ctx.lineWidth = 1 / transform.k;
      
      ctx.beginPath();
      ctx.rect(sw[0], ne[1], ne[0] - sw[0], sw[1] - ne[1]);
      ctx.fill();
      ctx.stroke();
    });
    */
    
    ctx.restore();
  }
  
  // Smooth zoom animation
  function zoomTo(targetK, centerX, centerY) {
    // Calculate target position to keep center point fixed
    const dx = centerX - transform.x;
    const dy = centerY - transform.y;
    
    targetTransform = {
      x: centerX - dx * targetK / transform.k,
      y: centerY - dy * targetK / transform.k,
      k: targetK
    };
    
    isAnimating = true;
    animate();
  }
  
  // Animation loop
  function animate() {
    if (!isAnimating || !targetTransform) return;
    
    // Interpolate transform
    const ease = 0.1;
    transform.x += (targetTransform.x - transform.x) * ease;
    transform.y += (targetTransform.y - transform.y) * ease;
    transform.k += (targetTransform.k - transform.k) * ease;
    
    // Check if close enough
    const dx = Math.abs(targetTransform.x - transform.x);
    const dy = Math.abs(targetTransform.y - transform.y);
    const dk = Math.abs(targetTransform.k - transform.k);
    
    if (dx < 0.1 && dy < 0.1 && dk < 0.001) {
      transform = { ...targetTransform };
      isAnimating = false;
    }
    
    render();
    
    if (isAnimating) {
      animationFrame = requestAnimationFrame(animate);
    }
  }
  
  // Mouse handlers
  function handleWheel(e) {
    e.preventDefault();
    
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    const targetK = Math.max(0.5, Math.min(5, transform.k * delta));
    
    zoomTo(targetK, x, y);
  }
  
  function handleMouseDown(e) {
    if (isAnimating) {
      isAnimating = false;
      cancelAnimationFrame(animationFrame);
    }
    
    isDragging = true;
    dragStart = { x: e.clientX, y: e.clientY };
    lastTransform = { ...transform };
    canvas.style.cursor = 'grabbing';
  }
  
  function handleMouseMove(e) {
    const rect = canvas.getBoundingClientRect();
    mousePos = {
      x: e.clientX - rect.left,
      y: e.clientY - rect.top
    };
    
    if (isDragging) {
      transform.x = lastTransform.x + (e.clientX - dragStart.x);
      transform.y = lastTransform.y + (e.clientY - dragStart.y);
      render();
    } else {
      // Check for city hover
      updateHover();
    }
  }
  
  function handleMouseUp() {
    isDragging = false;
    canvas.style.cursor = hoveredCity ? 'pointer' : 'grab';
  }
  
  function handleClick() {
    if (hoveredCity) {
      const city = cities.find(c => c.city_banana === hoveredCity);
      if (city) onCityClick(city);
    }
  }
  
  function updateHover() {
    // Transform mouse position to map coordinates
    const x = (mousePos.x - transform.x) / transform.k;
    const y = (mousePos.y - transform.y) / transform.k;
    
    let foundCity = null;
    
    // Check each city
    cities.forEach(city => {
      if (!city.bounds) return;
      
      const [west, south, east, north] = city.bounds;
      const sw = projection([west, south]);
      const ne = projection([east, north]);
      
      if (!sw || !ne) return;
      
      if (x >= sw[0] && x <= ne[0] && y >= ne[1] && y <= sw[1]) {
        foundCity = city.city_banana;
      }
    });
    
    if (foundCity !== hoveredCity) {
      hoveredCity = foundCity;
      canvas.style.cursor = hoveredCity ? 'pointer' : (isDragging ? 'grabbing' : 'grab');
      render();
    }
  }
  
  function setupCanvas() {
    const rect = container.getBoundingClientRect();
    width = rect.width || 960;
    height = rect.height || 600;
    
    console.log('Setting up canvas, dimensions:', width, height);
    
    // Handle retina displays
    dpr = window.devicePixelRatio || 1;
    
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = width + 'px';
    canvas.style.height = height + 'px';
    
    ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    
    console.log('Canvas context created:', !!ctx);
    
    // Draw immediate test
    ctx.fillStyle = 'blue';
    ctx.fillRect(0, 0, 100, 100);
    
    if (projection) {
      projection.translate([width / 2, height / 2]);
      render();
    }
  }
  
  onMount(() => {
    setupCanvas();
    loadMapData();
    
    window.addEventListener('resize', setupCanvas);
  });
  
  onDestroy(() => {
    window.removeEventListener('resize', setupCanvas);
    if (animationFrame) cancelAnimationFrame(animationFrame);
  });
</script>

<div class="map-container" bind:this={container}>
  <canvas
    bind:this={canvas}
    on:wheel={handleWheel}
    on:mousedown={handleMouseDown}
    on:mousemove={handleMouseMove}
    on:mouseup={handleMouseUp}
    on:mouseleave={handleMouseUp}
    on:click={handleClick}
  />
  
  {#if hoveredCity}
    {@const city = cities.find(c => c.city_banana === hoveredCity)}
    {#if city}
      <div class="tooltip">
        <div class="city-name">{city.name}, {city.state}</div>
        <div class="meeting-count">{city.meetingCount} meetings</div>
        <div class="zipcode-count">{city.zipcodeCount || 1} zipcodes</div>
      </div>
    {/if}
  {/if}
</div>

<style>
  .map-container {
    position: relative;
    width: 100%;
    height: 700px; /* Fixed height instead of 100vh */
    background: #f0f0f0;
    overflow: hidden;
    border: 2px solid red; /* Debug border */
  }
  
  canvas {
    display: block;
    cursor: grab;
    background: white;
    border: 2px solid blue; /* Debug border */
  }
  
  .tooltip {
    position: absolute;
    top: 20px;
    right: 20px;
    background: white;
    border: 2px solid black;
    padding: 16px;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    pointer-events: none;
    min-width: 200px;
  }
  
  .city-name {
    font-size: 16px;
    font-weight: 600;
    margin-bottom: 8px;
  }
  
  .meeting-count {
    font-size: 14px;
    margin-bottom: 4px;
  }
  
  .zipcode-count {
    font-size: 12px;
    color: #666;
  }
</style>