<script lang="ts">
	import { onMount } from 'svelte';

	interface Props {
		value: number;
		duration?: number;
		formatFn?: (n: number) => string;
	}

	let { value, duration = 1500, formatFn = (n) => n.toLocaleString() }: Props = $props();

	let displayValue = $state(0);
	let frameId: number;

	onMount(() => {
		const startTime = Date.now();
		const startValue = 0;
		const endValue = value;

		const animate = () => {
			const elapsed = Date.now() - startTime;
			const progress = Math.min(elapsed / duration, 1);

			// Easing function (ease-out cubic)
			const eased = 1 - Math.pow(1 - progress, 3);

			displayValue = Math.floor(startValue + (endValue - startValue) * eased);

			if (progress < 1) {
				frameId = requestAnimationFrame(animate);
			} else {
				displayValue = endValue;
			}
		};

		frameId = requestAnimationFrame(animate);

		return () => {
			if (frameId) {
				cancelAnimationFrame(frameId);
			}
		};
	});
</script>

<span class="animated-counter">
	{formatFn(displayValue)}
</span>

<style>
	.animated-counter {
		font-variant-numeric: tabular-nums;
		font-family: 'IBM Plex Mono', monospace;
	}
</style>
