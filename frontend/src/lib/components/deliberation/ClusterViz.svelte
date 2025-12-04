<script lang="ts">
	import type { ClusterResults } from '$lib/api/deliberation';

	interface Props {
		results: ClusterResults;
		width?: number;
		height?: number;
	}

	let { results, width = 300, height = 200 }: Props = $props();

	const clusterColors = ['#3b82f6', '#ef4444', '#22c55e', '#f59e0b', '#8b5cf6'];
	const padding = 20;

	const bounds = $derived.by(() => {
		if (!results.positions?.length) return null;
		const xs = results.positions.map((p) => p[0]);
		const ys = results.positions.map((p) => p[1]);
		return {
			minX: Math.min(...xs),
			maxX: Math.max(...xs),
			minY: Math.min(...ys),
			maxY: Math.max(...ys),
			innerWidth: width - padding * 2,
			innerHeight: height - padding * 2
		};
	});

	function normalize(x: number, y: number) {
		if (!bounds) return { x: 0, y: 0 };
		const rangeX = bounds.maxX - bounds.minX || 1;
		const rangeY = bounds.maxY - bounds.minY || 1;
		return {
			x: padding + ((x - bounds.minX) / rangeX) * bounds.innerWidth,
			y: padding + ((y - bounds.minY) / rangeY) * bounds.innerHeight
		};
	}

	const normalizedPositions = $derived(
		bounds ? results.positions.map((p) => normalize(p[0], p[1])) : []
	);

	const clusterAssignments = $derived(
		results.clusters ? Object.values(results.clusters) : []
	);

	const normalizedCenters = $derived(
		bounds && results.cluster_centers?.length
			? results.cluster_centers.map((c, i) => ({
					...normalize(c[0], c[1]),
					color: clusterColors[i % clusterColors.length]
				}))
			: []
	);
</script>

<div class="cluster-viz">
	<svg {width} {height} viewBox="0 0 {width} {height}">
		<rect x="0" y="0" {width} {height} fill="var(--bg-secondary, #f5f5f5)" rx="4" />

		<line
			x1={width / 2}
			y1={padding}
			x2={width / 2}
			y2={height - padding}
			stroke="var(--border-primary, #ddd)"
			stroke-dasharray="4,4"
		/>
		<line
			x1={padding}
			y1={height / 2}
			x2={width - padding}
			y2={height / 2}
			stroke="var(--border-primary, #ddd)"
			stroke-dasharray="4,4"
		/>

		{#each normalizedCenters as center, i (i)}
			<circle
				cx={center.x}
				cy={center.y}
				r="12"
				fill="none"
				stroke={center.color}
				stroke-width="2"
				opacity="0.5"
			/>
		{/each}

		{#each normalizedPositions as pos, i (i)}
			<circle
				cx={pos.x}
				cy={pos.y}
				r="4"
				fill={clusterColors[clusterAssignments[i] % clusterColors.length]}
				opacity="0.8"
			/>
		{/each}
	</svg>

	<div class="legend">
		{#each Array(results.k) as _, i (i)}
			<div class="legend-item">
				<span class="legend-dot" style="background: {clusterColors[i]}"></span>
				<span class="legend-label">Group {i + 1}</span>
			</div>
		{/each}
	</div>

	<p class="viz-caption">
		{results.n_participants} participants in {results.k} opinion groups
	</p>
</div>

<style>
	.cluster-viz {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.5rem;
	}

	svg {
		border-radius: 4px;
	}

	.legend {
		display: flex;
		gap: 1rem;
		flex-wrap: wrap;
		justify-content: center;
	}

	.legend-item {
		display: flex;
		align-items: center;
		gap: 0.35rem;
	}

	.legend-dot {
		width: 10px;
		height: 10px;
		border-radius: 50%;
	}

	.legend-label {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.7rem;
		color: var(--text-secondary, #6b7280);
	}

	.viz-caption {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.7rem;
		color: var(--civic-gray, #9ca3af);
		margin: 0;
		text-align: center;
	}
</style>
