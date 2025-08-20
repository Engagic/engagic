<script lang="ts">
	import type { Meeting } from '../types';
	import { generateMeetingSlug } from '../utils';
	import { formatMeetingDate, extractTime } from '../date-utils';
	
	interface Props {
		meeting: Meeting;
		cityUrl: string;
		isPast?: boolean;
	}
	
	let { meeting, cityUrl, isPast = false }: Props = $props();
	
	const meetingSlug = $derived(generateMeetingSlug(meeting));
	const formattedDate = $derived(formatMeetingDate(meeting.meeting_date));
	const time = $derived(extractTime(meeting.meeting_date));
</script>

<a 
	href="/{cityUrl}/{meetingSlug}" 
	class="meeting-card {isPast ? 'past-meeting' : 'upcoming-meeting'}"
	role="listitem"
	aria-label="{meeting.title || meeting.meeting_name} on {formattedDate} at {time}"
>
	<div class="meeting-title">
		{meeting.title || meeting.meeting_name} on {formattedDate}
	</div>
	
	<div class="meeting-date" aria-hidden="true">
		{time}
	</div>
	
	{#if meeting.processed_summary}
		<div class="meeting-status status-ready" role="status">
			<span class="sr-only">Status:</span> AI Summary Available
		</div>
	{:else if meeting.packet_url}
		<div class="meeting-status status-packet" role="status">
			<span class="sr-only">Status:</span> Agenda Packet Available
		</div>
	{:else}
		<div class="meeting-status status-none" role="status">
			<span class="sr-only">Status:</span> No agenda posted yet
		</div>
	{/if}
</a>

<style>
	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		padding: 0;
		margin: -1px;
		overflow: hidden;
		clip: rect(0, 0, 0, 0);
		white-space: nowrap;
		border-width: 0;
	}
</style>