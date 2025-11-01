<script lang="ts">
	import { fly } from 'svelte/transition';
	import type { Meeting } from '../api/types';
	import { generateMeetingSlug } from '../utils/utils';
	import { extractTime } from '../utils/date-utils';

	interface Props {
		meeting: Meeting;
		cityUrl: string;
		isPast?: boolean;
		animationDelay?: number;
		animationDuration?: number;
		onIntroEnd?: () => void;
	}

	let {
		meeting,
		cityUrl,
		isPast = false,
		animationDelay = 0,
		animationDuration = 0,
		onIntroEnd
	}: Props = $props();

	const meetingSlug = $derived(generateMeetingSlug(meeting));

	const date = $derived(meeting.date ? new Date(meeting.date) : null);
	const isValidDate = $derived(date && !isNaN(date.getTime()) && date.getTime() !== 0);
	const dayOfWeek = $derived(isValidDate ? date.toLocaleDateString('en-US', { weekday: 'short' }) : null);
	const monthDay = $derived(isValidDate ? date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : null);
	const timeStr = $derived(extractTime(meeting.date));
</script>

<a
	href="/{cityUrl}/{meetingSlug}"
	class="meeting-card {isPast ? 'past-meeting' : 'upcoming-meeting'} {meeting.meeting_status ? 'has-alert' : ''}"
	in:fly|global={{ y: 20, duration: animationDuration, delay: animationDelay }}
	onintroend={onIntroEnd}
>
	<div class="meeting-card-header">
		<div class="left-column">
			<div class="meeting-title">
				{meeting.title}
			</div>
		</div>
		<div class="right-column">
			{#if isValidDate}
				<div class="meeting-date-time">
					{dayOfWeek}, {monthDay}{#if timeStr} • {timeStr}{/if}
				</div>
			{/if}
		</div>
	</div>

	<div class="meeting-card-body">
		<div class="left-column">
			{#if meeting.topics && meeting.topics.length > 0}
				<div class="meeting-topics">
					{#each meeting.topics as topic}
						<span class="topic-tag">{topic}</span>
					{/each}
				</div>
			{/if}
		</div>

		<div class="right-column">
			{#if meeting.items?.length > 0 && meeting.items.some(item => item.summary)}
				<div class="meeting-status status-items">
					✓ Item Summaries
				</div>
			{:else if meeting.summary}
				<div class="meeting-status {isPast ? 'status-ready' : 'status-summary'}">
					✓ Summary Ready
				</div>
			{:else if meeting.agenda_url}
				<div class="meeting-status status-agenda">
					Agenda Posted
				</div>
			{:else if meeting.packet_url}
				<div class="meeting-status status-packet">
					{isPast ? 'Packet Available' : 'Packet Posted'}
				</div>
			{:else}
				<div class="meeting-status status-none">
					{isPast ? 'No agenda posted' : 'No Agenda Posted'}
				</div>
			{/if}

			{#if meeting.meeting_status}
				<div class="meeting-alert">
					This meeting has been {meeting.meeting_status}
				</div>
			{/if}
		</div>
	</div>
</a>

<style>
	.meeting-card.has-alert {
		border-left: 3px solid #dc2626;
	}

	.meeting-card-body {
		display: flex;
		gap: 1rem;
		margin-top: 0.5rem;
	}

	.left-column {
		flex: 1;
	}

	.right-column {
		flex-shrink: 0;
		text-align: right;
	}

	.meeting-alert {
		color: #ef4444;
		font-weight: 600;
		font-size: 0.85rem;
		margin-top: 0.25rem;
		text-transform: capitalize;
	}
</style>
