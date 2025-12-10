<script lang="ts">
	import { goto } from '$app/navigation';
	import { Protocol } from 'pmtiles';
	import maplibregl from 'maplibre-gl';
	import 'maplibre-gl/dist/maplibre-gl.css';

	interface Props {
		tilesUrl?: string;
	}

	let { tilesUrl = '/tiles/cities.pmtiles' }: Props = $props();

	let mapContainer: HTMLDivElement;
	let map: maplibregl.Map | null = $state(null);
	let hoveredCity: { name: string; state: string; meeting_count: number } | null = $state(null);

	// Theme color palettes - MapLibre requires actual hex values, not CSS vars
	const themes = {
		light: {
			background: '#f8fafc',
			inactive: '#e2e8f0',
			inactiveOutline: '#475569',
			active: '#4f46e5',
			summarized: '#10b981',
			hover: '#8b5cf6',
			stateBorder: '#cbd5e1',
			countryFill: '#f1f5f9'
		},
		dark: {
			background: '#1e293b',
			inactive: '#334155',
			inactiveOutline: '#64748b',
			active: '#4f46e5',
			summarized: '#10b981',
			hover: '#8b5cf6',
			stateBorder: '#475569',
			countryFill: '#0f172a'
		}
	};

	function getTheme(): 'light' | 'dark' {
		if (typeof document === 'undefined') return 'light';
		return document.documentElement.classList.contains('dark') ? 'dark' : 'light';
	}

	function buildStyle(colors: typeof themes.light): maplibregl.StyleSpecification {
		return {
			version: 8,
			glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
			sources: {
				cities: {
					type: 'vector',
					url: `pmtiles://${tilesUrl}`
				},
				// US state boundaries (public domain, ~80KB)
				states: {
					type: 'geojson',
					data: 'https://raw.githubusercontent.com/PublicaMundi/MappingAPI/master/data/geojson/us-states.json'
				}
			},
			layers: [
				{
					id: 'background',
					type: 'background',
					paint: {
						'background-color': colors.countryFill
					}
				},
				// US states fill (gives the country shape)
				{
					id: 'states-fill',
					type: 'fill',
					source: 'states',
					paint: {
						'fill-color': colors.background,
						'fill-opacity': 1
					}
				},
				// State boundaries
				{
					id: 'state-borders',
					type: 'line',
					source: 'states',
					paint: {
						'line-color': colors.stateBorder,
						'line-width': 1,
						'line-opacity': 0.4
					}
				},
				{
					id: 'city-fill-inactive',
					type: 'fill',
					source: 'cities',
					'source-layer': 'cities',
					filter: ['==', ['get', 'has_data'], false],
					paint: {
						'fill-color': colors.inactive,
						'fill-opacity': 0.4
					}
				},
				{
					id: 'city-fill-active',
					type: 'fill',
					source: 'cities',
					'source-layer': 'cities',
					filter: ['==', ['get', 'has_data'], true],
					paint: {
						'fill-color': colors.active,
						'fill-opacity': [
							'interpolate',
							['linear'],
							['get', 'meeting_count'],
							0, 0.3,
							50, 0.5,
							200, 0.7
						]
					}
				},
				{
					id: 'city-fill-summarized',
					type: 'fill',
					source: 'cities',
					'source-layer': 'cities',
					filter: ['==', ['get', 'has_summaries'], true],
					paint: {
						'fill-color': colors.summarized,
						'fill-opacity': [
							'interpolate',
							['linear'],
							['get', 'summarized_count'],
							0, 0.4,
							20, 0.6,
							100, 0.8
						]
					}
				},
				{
					id: 'city-outline',
					type: 'line',
					source: 'cities',
					'source-layer': 'cities',
					paint: {
						'line-color': [
							'case',
							['==', ['get', 'has_summaries'], true],
							colors.summarized,
							['==', ['get', 'has_data'], true],
							colors.active,
							colors.inactiveOutline
						],
						'line-width': [
							'interpolate',
							['linear'],
							['zoom'],
							3, 0.3,
							8, 1,
							12, 2
						],
						'line-opacity': 0.6
					}
				},
				{
					id: 'city-hover',
					type: 'fill',
					source: 'cities',
					'source-layer': 'cities',
					filter: ['==', ['get', 'banana'], ''],
					paint: {
						'fill-color': colors.hover,
						'fill-opacity': 0.5
					}
				}
			]
		};
	}

	// Update layer paint properties when theme changes
	function applyTheme(mapInstance: maplibregl.Map, colors: typeof themes.light) {
		mapInstance.setPaintProperty('background', 'background-color', colors.countryFill);
		mapInstance.setPaintProperty('states-fill', 'fill-color', colors.background);
		mapInstance.setPaintProperty('state-borders', 'line-color', colors.stateBorder);
		mapInstance.setPaintProperty('city-fill-inactive', 'fill-color', colors.inactive);
		mapInstance.setPaintProperty('city-fill-active', 'fill-color', colors.active);
		mapInstance.setPaintProperty('city-fill-summarized', 'fill-color', colors.summarized);
		mapInstance.setPaintProperty('city-hover', 'fill-color', colors.hover);
		mapInstance.setPaintProperty('city-outline', 'line-color', [
			'case',
			['==', ['get', 'has_summaries'], true],
			colors.summarized,
			['==', ['get', 'has_data'], true],
			colors.active,
			colors.inactiveOutline
		]);
	}

	// Map initialization effect
	$effect(() => {
		if (!mapContainer) return;

		// Register PMTiles protocol
		const protocol = new Protocol();
		maplibregl.addProtocol('pmtiles', protocol.tile);

		// Get initial theme and build style
		const initialTheme = getTheme();
		const initialColors = themes[initialTheme];

		// Create map with theme-aware style
		const mapInstance = new maplibregl.Map({
			container: mapContainer,
			style: buildStyle(initialColors),
			center: [-98.5, 39.8],
			zoom: 4,
			maxBounds: [[-130, 24], [-65, 50]],
			minZoom: 3,
			maxZoom: 12
		});

		// Navigation controls
		mapInstance.addControl(new maplibregl.NavigationControl(), 'top-right');

		// Click to navigate to city page
		mapInstance.on('click', 'city-fill-active', (e) => {
			if (e.features && e.features[0]) {
				const banana = e.features[0].properties?.banana;
				if (banana) {
					goto(`/${banana}`);
				}
			}
		});

		mapInstance.on('click', 'city-fill-summarized', (e) => {
			if (e.features && e.features[0]) {
				const banana = e.features[0].properties?.banana;
				if (banana) {
					goto(`/${banana}`);
				}
			}
		});

		// Hover effects
		mapInstance.on('mouseenter', 'city-fill-active', (e) => {
			mapInstance.getCanvas().style.cursor = 'pointer';
			if (e.features && e.features[0]) {
				const props = e.features[0].properties;
				hoveredCity = {
					name: props?.name || 'Unknown',
					state: props?.state || '',
					meeting_count: props?.meeting_count || 0
				};
				mapInstance.setFilter('city-hover', ['==', ['get', 'banana'], props?.banana || '']);
			}
		});

		mapInstance.on('mouseenter', 'city-fill-summarized', (e) => {
			mapInstance.getCanvas().style.cursor = 'pointer';
			if (e.features && e.features[0]) {
				const props = e.features[0].properties;
				hoveredCity = {
					name: props?.name || 'Unknown',
					state: props?.state || '',
					meeting_count: props?.meeting_count || 0
				};
				mapInstance.setFilter('city-hover', ['==', ['get', 'banana'], props?.banana || '']);
			}
		});

		mapInstance.on('mouseleave', 'city-fill-active', () => {
			mapInstance.getCanvas().style.cursor = '';
			hoveredCity = null;
			mapInstance.setFilter('city-hover', ['==', ['get', 'banana'], '']);
		});

		mapInstance.on('mouseleave', 'city-fill-summarized', () => {
			mapInstance.getCanvas().style.cursor = '';
			hoveredCity = null;
			mapInstance.setFilter('city-hover', ['==', ['get', 'banana'], '']);
		});

		// Watch for theme changes via MutationObserver on <html> element
		let currentTheme = initialTheme;
		const observer = new MutationObserver(() => {
			const newTheme = getTheme();
			if (newTheme !== currentTheme) {
				currentTheme = newTheme;
				applyTheme(mapInstance, themes[newTheme]);
			}
		});

		observer.observe(document.documentElement, {
			attributes: true,
			attributeFilter: ['class']
		});

		map = mapInstance;

		// Teardown
		return () => {
			observer.disconnect();
			mapInstance.remove();
			maplibregl.removeProtocol('pmtiles');
		};
	});
</script>

<div class="map-wrapper">
	<div bind:this={mapContainer} class="map-container"></div>

	{#if hoveredCity}
		<div class="tooltip">
			<div class="tooltip-city">{hoveredCity.name}, {hoveredCity.state}</div>
			<div class="tooltip-stats">{hoveredCity.meeting_count} meetings</div>
		</div>
	{/if}

	<div class="legend">
		<div class="legend-title">Coverage</div>
		<div class="legend-item">
			<span class="legend-swatch legend-summarized"></span>
			<span>With AI summaries</span>
		</div>
		<div class="legend-item">
			<span class="legend-swatch legend-active"></span>
			<span>Meeting data</span>
		</div>
		<div class="legend-item">
			<span class="legend-swatch legend-inactive"></span>
			<span>Boundary only</span>
		</div>
	</div>
</div>

<style>
	.map-wrapper {
		position: relative;
		width: 100%;
		height: 100%;
	}

	.map-container {
		width: 100%;
		height: 100%;
		background: var(--surface-secondary);
		border-radius: var(--radius-lg);
		overflow: hidden;
	}

	.tooltip {
		position: absolute;
		top: var(--space-md);
		left: var(--space-md);
		background: var(--surface-primary);
		border: 1px solid var(--border-primary);
		border-radius: var(--radius-md);
		padding: var(--space-sm) var(--space-md);
		box-shadow: 0 2px 8px var(--shadow-md);
		pointer-events: none;
		z-index: 10;
	}

	.tooltip-city {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--text-primary);
	}

	.tooltip-stats {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		color: var(--text-secondary);
		margin-top: 0.25rem;
	}

	.legend {
		position: absolute;
		bottom: var(--space-md);
		left: var(--space-md);
		background: var(--surface-primary);
		border: 1px solid var(--border-primary);
		border-radius: var(--radius-md);
		padding: var(--space-sm) var(--space-md);
		box-shadow: 0 2px 8px var(--shadow-md);
		z-index: 10;
	}

	.legend-title {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--text-primary);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin-bottom: var(--space-xs);
	}

	.legend-item {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
		font-family: system-ui, -apple-system, sans-serif;
		font-size: 0.8rem;
		color: var(--text-secondary);
		margin-top: 0.25rem;
	}

	.legend-swatch {
		display: inline-block;
		width: 12px;
		height: 12px;
		border-radius: 2px;
	}

	.legend-summarized {
		background: var(--civic-green);
		opacity: 0.7;
	}

	.legend-active {
		background: var(--civic-blue);
		opacity: 0.5;
	}

	.legend-inactive {
		background: var(--border-primary);
		opacity: 0.4;
	}

	/* MapLibre overrides for dark mode */
	:global(.maplibregl-ctrl-group) {
		background: var(--surface-primary) !important;
		border: 1px solid var(--border-primary) !important;
	}

	:global(.maplibregl-ctrl-group button) {
		background-color: var(--surface-primary) !important;
	}

	:global(.maplibregl-ctrl-group button + button) {
		border-top: 1px solid var(--border-primary) !important;
	}

	:global(.maplibregl-ctrl button:not(:disabled):hover) {
		background-color: var(--surface-hover) !important;
	}
</style>
