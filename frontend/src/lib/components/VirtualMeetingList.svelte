<script lang="ts">
	import { createVirtualizer } from '@tanstack/svelte-virtual';
	import type { Meeting } from '../types';
	import MeetingCard from './MeetingCard.svelte';
	
	interface Props {
		meetings: Meeting[];
		cityUrl: string;
		isPast?: boolean;
	}
	
	let { meetings, cityUrl, isPast = false }: Props = $props();
	
	let scrollElement = $state<HTMLDivElement>();
	
	const virtualizer = $derived.by(() => {
		if (!scrollElement) return null;
		
		return createVirtualizer({
			count: meetings.length,
			getScrollElement: () => scrollElement,
			estimateSize: () => 120, // Estimated height of meeting card
			overscan: 5,
		});
	});
	
	const virtualItems = $derived(virtualizer?.getVirtualItems() || []);
</script>

<div 
	bind:this={scrollElement}
	class="virtual-scroll-container"
	role="list"
	aria-label={isPast ? "Past meetings" : "Upcoming meetings"}
>
	{#if virtualizer}
		<div
			style="height: {virtualizer.getTotalSize()}px; width: 100%; position: relative;"
		>
			{#each virtualItems as item (item.key)}
				<div
					style="
						position: absolute;
						top: 0;
						left: 0;
						width: 100%;
						height: {item.size}px;
						transform: translateY({item.start}px);
					"
				>
					<MeetingCard 
						meeting={meetings[item.index]}
						{cityUrl}
						{isPast}
					/>
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.virtual-scroll-container {
		height: 600px;
		overflow-y: auto;
		overflow-x: hidden;
	}
	
	@media (max-width: 640px) {
		.virtual-scroll-container {
			height: 400px;
		}
	}
</style>