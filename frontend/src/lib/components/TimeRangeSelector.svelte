<script lang="ts">
	export type TimeRange = '7d' | '30d' | '90d' | 'all';

	interface Props {
		selected: TimeRange;
		onchange: (range: TimeRange) => void;
	}

	let { selected = $bindable(), onchange }: Props = $props();

	const ranges: { value: TimeRange; label: string }[] = [
		{ value: '7d', label: 'Last 7 days' },
		{ value: '30d', label: 'Last 30 days' },
		{ value: '90d', label: 'Last 90 days' },
		{ value: 'all', label: 'All time' },
	];

	function handleSelect(range: TimeRange) {
		selected = range;
		onchange(range);
	}
</script>

<div class="time-range-selector">
	{#each ranges as range}
		<button
			class="range-button"
			class:active={selected === range.value}
			onclick={() => handleSelect(range.value)}
		>
			{range.label}
		</button>
	{/each}
</div>

<style>
	.time-range-selector {
		display: flex;
		gap: 0.5rem;
		padding: 0.25rem;
		background: var(--bg-secondary);
		border-radius: 0.5rem;
		border: 1px solid var(--border);
	}

	.range-button {
		padding: 0.5rem 1rem;
		border: none;
		background: transparent;
		color: var(--text-secondary);
		border-radius: 0.375rem;
		cursor: pointer;
		font-size: 0.875rem;
		font-weight: 500;
		transition: all 0.2s ease;
	}

	.range-button:hover {
		background: var(--bg-tertiary);
		color: var(--text-primary);
	}

	.range-button.active {
		background: var(--bg-primary);
		color: var(--text-primary);
		box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
	}
</style>
