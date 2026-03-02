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
		background: var(--surface-primary);
		border: 1px solid var(--border-primary);
		border-radius: 12px;
		padding: 1.5rem;
		cursor: pointer;
		transition: all var(--transition-normal);
		box-shadow: 0 2px 8px var(--shadow-sm);
		text-decoration: none;
		color: inherit;
	}

	.meeting-card:hover {
		border-color: var(--border-hover);
		transform: translateY(-4px);
		box-shadow: 0 8px 24px var(--shadow-lg);
	}

	.meeting-card.has-alert {
		border-left: 4px solid var(--badge-cancelled-text);
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

	.meeting-card.past-meeting {
		opacity: 0.8;
	}

	.meeting-card.past-meeting:hover {
		opacity: 1;
	}

	.meeting-card-header {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 1rem;
		margin-bottom: 0.5rem;
	}

	.meeting-title {
		font-size: 1.1rem;
		font-weight: 700;
		color: var(--text-primary);
		line-height: 1.4;
		letter-spacing: 0.026em;
		flex: 1;
		min-width: 0;
		margin: 0;
	}

	.meeting-date-time {
		font-size: 0.95rem;
		font-weight: 600;
		color: var(--civic-orange);
		white-space: nowrap;
		flex-shrink: 0;
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

	.meeting-status {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8rem;
		font-weight: 500;
		color: var(--civic-gray);
	}

	.status-items {
		color: var(--civic-accent);
	}

	.status-summary {
		color: var(--civic-green);
	}

	.status-agenda {
		color: var(--civic-yellow);
	}

	.status-packet {
		color: var(--civic-orange);
	}

	.status-none {
		color: var(--civic-gray);
	}

	.status-icon-svg {
		width: 0.9em;
		height: 0.9em;
		vertical-align: -0.1em;
		flex-shrink: 0;
	}

	.meeting-topics {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin-top: 0.75rem;
	}

	.topic-tag {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.7rem;
		padding: 0.25rem 0.55rem;
		background: var(--topic-tag-bg);
		color: var(--topic-tag-text);
		border: 1px solid var(--topic-tag-border);
		border-radius: 4px;
		font-weight: 500;
		transition: background var(--transition-normal), border-color var(--transition-normal);
	}

	.topic-tag.topic-more {
		background: var(--topic-tag-bg);
		color: var(--civic-gray);
		border-color: var(--topic-tag-border);
		font-weight: 600;
	}

	.meeting-alert {
		color: var(--civic-red);
		font-weight: 600;
		font-size: 0.85rem;
		margin-top: 0.25rem;
		text-transform: capitalize;
	}

	.participation-indicator {
		color: var(--civic-green);
		font-weight: 600;
		font-size: 0.8rem;
		margin-top: 0.375rem;
		padding: 0.25rem 0.5rem;
		background: var(--participation-bg);
		border-radius: 4px;
		display: inline-block;
	}

	@media (max-width: 640px) {
		.meeting-card-header {
			flex-direction: column;
			align-items: flex-start;
			gap: 0.5rem;
		}

		.meeting-card-body {
			flex-direction: column;
			gap: 0.75rem;
		}

		.right-column {
			text-align: left;
		}
	}
</style>
