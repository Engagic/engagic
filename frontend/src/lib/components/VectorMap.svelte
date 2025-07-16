<script>
  import { onMount, onDestroy } from 'svelte';
  import { geoPath, geoAlbersUsa } from 'd3-geo';
  import { US_STATES_GEOJSON } from '../USGeometry.js';
  
  export let cities = [];
  export let onCityClick = () => {};
  
  let container;
  let svg;
  let g; // Transform group
  
  // Dimensions
  let width = 1000;
  let height = 600;
  
  // Projection and path generator
  let projection;
  let pathGenerator;
  
  // Transform state
  let transform = { k: 1, x: 0, y: 0 };
  
  // Interaction state
  let isDragging = false;
  let dragStart = { x: 0, y: 0, transform: null };
  let hoveredCity = null;
  
  $: if (svg && cities.length > 0) {
    drawCities();
  }
  
  function initializeMap() {
    // Set up projection
    projection = geoAlbersUsa()
      .scale(1300)
      .translate([width / 2, height / 2]);
    
    pathGenerator = geoPath().projection(projection);
    
    // Create SVG structure
    svg = container.querySelector('svg');
    g = svg.querySelector('g');
    
    // Draw US outline
    drawUSOutline();
  }
  
  function drawUSOutline() {
    const usPath = g.querySelector('.us-outline');
    usPath.setAttribute('d', pathGenerator(US_STATES_GEOJSON));
  }
  
  function drawCities() {
    const citiesGroup = g.querySelector('.cities');
    
    // Clear existing cities
    citiesGroup.innerHTML = '';
    
    cities.forEach(city => {
      if (!city.bounds) return;
      
      const [west, south, east, north] = city.bounds;
      
      // Project the bounds
      const sw = projection([west, south]);
      const ne = projection([east, north]);
      
      if (!sw || !ne) return; // Skip if outside projection
      
      const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      rect.setAttribute('x', sw[0]);
      rect.setAttribute('y', ne[1]);
      rect.setAttribute('width', ne[0] - sw[0]);
      rect.setAttribute('height', sw[1] - ne[1]);
      rect.setAttribute('class', 'city-coverage');
      rect.setAttribute('data-city', city.city_banana);
      
      // Add hover listeners
      rect.addEventListener('mouseenter', () => {
        hoveredCity = city;
        rect.classList.add('hovered');
      });
      
      rect.addEventListener('mouseleave', () => {
        hoveredCity = null;
        rect.classList.remove('hovered');
      });
      
      rect.addEventListener('click', () => {
        onCityClick(city);
      });
      
      citiesGroup.appendChild(rect);
    });
  }
  
  // Pan and zoom handlers
  function handleWheel(e) {
    e.preventDefault();
    
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    const point = { x: e.offsetX, y: e.offsetY };
    
    // Calculate new transform
    const newK = transform.k * delta;
    if (newK < 0.5 || newK > 5) return;
    
    // Zoom around mouse position
    transform.x = point.x - (point.x - transform.x) * delta;
    transform.y = point.y - (point.y - transform.y) * delta;
    transform.k = newK;
    
    applyTransform();
  }
  
  function handleMouseDown(e) {
    isDragging = true;
    dragStart = {
      x: e.clientX,
      y: e.clientY,
      transform: { ...transform }
    };
  }
  
  function handleMouseMove(e) {
    if (!isDragging) return;
    
    transform.x = dragStart.transform.x + (e.clientX - dragStart.x);
    transform.y = dragStart.transform.y + (e.clientY - dragStart.y);
    
    applyTransform();
  }
  
  function handleMouseUp() {
    isDragging = false;
  }
  
  function applyTransform() {
    g.style.transform = `translate(${transform.x}px, ${transform.y}px) scale(${transform.k})`;
  }
  
  function handleResize() {
    const rect = container.getBoundingClientRect();
    width = rect.width;
    height = rect.height;
    
    if (projection) {
      projection.translate([width / 2, height / 2]);
      drawUSOutline();
      drawCities();
    }
  }
  
  onMount(() => {
    initializeMap();
    handleResize();
    
    window.addEventListener('resize', handleResize);
  });
  
  onDestroy(() => {
    window.removeEventListener('resize', handleResize);
  });
</script>

<div class="map-container" bind:this={container}>
  <svg
    {width}
    {height}
    on:wheel={handleWheel}
    on:mousedown={handleMouseDown}
    on:mousemove={handleMouseMove}
    on:mouseup={handleMouseUp}
    on:mouseleave={handleMouseUp}
  >
    <rect width="100%" height="100%" fill="white" />
    
    <g>
      <!-- US Outline -->
      <path class="us-outline" />
      
      <!-- Cities -->
      <g class="cities"></g>
    </g>
  </svg>
  
  {#if hoveredCity}
    <div class="tooltip">
      <strong>{hoveredCity.name}, {hoveredCity.state}</strong><br>
      {hoveredCity.meetingCount} meetings available<br>
      <span class="zipcode-count">{hoveredCity.zipcodeCount || 1} zipcodes</span>
    </div>
  {/if}
</div>

<style>
  .map-container {
    width: 100%;
    height: 700px;
    position: relative;
    background: white;
    overflow: hidden;
    cursor: grab;
  }
  
  .map-container:active {
    cursor: grabbing;
  }
  
  svg {
    display: block;
    width: 100%;
    height: 100%;
  }
  
  :global(.us-outline) {
    fill: none;
    stroke: black;
    stroke-width: 2px;
    vector-effect: non-scaling-stroke;
  }
  
  :global(.city-coverage) {
    fill: rgba(0, 0, 0, 0.6);
    stroke: black;
    stroke-width: 1px;
    vector-effect: non-scaling-stroke;
    cursor: pointer;
    transition: fill 0.2s ease;
  }
  
  :global(.city-coverage.hovered) {
    fill: rgba(0, 0, 0, 0.8);
  }
  
  .tooltip {
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
  
  .zipcode-count {
    font-size: 12px;
    color: #666;
  }
</style>