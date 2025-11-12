<script lang="ts">
	import { fly } from 'svelte/transition';
	import { onMount } from 'svelte';
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

	// Track mobile state for topic limiting (performance: check once, not on every render)
	let isMobile = $state(false);

	onMount(() => {
		isMobile = window.innerWidth <= 640;
		const handleResize = () => {
			isMobile = window.innerWidth <= 640;
		};
		window.addEventListener('resize', handleResize);
		return () => window.removeEventListener('resize', handleResize);
	});

	function getStatusClass(meeting: Meeting): string {
		if (meeting.items?.length > 0 && meeting.items.some(item => item.summary)) {
			return 'status-border-ai';
		} else if (meeting.summary) {
			return 'status-border-ai';
		} else if (meeting.agenda_url) {
			return 'status-border-agenda';
		} else if (meeting.packet_url) {
			return 'status-border-packet';
		}
		return 'status-border-none';
	}
</script>

<a
	href="/{cityUrl}/{meetingSlug}"
	class="meeting-card {isPast ? 'past-meeting' : 'upcoming-meeting'} {meeting.meeting_status ? 'has-alert' : ''} {getStatusClass(meeting)}"
	data-sveltekit-preload-data="hover"
	in:fly={{ y: 20, duration: animationDuration, delay: animationDelay }}
	onintroend={onIntroEnd}
>
	<div class="meeting-card-header">
		<div class="left-column">
			<h2 class="meeting-title">
				{meeting.title}
			</h2>
		</div>
		<div class="right-column">
			{#if isValidDate}
				<div class="meeting-date-time">
					<time datetime={meeting.date}>
						{dayOfWeek}, {monthDay}{#if timeStr} • {timeStr}{/if}
					</time>
				</div>
			{/if}
		</div>
	</div>

	<div class="meeting-card-body">
		<div class="left-column">
			{#if meeting.topics && meeting.topics.length > 0}
				{@const maxTopics = isMobile ? 3 : 5}
				{@const displayTopics = meeting.topics.slice(0, maxTopics)}
				{@const remainingCount = meeting.topics.length - maxTopics}
				<div class="meeting-topics">
					{#each displayTopics as topic}
						<span class="topic-tag">{topic}</span>
					{/each}
					{#if remainingCount > 0}
						<span class="topic-tag topic-more">+{remainingCount} more</span>
					{/if}
				</div>
			{/if}
		</div>

		<div class="right-column">
			{#if meeting.items?.length > 0 && meeting.items.some(item => item.summary)}
				<div class="meeting-status status-items">
					<span class="status-icon">✓</span> AI Summary
				</div>
			{:else if meeting.summary}
				<div class="meeting-status {isPast ? 'status-ready' : 'status-summary'}">
					<span class="status-icon">✓</span> AI Summary
				</div>
			{:else if meeting.agenda_url}
				<div class="meeting-status status-agenda">
					<span class="status-icon">📄</span> Agenda Available
				</div>
			{:else if meeting.packet_url}
				<div class="meeting-status status-packet">
					<span class="status-icon">📋</span> Meeting Packet
				</div>
			{:else}
				<div class="meeting-status status-none">
					<span class="status-icon">⏳</span> {isPast ? 'No Documents' : 'Coming Soon'}
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
		border-left: 4px solid #dc2626;
	}

	.meeting-card.status-border-ai {
		border-left: 4px solid var(--civic-green);
	}

	.meeting-card.status-border-agenda {
		border-left: 4px solid var(--civic-yellow);
	}

	.meeting-card.status-border-packet {
		border-left: 4px solid var(--civic-orange);
	}

	.meeting-card.status-border-none {
		border-left: 4px solid var(--civic-border);
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

	.status-icon {
		display: inline-block;
		margin-right: 0.25rem;
		font-size: 0.9em;
	}

	.meeting-alert {
		color: #ef4444;
		font-weight: 600;
		font-size: 0.85rem;
		margin-top: 0.25rem;
		text-transform: capitalize;
	}
</style>
