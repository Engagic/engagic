<script lang="ts">
	interface Props {
		value: number;
		showIcon?: boolean;
	}

	let { value, showIcon = true }: Props = $props();

	const isPositive = $derived(value > 0);
	const isNeutral = $derived(value === 0);
	const icon = $derived(isPositive ? '↑' : isNeutral ? '→' : '↓');
	const color = $derived(isPositive ? 'var(--green)' : isNeutral ? 'var(--text-secondary)' : 'var(--red)');
	const formattedValue = $derived(
		isPositive ? `+${value.toFixed(1)}%` : `${value.toFixed(1)}%`
	);
</script>

<span class="trend-indicator" style="color: {color}">
	{#if showIcon}
		<span class="trend-icon">{icon}</span>
	{/if}
	<span class="trend-value">{formattedValue}</span>
</span>

<style>
	.trend-indicator {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		font-size: 0.875rem;
		font-weight: 600;
		font-family: 'IBM Plex Mono', monospace;
	}

	.trend-icon {
		font-size: 1rem;
		line-height: 1;
	}

	.trend-value {
		font-variant-numeric: tabular-nums;
	}
</style>
