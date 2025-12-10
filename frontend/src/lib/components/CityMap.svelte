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

	// Map initialization effect
	$effect(() => {
		if (!mapContainer) return;

		// Register PMTiles protocol
		const protocol = new Protocol();
		maplibregl.addProtocol('pmtiles', protocol.tile);

		// Create map
		const mapInstance = new maplibregl.Map({
			container: mapContainer,
			style: {
				version: 8,
				glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
				sources: {
					cities: {
						type: 'vector',
						url: `pmtiles://${tilesUrl}`
					}
				},
				layers: [
					{
						id: 'background',
						type: 'background',
						paint: {
							'background-color': 'var(--surface-secondary, #f8fafc)'
						}
					},
					// Cities without data - gray, less prominent
					{
						id: 'city-fill-inactive',
						type: 'fill',
						source: 'cities',
						'source-layer': 'cities',
						filter: ['==', ['get', 'has_data'], false],
						paint: {
							'fill-color': 'var(--border-primary, #e2e8f0)',
							'fill-opacity': 0.4
						}
					},
					// Cities with data - blue, prominent
					{
						id: 'city-fill-active',
						type: 'fill',
						source: 'cities',
						'source-layer': 'cities',
						filter: ['==', ['get', 'has_data'], true],
						paint: {
							'fill-color': 'var(--civic-blue, #4f46e5)',
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
					// Cities with summaries - even more prominent
					{
						id: 'city-fill-summarized',
						type: 'fill',
						source: 'cities',
						'source-layer': 'cities',
						filter: ['==', ['get', 'has_summaries'], true],
						paint: {
							'fill-color': 'var(--civic-green, #10b981)',
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
					// City outlines
					{
						id: 'city-outline',
						type: 'line',
						source: 'cities',
						'source-layer': 'cities',
						paint: {
							'line-color': [
								'case',
								['==', ['get', 'has_summaries'], true],
								'var(--civic-green, #10b981)',
								['==', ['get', 'has_data'], true],
								'var(--civic-blue, #4f46e5)',
								'var(--civic-gray, #475569)'
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
					// Hover highlight
					{
						id: 'city-hover',
						type: 'fill',
						source: 'cities',
						'source-layer': 'cities',
						filter: ['==', ['get', 'banana'], ''],
						paint: {
							'fill-color': 'var(--civic-accent, #8b5cf6)',
							'fill-opacity': 0.5
						}
					}
				]
			},
			center: [-98.5, 39.8],  // Center of contiguous US
			zoom: 4,
			maxBounds: [[-130, 24], [-65, 50]],  // Restrict to US
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
				// Update hover filter
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

		map = mapInstance;

		// Teardown
		return () => {
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
