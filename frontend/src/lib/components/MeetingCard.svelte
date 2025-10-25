<script lang="ts">
	import type { Meeting } from '../api/types';
	import { generateMeetingSlug } from '../utils/utils';
	import { formatMeetingDate, extractTime } from '../utils/date-utils';
	
	interface Props {
		meeting: Meeting;
		cityUrl: string;
		isPast?: boolean;
	}
	
	let { meeting, cityUrl, isPast = false }: Props = $props();
	
	const meetingSlug = $derived(generateMeetingSlug(meeting));
	const formattedDate = $derived(formatMeetingDate(meeting.date));
	const time = $derived(extractTime(meeting.date));
</script>

<a
	href="/{cityUrl}/{meetingSlug}"
	class="meeting-card {isPast ? 'past-meeting' : 'upcoming-meeting'} {meeting.meeting_status ? 'has-alert' : ''}"
	aria-label="{meeting.title} on {formattedDate} at {time}"
>
	{#if meeting.meeting_status}
		<div class="status-flag" title="This meeting has been {meeting.meeting_status}">
			<span class="flag-icon">!</span>
		</div>
	{/if}

	<div class="meeting-content">
		<div class="meeting-title">
			{meeting.title} on {formattedDate}
		</div>

		{#if meeting.meeting_status}
			<div class="meeting-alert">
				This meeting has been {meeting.meeting_status}
			</div>
		{/if}

		<div class="meeting-date" aria-hidden="true">
			{time}
		</div>

		{#if meeting.summary}
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
	</div>
</a>

<style>
	.meeting-card {
		position: relative;
		display: flex;
		gap: 0.75rem;
	}

	.meeting-card.has-alert {
		border-left: 3px solid #dc2626;
	}

	.status-flag {
		flex-shrink: 0;
		width: 24px;
		height: 24px;
		background: #dc2626;
		color: white;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		font-weight: 700;
		font-size: 0.9rem;
		align-self: flex-start;
		margin-top: 0.25rem;
	}

	.flag-icon {
		line-height: 1;
	}

	.meeting-content {
		flex: 1;
		min-width: 0;
	}

	.meeting-alert {
		color: #dc2626;
		font-weight: 600;
		font-size: 0.85rem;
		margin-top: 0.25rem;
		text-transform: capitalize;
	}

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