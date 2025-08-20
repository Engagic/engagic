<script lang="ts">
	import type { Meeting } from '../api/types';
	import MeetingCard from './MeetingCard.svelte';
	
	interface Props {
		meetings: Meeting[];
		cityUrl: string;
		isPast?: boolean;
	}
	
	let { meetings, cityUrl, isPast = false }: Props = $props();
</script>

<div 
	class="meeting-list-container"
	role="list"
	aria-label={isPast ? "Past meetings" : "Upcoming meetings"}
>
	{#each meetings as meeting}
		<MeetingCard 
			{meeting}
			{cityUrl}
			{isPast}
		/>
	{/each}
</div>

<style>
	.meeting-list-container {
		display: grid;
		gap: 1rem;
	}
</style>