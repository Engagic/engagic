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
	const dayOfWeek = $derived(isValidDate && date ? date.toLocaleDateString('en-US', { weekday: 'short' }) : null);
	const monthDay = $derived(isValidDate && date ? date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : null);
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
		if (meeting.has_items) {
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

	// Check if meeting has any participation info
	const hasParticipation = $derived(() => {
		const p = meeting.participation;
		if (!p) return false;
		return !!(p.email || p.emails?.length || p.phone || p.virtual_url);
	});
</script>

<a
	href="/{cityUrl}/{meetingSlug}"
	class="meeting-card {isPast ? 'past-meeting' : 'upcoming-meeting'} {meeting.meeting_status ? 'has-alert' : ''} {getStatusClass(meeting)}"
	data-sveltekit-preload-data="tap"
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
			{#if meeting.has_items}
				<div class="meeting-status status-items">
					<svg class="status-icon-svg" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13.25 4.75 6 12 2.75 8.75"/></svg>
					AI Summary
				</div>
			{:else if meeting.summary}
				<div class="meeting-status {isPast ? 'status-ready' : 'status-summary'}">
					<svg class="status-icon-svg" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13.25 4.75 6 12 2.75 8.75"/></svg>
					AI Summary
				</div>
			{:else if meeting.agenda_url}
				<div class="meeting-status status-agenda">
					<svg class="status-icon-svg" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 1.5H4a1.5 1.5 0 0 0-1.5 1.5v10A1.5 1.5 0 0 0 4 14.5h8A1.5 1.5 0 0 0 13.5 13V6L9 1.5Z"/><path d="M9 1.5V6h4.5"/></svg>
					Agenda Available
				</div>
			{:else if meeting.packet_url}
				<div class="meeting-status status-packet">
					<svg class="status-icon-svg" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.5 2H4a1.5 1.5 0 0 0-1.5 1.5v9A1.5 1.5 0 0 0 4 14h8a1.5 1.5 0 0 0 1.5-1.5V5L10.5 2Z"/><path d="M5.5 8.5h5M5.5 11h3"/></svg>
					Meeting Packet
				</div>
			{:else}
				<div class="meeting-status status-none">
					<svg class="status-icon-svg" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="8" r="6"/><path d="M8 4v4l2.5 1.5"/></svg>
					{isPast ? 'No Documents' : 'Coming Soon'}
				</div>
			{/if}

			{#if meeting.meeting_status}
				<div class="meeting-alert">
					This meeting has been {meeting.meeting_status}
				</div>
			{/if}

			{#if hasParticipation() && !isPast}
				<div class="participation-indicator">
					<svg class="status-icon-svg" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 13a6 6 0 0 1 12 0"/><path d="M8 3v4M5.5 5.5 8 7l2.5-1.5"/></svg>
					How to Participate
				</div>
			{/if}
		</div>
	</div>
</a>

<style>
	.meeting-card {
		display: block;
		width: 100%;
		box-sizing: border-box;
		background: transparent;
		border: none;
		border-bottom: 1px solid var(--border-primary);
		padding: 1.5rem 0;
		cursor: pointer;
		transition: padding-left 0.2s ease;
		text-decoration: none;
		color: inherit;
	}

	.meeting-card:hover {
		padding-left: 8px;
	}

	.meeting-card.has-alert {
		border-left: 2px solid var(--badge-cancelled-text);
		padding-left: 12px;
	}

	.meeting-card.has-alert:hover {
		padding-left: 18px;
	}

	/* Status borders — no-op in list layout */
	.meeting-card.status-border-ai,
	.meeting-card.status-border-agenda,
	.meeting-card.status-border-packet,
	.meeting-card.status-border-none {
		border-image: none;
	}

	.meeting-card.past-meeting {
		opacity: 0.7;
	}

	.meeting-card.past-meeting:hover {
		opacity: 1;
	}

	.meeting-card-header {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 1rem;
		margin-bottom: 0.35rem;
	}

	.meeting-title {
		font-family: var(--font-display);
		font-size: 1.3rem;
		font-weight: 400;
		color: var(--text-primary);
		line-height: 1.25;
		letter-spacing: -0.01em;
		flex: 1;
		min-width: 0;
		margin: 0;
	}

	.meeting-date-time {
		font-family: var(--font-body);
		font-size: 0.8rem;
		color: var(--civic-gray);
		white-space: nowrap;
		flex-shrink: 0;
	}

	.meeting-card-body {
		display: flex;
		gap: 1rem;
		margin-top: 0.5rem;
		align-items: center;
	}

	.left-column {
		flex: 1;
	}

	.right-column {
		flex-shrink: 0;
		text-align: right;
	}

	.meeting-status {
		font-family: var(--font-body);
		font-size: 0.65rem;
		font-weight: 700;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		padding: 3px 8px;
		border-radius: 2px;
		display: inline-flex;
		align-items: center;
		gap: 0.3em;
		white-space: nowrap;
	}

	.status-items {
		color: var(--badge-green-text);
		background: var(--badge-green-bg);
	}

	.status-summary {
		color: var(--badge-green-text);
		background: var(--badge-green-bg);
	}

	.status-agenda {
		color: var(--civic-yellow);
		background: rgba(196, 150, 10, 0.1);
	}

	.status-packet {
		color: var(--civic-orange);
		background: rgba(212, 135, 77, 0.1);
	}

	.status-none {
		color: var(--civic-gray);
		background: var(--surface-secondary);
	}

	.status-icon-svg {
		width: 0.85em;
		height: 0.85em;
		vertical-align: -0.1em;
		flex-shrink: 0;
	}

	.meeting-topics {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
		margin-top: 0.5rem;
	}

	.topic-tag {
		font-family: var(--font-body);
		font-size: 0.65rem;
		font-weight: 600;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		padding: 1px 7px;
		background: var(--topic-tag-bg);
		color: var(--topic-tag-text);
		border: none;
		border-radius: 2px;
	}

	.topic-tag.topic-more {
		color: var(--civic-gray);
		font-weight: 600;
	}

	.meeting-alert {
		color: var(--civic-red);
		font-weight: 600;
		font-size: 0.8rem;
		margin-top: 0.25rem;
		text-transform: capitalize;
	}

	.participation-indicator {
		color: var(--civic-green);
		font-weight: 600;
		font-size: 0.7rem;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		margin-top: 0.375rem;
		padding: 0.2rem 0.4rem;
		background: var(--participation-bg);
		border-radius: 2px;
		display: inline-block;
	}

	@media (max-width: 640px) {
		.meeting-card-header {
			flex-direction: column;
			align-items: flex-start;
			gap: 0.25rem;
		}

		.meeting-title {
			font-size: 1.15rem;
		}

		.meeting-card-body {
			flex-direction: column;
			align-items: flex-start;
			gap: 0.5rem;
		}

		.right-column {
			text-align: left;
		}
	}
</style>
