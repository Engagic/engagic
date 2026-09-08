<script lang="ts">
	import { onMount } from 'svelte';
	import {
		ATLAS_EDGES,
		ATLAS_NODES,
		NODE_BY_ID,
		WORLD,
		nodeTrail,
		type AtlasEdge,
		type AtlasNode
	} from '$lib/atlas/engagic';

	let viewport: HTMLDivElement;
	let width = $state(0);
	let height = $state(0);
	let fitScale = $state(1);
	let scale = $state(1);
	let offsetX = $state(0);
	let offsetY = $state(0);
	let ready = $state(false);
	let focusedId = $state('engagic');
	let pointerCount = $state(0);
	let dragged = false;
	let animationFrame: number | null = null;
	let wheelFrame: number | null = null;
	let pendingWheelDelta = 0;
	let pendingWheelPoint = { x: 0, y: 0 };

	const pointers = new Map<number, { x: number; y: number }>();
	let panStart = { x: 0, y: 0, offsetX: 0, offsetY: 0 };
	let pinchStart = { distance: 0, scale: 1, worldX: 0, worldY: 0 };

	const MIN_RATIO = 0.82;
	const MAX_RATIO = 14;
	const REGION_REVEAL = 1.22;
	const COMPONENT_REVEAL = 1.95;
	const DETAIL_REVEAL = 4.3;
	const zoomRatio = $derived(scale / fitScale);
	const zoomPercent = $derived(Math.round(zoomRatio * 100));
	const level = $derived(
		zoomRatio < REGION_REVEAL ? 'SYSTEM' : zoomRatio < COMPONENT_REVEAL ? 'REGIONS' : zoomRatio < DETAIL_REVEAL ? 'COMPONENTS' : 'CODE'
	);
	const focusedNode = $derived(NODE_BY_ID.get(focusedId) ?? ATLAS_NODES[0]);
	const trail = $derived(nodeTrail(focusedNode.id));
	const renderedNodes = $derived.by(() => {
		const padding = 160 / Math.max(scale, 0.001);
		const left = -offsetX / scale - padding;
		const top = -offsetY / scale - padding;
		const right = (width - offsetX) / scale + padding;
		const bottom = (height - offsetY) / scale + padding;
		return ATLAS_NODES.filter((node) => {
			const semanticallyActive =
				node.depth === 0
					? zoomRatio < REGION_REVEAL + 0.12
					: node.depth === 1
						? zoomRatio >= REGION_REVEAL - 0.1
						: zoomRatio >= COMPONENT_REVEAL - 0.1;
			return semanticallyActive && node.x + node.w >= left && node.x <= right && node.y + node.h >= top && node.y <= bottom;
		});
	});
	const renderedNodeIds = $derived.by(() => new Set(renderedNodes.map((node) => node.id)));
	const renderedEdges = $derived.by(() => ATLAS_EDGES.filter((edge) => {
		const isRegionFlow = edge.reveal < 2;
		if (isRegionFlow) {
			return zoomRatio >= REGION_REVEAL - 0.1 && zoomRatio < COMPONENT_REVEAL + 0.35 &&
				renderedNodeIds.has(edge.from) && renderedNodeIds.has(edge.to);
		}
		if (zoomRatio < COMPONENT_REVEAL - 0.1 || !renderedNodeIds.has(edge.from) || !renderedNodeIds.has(edge.to)) return false;
		if (focusedNode.depth === 2) return edge.from === focusedNode.id || edge.to === focusedNode.id;
		if (focusedNode.depth === 1) {
			const from = NODE_BY_ID.get(edge.from);
			const to = NODE_BY_ID.get(edge.to);
			return from?.parent === focusedNode.id || to?.parent === focusedNode.id;
		}
		return true;
	}));

	const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));
	const screen = (pixels: number) => pixels / Math.max(scale, 0.001);

	function localPoint(event: PointerEvent | WheelEvent) {
		const rect = viewport.getBoundingClientRect();
		return { x: event.clientX - rect.left, y: event.clientY - rect.top };
	}

	function cancelCameraAnimation() {
		if (animationFrame !== null) cancelAnimationFrame(animationFrame);
		animationFrame = null;
	}

	function setZoomAt(nextScale: number, x: number, y: number) {
		const bounded = clamp(nextScale, fitScale * MIN_RATIO, fitScale * MAX_RATIO);
		const worldX = (x - offsetX) / scale;
		const worldY = (y - offsetY) / scale;
		offsetX = x - worldX * bounded;
		offsetY = y - worldY * bounded;
		scale = bounded;
	}

	function handleWheel(event: WheelEvent) {
		event.preventDefault();
		cancelCameraAnimation();
		const delta = event.deltaMode === 1 ? event.deltaY * 16 : event.deltaY;
		pendingWheelDelta += delta;
		pendingWheelPoint = localPoint(event);
		if (wheelFrame !== null) return;
		wheelFrame = requestAnimationFrame(() => {
			const factor = clamp(Math.exp(-pendingWheelDelta * 0.0015), 0.76, 1.32);
			setZoomAt(scale * factor, pendingWheelPoint.x, pendingWheelPoint.y);
			pendingWheelDelta = 0;
			wheelFrame = null;
		});
	}

	function beginPointer(event: PointerEvent) {
		cancelCameraAnimation();
		const point = localPoint(event);
		pointers.set(event.pointerId, point);
		pointerCount = pointers.size;
		dragged = false;
		if (pointers.size === 1) {
			panStart = { ...point, offsetX, offsetY };
		} else if (pointers.size === 2) {
			for (const pointerId of pointers.keys()) {
				if (!viewport.hasPointerCapture(pointerId)) viewport.setPointerCapture(pointerId);
			}
			const [a, b] = [...pointers.values()];
			const midpoint = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
			pinchStart = {
				distance: Math.hypot(a.x - b.x, a.y - b.y),
				scale,
				worldX: (midpoint.x - offsetX) / scale,
				worldY: (midpoint.y - offsetY) / scale
			};
		}
	}

	function movePointer(event: PointerEvent) {
		if (!pointers.has(event.pointerId)) return;
		const point = localPoint(event);
		pointers.set(event.pointerId, point);
		if (pointers.size === 1) {
			const dx = point.x - panStart.x;
			const dy = point.y - panStart.y;
			if (Math.hypot(dx, dy) > 3) {
				dragged = true;
				if (!viewport.hasPointerCapture(event.pointerId)) viewport.setPointerCapture(event.pointerId);
			}
			offsetX = panStart.offsetX + dx;
			offsetY = panStart.offsetY + dy;
			return;
		}
		if (pointers.size === 2) {
			dragged = true;
			const [a, b] = [...pointers.values()];
			const midpoint = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
			const distance = Math.hypot(a.x - b.x, a.y - b.y);
			const nextScale = clamp(
				pinchStart.scale * (distance / Math.max(pinchStart.distance, 1)),
				fitScale * MIN_RATIO,
				fitScale * MAX_RATIO
			);
			scale = nextScale;
			offsetX = midpoint.x - pinchStart.worldX * nextScale;
			offsetY = midpoint.y - pinchStart.worldY * nextScale;
		}
	}

	function endPointer(event: PointerEvent) {
		pointers.delete(event.pointerId);
		pointerCount = pointers.size;
		if (viewport.hasPointerCapture(event.pointerId)) viewport.releasePointerCapture(event.pointerId);
		if (pointers.size === 1) {
			const [remaining] = [...pointers.values()];
			panStart = { ...remaining, offsetX, offsetY };
		}
	}

	function animateCamera(targetScale: number, targetX: number, targetY: number) {
		cancelCameraAnimation();
		const startScale = scale;
		const startX = offsetX;
		const startY = offsetY;
		const start = performance.now();
		const duration = 520;
		const tick = (now: number) => {
			const raw = clamp((now - start) / duration, 0, 1);
			const eased = 1 - Math.pow(1 - raw, 4);
			scale = startScale + (targetScale - startScale) * eased;
			offsetX = startX + (targetX - startX) * eased;
			offsetY = startY + (targetY - startY) * eased;
			if (raw < 1) animationFrame = requestAnimationFrame(tick);
			else animationFrame = null;
		};
		animationFrame = requestAnimationFrame(tick);
	}

	function focus(node: AtlasNode) {
		if (dragged) return;
		if (node.depth === 0) {
			reset();
			return;
		}
		focusedId = node.id;
		const padding = 100;
		const fit = Math.min(width / (node.w + padding), height / (node.h + padding));
		const minimumRatio = node.depth === 1 ? COMPONENT_REVEAL + 0.2 : DETAIL_REVEAL + 0.45;
		const detailContentScale = node.depth === 2 && node.details
			? (105 + node.details.length * 20) / (node.h * 0.9)
			: 0;
		const targetScale = clamp(Math.max(fit, fitScale * minimumRatio, detailContentScale), fitScale * MIN_RATIO, fitScale * MAX_RATIO);
		const centerX = node.x + node.w / 2;
		const centerY = node.y + node.h / 2;
		animateCamera(targetScale, width / 2 - centerX * targetScale, height / 2 - centerY * targetScale);
	}

	function reset() {
		focusedId = 'engagic';
		const targetX = (width - WORLD.width * fitScale) / 2;
		const targetY = (height - WORLD.height * fitScale) / 2;
		animateCamera(fitScale, targetX, targetY);
	}

	function zoomButton(factor: number) {
		cancelCameraAnimation();
		setZoomAt(scale * factor, width / 2, height / 2);
	}

	function keydown(event: KeyboardEvent) {
		if (event.key === '+' || event.key === '=') {
			event.preventDefault();
			zoomButton(1.35);
		} else if (event.key === '-' || event.key === '_') {
			event.preventDefault();
			zoomButton(1 / 1.35);
		} else if (event.key === '0' || event.key === 'Home') {
			event.preventDefault();
			reset();
		}
	}

	function nodeOpacity(node: AtlasNode) {
		if (node.depth === 0) return clamp(1 - (zoomRatio - 1) * 4.5, 0, 1);
		const reveal = node.depth === 1 ? REGION_REVEAL : COMPONENT_REVEAL;
		return clamp((zoomRatio - reveal + 0.1) * 3.4, 0, 1);
	}

	function edgeOpacity(edge: AtlasEdge) {
		const isRegionFlow = edge.reveal < 2;
		const reveal = isRegionFlow ? REGION_REVEAL : COMPONENT_REVEAL;
		const enter = clamp((zoomRatio - reveal + 0.1) * 3, 0, 1);
		if (!isRegionFlow) return enter;
		return enter * clamp((COMPONENT_REVEAL + 0.35 - zoomRatio) / 0.35, 0, 1);
	}

	function rootTitleOpacity() {
		return clamp(1 - (zoomRatio - 1) * 4.8, 0, 1);
	}

	function regionDescriptionOpacity(node: AtlasNode) {
		if (node.depth !== 1 || focusedId !== node.id) return 0;
		return clamp((zoomRatio - REGION_REVEAL) * 2.2, 0, 0.82);
	}

	function edgePath(edge: AtlasEdge) {
		const from = NODE_BY_ID.get(edge.from)!;
		const to = NODE_BY_ID.get(edge.to)!;
		const fromX = from.x + from.w / 2;
		const fromY = from.y + from.h / 2;
		const toX = to.x + to.w / 2;
		const toY = to.y + to.h / 2;
		const dx = toX - fromX;
		const dy = toY - fromY;
		const distance = Math.max(Math.hypot(dx, dy), 1);
		const ux = dx / distance;
		const uy = dy / distance;
		const fromRadius = Math.min(from.w, from.h) / 2;
		const toRadius = Math.min(to.w, to.h) / 2;
		return `M ${fromX + ux * fromRadius} ${fromY + uy * fromRadius} L ${toX - ux * toRadius} ${toY - uy * toRadius}`;
	}

	function labelLines(label: string, maxCharacters: number) {
		const words = label.split(' ');
		const lines: string[] = [];
		for (const word of words) {
			const current = lines[lines.length - 1];
			if (!current || current.length + word.length + 1 > maxCharacters) lines.push(word);
			else lines[lines.length - 1] = `${current} ${word}`;
		}
		if (lines.length <= 3) return lines;
		return [lines[0], lines[1], lines.slice(2).join(' ')];
	}

	function edgeLabelPoint(edge: AtlasEdge) {
		const from = NODE_BY_ID.get(edge.from)!;
		const to = NODE_BY_ID.get(edge.to)!;
		return {
			x: (from.x + from.w / 2 + to.x + to.w / 2) / 2,
			y: (from.y + from.h / 2 + to.y + to.h / 2) / 2
		};
	}

	onMount(() => {
		document.body.classList.add('atlas-open');
		const observer = new ResizeObserver(([entry]) => {
			const oldWidth = width;
			const oldHeight = height;
			const oldFit = fitScale;
			const oldRatio = ready ? scale / oldFit : 1;
			const worldCenter = ready
				? { x: (oldWidth / 2 - offsetX) / scale, y: (oldHeight / 2 - offsetY) / scale }
				: { x: WORLD.width / 2, y: WORLD.height / 2 };
			width = entry.contentRect.width;
			height = entry.contentRect.height;
			fitScale = Math.min((width - 64) / WORLD.width, (height - 64) / WORLD.height);
			scale = fitScale * oldRatio;
			offsetX = width / 2 - worldCenter.x * scale;
			offsetY = height / 2 - worldCenter.y * scale;
			ready = true;
		});
		observer.observe(viewport);
		viewport.addEventListener('wheel', handleWheel, { passive: false });
		return () => {
			document.body.classList.remove('atlas-open');
			observer.disconnect();
			viewport.removeEventListener('wheel', handleWheel);
			if (wheelFrame !== null) cancelAnimationFrame(wheelFrame);
			cancelCameraAnimation();
		};
	});
</script>

<svelte:head>
	<title>Engagic System Atlas</title>
	<meta name="description" content="A semantic-zoom map of the Engagic municipal record infrastructure." />
</svelte:head>

<svelte:window onkeydown={keydown} />

<div class="atlas-shell">
	<div
		class:dragging={pointerCount > 0}
		class="viewport"
		bind:this={viewport}
		role="application"
		aria-label="Interactive Engagic system atlas. Scroll to zoom, drag to pan, and select regions to enter them."
		onpointerdown={beginPointer}
		onpointermove={movePointer}
		onpointerup={endPointer}
		onpointercancel={endPointer}
	>
		<svg class:ready viewBox={`0 0 ${Math.max(width, 1)} ${Math.max(height, 1)}`} aria-hidden="true">
			<defs>
				<pattern id="minor-grid" width="28" height="28" patternUnits="userSpaceOnUse">
					<circle cx="1.5" cy="1.5" r="1.2" fill="var(--grid-minor)" />
				</pattern>
				<pattern id="major-grid" width="140" height="140" patternUnits="userSpaceOnUse">
					<rect width="140" height="140" fill="url(#minor-grid)" />
					<path d="M 140 0 L 0 0 0 140" fill="none" stroke="var(--grid-major)" stroke-width="1" />
				</pattern>
				{#each ['source', 'sync', 'process', 'store', 'serve'] as tone}
					<marker id={`arrow-${tone}`} markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto" markerUnits="strokeWidth">
						<path d="M 0 0 L 7 3.5 L 0 7 z" class={`marker tone-${tone}`} />
					</marker>
				{/each}
			</defs>
			<rect width={Math.max(width, 1)} height={Math.max(height, 1)} fill="url(#major-grid)" />

			<g transform={`matrix(${scale} 0 0 ${scale} ${offsetX} ${offsetY})`}>
				<!-- Only semantic nodes near the camera are mounted. -->
				{#each renderedNodes as node (node.id)}
					{@const opacity = nodeOpacity(node)}
					{#if opacity > 0}
						<circle
							cx={node.x + node.w / 2}
							cy={node.y + node.h / 2}
							r={Math.min(node.w, node.h) / 2}
							class={`node-box tone-${node.tone} depth-${node.depth}`}
							style={`opacity:${opacity}`}
						/>
					{/if}
				{/each}

				{#each renderedEdges as edge (edge.id)}
					{@const opacity = edgeOpacity(edge)}
					{#if opacity > 0}
						<path
							d={edgePath(edge)}
							class={`flow tone-${edge.tone}`}
							class:dashed={edge.dashed}
							style={`opacity:${opacity};stroke-width:${screen(edge.reveal < 2 ? 2.4 : 1.5)}`}
							stroke-dasharray={edge.dashed ? `${screen(8)} ${screen(7)}` : undefined}
							marker-end={`url(#arrow-${edge.tone})`}
						/>
						{#if edge.label && zoomRatio < 7}
							{@const point = edgeLabelPoint(edge)}
							<text
								x={point.x}
								y={point.y - screen(7)}
								class="edge-label"
								style={`font-size:${screen(9)}px;opacity:${opacity}`}
								text-anchor="middle"
							>{edge.label}</text>
						{/if}
					{/if}
				{/each}

				<!-- Root title is the entire first zoom level. -->
				<g class="root-title" style={`opacity:${rootTitleOpacity()}`}>
					<text x={WORLD.width / 2} y={WORLD.height / 2 - screen(26)} text-anchor="middle" style={`font-size:${screen(68)}px`}>
						ENGAGIC
					</text>
					<text class="root-kicker" x={WORLD.width / 2} y={WORLD.height / 2 + screen(20)} text-anchor="middle" style={`font-size:${screen(11)}px`}>
						MUNICIPAL RECORD INFRASTRUCTURE
					</text>
					<text class="root-description" x={WORLD.width / 2} y={WORLD.height / 2 + screen(52)} text-anchor="middle" style={`font-size:${screen(15)}px`}>
						discover · preserve · understand · publish
					</text>
				</g>

				{#each renderedNodes.filter((candidate) => candidate.depth > 0) as node (node.id)}
					{@const opacity = nodeOpacity(node)}
					{@const centerX = node.x + node.w / 2}
					{@const centerY = node.y + node.h / 2}
					{@const radius = Math.min(node.w, node.h) / 2}
					{@const titleLines = labelLines(node.label, node.depth === 1 ? 22 : 14)}
					{@const showingDetails = node.depth === 2 && focusedId === node.id && zoomRatio >= DETAIL_REVEAL && !!node.details}
					{@const expandedRegion = node.depth === 1 && zoomRatio >= COMPONENT_REVEAL}
					{@const detailCount = showingDetails ? node.details?.length ?? 0 : 0}
					{@const contentHeight = 85 + detailCount * 20}
					{@const contentTop = centerY - screen(contentHeight / 2)}
					{@const fileY = contentTop + screen(42 + titleLines.length * 15)}
					{@const detailStartY = fileY + screen(25)}
					{#if opacity > 0}
						<g
							class={`node-label tone-${node.tone}`}
							style={`opacity:${opacity}`}
							role="button"
							tabindex="0"
							onclick={() => focus(node)}
							onkeydown={(event) => {
								if (event.key === 'Enter' || event.key === ' ') {
									event.preventDefault();
									focus(node);
								}
							}}
						>
							<circle class="node-hit" cx={centerX} cy={centerY} r={radius} />
							{#if showingDetails}
								<text
									x={centerX}
									y={contentTop + screen(11)}
									text-anchor="middle"
									class="node-kicker"
									style={`font-size:${screen(8)}px`}
								>{node.kicker}</text>
								<text
									x={centerX}
									y={contentTop + screen(32)}
									text-anchor="middle"
									class="node-title"
									style={`font-size:${screen(14)}px`}
								>
									{#each titleLines as line, index (`${node.id}-title-${index}`)}
										<tspan x={centerX} dy={index === 0 ? 0 : screen(15)}>{line}</tspan>
									{/each}
								</text>
								{#if node.file}
									<text
										x={centerX}
										y={fileY}
										text-anchor="middle"
										class="node-file"
										style={`font-size:${screen(9.5)}px`}
									>{node.file}</text>
								{/if}
								{#each node.details ?? [] as detail, index (`${node.id}-detail-${index}`)}
									<text
										x={centerX}
										y={detailStartY + screen(index * 20)}
										text-anchor="middle"
										class="detail-label"
										style={`font-size:${screen(10)}px`}
									>{detail}</text>
								{/each}
							{:else}
								<text
									x={centerX}
									y={expandedRegion ? node.y + screen(22) : centerY - screen(titleLines.length * 8 + 12)}
									text-anchor="middle"
									class="node-kicker"
									style={`font-size:${screen(node.depth === 1 ? 9 : 7.5)}px`}
								>{node.kicker}</text>
								<text
									x={centerX}
									y={expandedRegion ? node.y + screen(46) : centerY - screen((titleLines.length - 1) * 7) + screen(7)}
									text-anchor="middle"
									class="node-title"
									style={`font-size:${screen(node.depth === 1 ? 18 : 12.5)}px`}
								>
									{#each titleLines as line, index (`${node.id}-title-${index}`)}
										<tspan x={centerX} dy={index === 0 ? 0 : screen(node.depth === 1 ? 18 : 14)}>{line}</tspan>
									{/each}
								</text>
								{#if node.description}
									<text
										x={centerX}
										y={expandedRegion ? node.y + screen(68 + (titleLines.length - 1) * 18) : centerY + screen(titleLines.length * 9 + 27)}
										text-anchor="middle"
										class="node-description"
										style={`font-size:${screen(10)}px;opacity:${regionDescriptionOpacity(node)}`}
									>{node.description}</text>
								{/if}
							{/if}
						</g>
					{/if}
				{/each}
			</g>
		</svg>
	</div>

	<header class="hud hud-top">
		<div>
			<p class="eyebrow">ENGAGIC / SYSTEM ATLAS</p>
			<nav aria-label="Current map location">
				{#each trail as item, index (item.id)}
					{#if index > 0}<span>/</span>{/if}
					<button onclick={() => focus(item)}>{item.label}</button>
				{/each}
			</nav>
		</div>
		<div class="readout">
			<span>{level}</span>
			<strong>{zoomPercent}%</strong>
		</div>
	</header>

	<div class="hud instructions">
		<span>SCROLL TO ENTER</span>
		<i></i>
		<span>DRAG TO MOVE</span>
		<i></i>
		<span>SELECT A REGION TO FOCUS</span>
	</div>

	<div class="zoom-controls" aria-label="Map zoom controls">
		<button onclick={() => zoomButton(1 / 1.35)} aria-label="Zoom out">−</button>
		<button class="home" onclick={reset} aria-label="Reset map">ENGAGIC</button>
		<button onclick={() => zoomButton(1.35)} aria-label="Zoom in">+</button>
	</div>
</div>

<style>
	:global(body.atlas-open) {
		overflow: hidden;
		background: #090711;
	}

	:global(body.atlas-open main) {
		height: 100dvh;
	}

	.atlas-shell {
		--atlas-bg: #090711;
		--atlas-panel: #100d1c;
		--atlas-text: #f4f0e8;
		--atlas-muted: #8f899f;
		--atlas-dim: #575064;
		--grid-minor: rgba(141, 130, 165, 0.13);
		--grid-major: rgba(151, 132, 178, 0.12);
		--source: #d69a5b;
		--sync: #9d79cb;
		--process: #55b5a6;
		--store: #6e92d8;
		--serve: #c36e88;
		position: fixed;
		inset: 0;
		z-index: 200;
		background:
			radial-gradient(circle at 51% 46%, rgba(91, 58, 138, 0.16), transparent 48%),
			var(--atlas-bg);
		color: var(--atlas-text);
		font-family: var(--font-mono);
		user-select: none;
	}

	.viewport {
		position: absolute;
		inset: 0;
		overflow: hidden;
		cursor: grab;
		touch-action: none;
	}

	.viewport.dragging {
		cursor: grabbing;
	}

	svg {
		display: block;
		width: 100%;
		height: 100%;
		opacity: 0;
		transition: opacity 260ms ease-out;
	}

	svg.ready {
		opacity: 1;
	}

	.node-box {
		--tone: var(--sync);
		fill: color-mix(in srgb, var(--tone) 7%, var(--atlas-panel));
		stroke: color-mix(in srgb, var(--tone) 54%, transparent);
		stroke-width: 1.2;
		vector-effect: non-scaling-stroke;
	}

	.node-box.depth-0 {
		fill: color-mix(in srgb, var(--sync) 8%, rgba(12, 9, 22, 0.92));
		stroke: rgba(157, 121, 203, 0.58);
		stroke-width: 1.4;
	}

	.node-box.depth-1 {
		fill: color-mix(in srgb, var(--tone) 4%, rgba(12, 10, 21, 0.86));
		stroke-width: 1.5;
	}

	.node-box.depth-2 {
		fill: color-mix(in srgb, var(--tone) 5%, rgba(9, 7, 17, 0.92));
		stroke-dasharray: 3 3;
	}

	.tone-source { --tone: var(--source); }
	.tone-sync { --tone: var(--sync); }
	.tone-process { --tone: var(--process); }
	.tone-store { --tone: var(--store); }
	.tone-serve { --tone: var(--serve); }

	.marker {
		fill: var(--tone);
	}

	.flow {
		fill: none;
		stroke: var(--tone);
		vector-effect: non-scaling-stroke;
	}

	.flow.dashed {
		stroke-linecap: round;
	}

	.edge-label,
	.node-kicker,
	.node-file,
	.detail-label {
		font-family: var(--font-mono);
	}

	.edge-label {
		fill: var(--atlas-muted);
		letter-spacing: 0.08em;
		paint-order: stroke;
		stroke: var(--atlas-bg);
		stroke-width: 4px;
		stroke-linejoin: round;
	}

	.root-title {
		pointer-events: none;
		transition: opacity 80ms linear;
	}

	.root-title > text:first-child {
		fill: var(--atlas-text);
		font-family: var(--font-display);
		font-weight: 400;
		letter-spacing: -0.035em;
	}

	.root-kicker {
		fill: var(--sync);
		font-family: var(--font-mono);
		font-weight: 600;
		letter-spacing: 0.2em;
	}

	.root-description {
		fill: var(--atlas-muted);
		font-family: var(--font-display);
		font-style: italic;
	}

	.node-label {
		--tone: var(--sync);
		cursor: pointer;
		outline: none;
	}

	.node-hit {
		fill: transparent;
		stroke: transparent;
		pointer-events: all;
	}

	.node-label:hover .node-hit,
	.node-label:focus .node-hit {
		fill: color-mix(in srgb, var(--tone) 9%, transparent);
		stroke: color-mix(in srgb, var(--tone) 70%, transparent);
		stroke-width: 1.5;
		vector-effect: non-scaling-stroke;
	}

	.node-label:focus .node-title,
	.node-label:hover .node-title {
		fill: var(--tone);
	}

	.node-kicker {
		fill: var(--tone);
		font-weight: 600;
		letter-spacing: 0.14em;
	}

	.node-title {
		fill: var(--atlas-text);
		font-family: var(--font-display);
		font-weight: 500;
		letter-spacing: -0.01em;
		transition: fill 160ms ease-out;
	}

	.node-description {
		fill: var(--atlas-muted);
		font-family: var(--font-body);
		pointer-events: none;
	}

	.node-file {
		fill: var(--atlas-muted);
		letter-spacing: 0.02em;
	}

	.detail-label {
		fill: color-mix(in srgb, var(--tone) 34%, var(--atlas-text));
		letter-spacing: 0.01em;
	}

	.hud {
		position: absolute;
		z-index: 3;
		pointer-events: none;
	}

	.hud-top {
		top: 24px;
		left: 28px;
		right: 28px;
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
	}

	.hud-top > div:first-child {
		padding: 10px 12px;
		margin: -10px -12px;
		background: linear-gradient(90deg, rgba(9, 7, 17, 0.92), rgba(9, 7, 17, 0.7) 78%, transparent);
	}

	.eyebrow {
		margin: 0 0 8px;
		color: var(--sync);
		font-size: 10px;
		font-weight: 600;
		letter-spacing: 0.18em;
	}

	nav {
		display: flex;
		align-items: center;
		gap: 7px;
		min-height: 24px;
	}

	nav span {
		color: var(--atlas-dim);
		font-size: 10px;
	}

	nav button {
		pointer-events: auto;
		margin: 0;
		padding: 0;
		border: 0;
		background: transparent;
		color: var(--atlas-muted);
		font: 500 11px/1.2 var(--font-mono);
		letter-spacing: 0.04em;
		cursor: pointer;
	}

	nav button:last-child,
	nav button:hover {
		color: var(--atlas-text);
	}

	.readout {
		display: grid;
		grid-template-columns: auto auto;
		gap: 10px;
		align-items: baseline;
		padding: 8px 10px;
		border: 1px solid rgba(157, 121, 203, 0.25);
		background: rgba(9, 7, 17, 0.76);
		backdrop-filter: blur(10px);
	}

	.readout span {
		color: var(--atlas-muted);
		font-size: 9px;
		letter-spacing: 0.14em;
	}

	.readout strong {
		color: var(--atlas-text);
		font-size: 11px;
		font-weight: 500;
		font-variant-numeric: tabular-nums;
	}

	.instructions {
		left: 28px;
		bottom: 27px;
		display: flex;
		align-items: center;
		gap: 9px;
		color: var(--atlas-muted);
		font-size: 9px;
		letter-spacing: 0.13em;
	}

	.instructions i {
		width: 16px;
		height: 1px;
		background: var(--atlas-dim);
	}

	.zoom-controls {
		position: absolute;
		right: 28px;
		bottom: 24px;
		z-index: 4;
		display: flex;
		border: 1px solid rgba(157, 121, 203, 0.28);
		background: rgba(9, 7, 17, 0.82);
		backdrop-filter: blur(10px);
	}

	.zoom-controls button {
		min-width: 38px;
		height: 36px;
		padding: 0 11px;
		border: 0;
		border-right: 1px solid rgba(157, 121, 203, 0.2);
		background: transparent;
		color: var(--atlas-text);
		font: 500 17px/1 var(--font-mono);
		cursor: pointer;
	}

	.zoom-controls button:last-child {
		border-right: 0;
	}

	.zoom-controls button:hover {
		background: rgba(157, 121, 203, 0.12);
		color: var(--sync);
	}

	.zoom-controls .home {
		font-size: 9px;
		letter-spacing: 0.12em;
	}

	@media (max-width: 700px) {
		.hud-top {
			top: 16px;
			left: 16px;
			right: 16px;
		}

		.instructions {
			left: 16px;
			bottom: 18px;
		}

		.instructions span:nth-of-type(n + 2),
		.instructions i:nth-of-type(n + 1) {
			display: none;
		}

		.zoom-controls {
			right: 16px;
			bottom: 14px;
		}

		nav {
			max-width: 58vw;
			overflow: hidden;
		}

		nav button {
			white-space: nowrap;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		svg,
		.node-title {
			transition: none;
		}
	}
</style>
