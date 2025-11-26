<script lang="ts">
	import { fly } from 'svelte/transition';
	import type { Meeting } from '../api/types';
	import { generateMeetingSlug } from '../utils/utils';
	import { formatRelativeTime, getUrgencyLevel } from '../utils/date-utils';

	interface Props {
		meeting: Meeting;
		cityUrl: string;
		isPast?: boolean;
		showCity?: boolean;
		cityName?: string;
		animationDelay?: number;
		animationDuration?: number;
		onIntroEnd?: () => void;
	}

	let {
		meeting,
		cityUrl,
		isPast = false,
		showCity = false,
		cityName = '',
		animationDelay = 0,
		animationDuration = 300,
		onIntroEnd
	}: Props = $props();

	const meetingSlug = $derived(generateMeetingSlug(meeting));
	const relativeTime = $derived(formatRelativeTime(meeting.date));
	const urgency = $derived(getUrgencyLevel(meeting.date));

	// Participation info
	const participation = $derived(meeting.participation || {});
	const canEmail = $derived(Boolean(participation.email));
	const canWatch = $derived(Boolean(participation.virtual_url || participation.streaming_urls?.length));
	const canAttend = $derived(!participation.is_virtual_only);

	// Primary action - the most useful participation method
	const primaryAction = $derived(
		canEmail ? 'email' :
		canWatch ? 'watch' :
		canAttend ? 'attend' : null
	);

	// Single topic for clean display
	const primaryTopic = $derived(meeting.topics?.[0] || null);

	function handleActionClick(e: MouseEvent) {
		// Prevent navigation when clicking action button
		e.preventDefault();
		e.stopPropagation();

		if (primaryAction === 'email' && participation.email) {
			window.location.href = `mailto:${participation.email}?subject=${encodeURIComponent(meeting.title)}`;
		} else if (primaryAction === 'watch' && participation.virtual_url) {
			window.open(participation.virtual_url, '_blank');
		}
	}
</script>

<a
	href="/{cityUrl}/{meetingSlug}"
	class="card"
	class:past={isPast}
	class:urgent={urgency === 'urgent'}
	class:soon={urgency === 'soon'}
	data-sveltekit-preload-data="tap"
	in:fly={{ y: 20, duration: animationDuration, delay: animationDelay }}
	onintroend={onIntroEnd}
>
	{#if showCity && cityName}
		<div class="city-label">{cityName}</div>
	{/if}

	<div class="card-content">
		<div class="main">
			<h2 class="title">{meeting.title}</h2>
			<time class="time" datetime={meeting.date}>{relativeTime}</time>
		</div>

		<div class="actions">
			{#if !isPast && primaryAction}
				<button
					class="action-btn"
					class:pulse={urgency === 'urgent' || urgency === 'soon'}
					onclick={handleActionClick}
					aria-label={primaryAction === 'email' ? 'Email council' : primaryAction === 'watch' ? 'Watch live' : 'Attend meeting'}
				>
					{#if primaryAction === 'email'}
						Email Council
					{:else if primaryAction === 'watch'}
						Watch Live
					{:else}
						Attend
					{/if}
				</button>
			{/if}

			{#if primaryTopic}
				<span class="topic">{primaryTopic}</span>
			{/if}
		</div>
	</div>

	{#if urgency === 'urgent' && !isPast}
		<div class="urgency-badge">Today</div>
	{:else if urgency === 'soon' && !isPast}
		<div class="urgency-badge soon">Soon</div>
	{/if}
</a>

<style>
	.card {
		display: block;
		background: var(--surface-card);
		border: 1px solid var(--border-primary);
		border-radius: var(--radius-lg);
		padding: var(--space-lg);
		text-decoration: none;
		color: inherit;
		transition: all var(--transition-normal);
		position: relative;
	}

	.card:hover {
		border-color: var(--border-hover);
		background: var(--surface-card-hover);
	}

	.card.past {
		opacity: 0.7;
	}

	.card.past:hover {
		opacity: 1;
	}

	.card.urgent {
		border-left: 3px solid var(--action-coral);
	}

	.card.soon {
		border-left: 3px solid var(--urgent-amber);
	}

	.city-label {
		font-family: var(--font-body);
		font-size: var(--text-xs);
		font-weight: var(--font-medium);
		color: var(--text-muted);
		margin-bottom: var(--space-xs);
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}

	.card-content {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: var(--space-lg);
	}

	.main {
		flex: 1;
		min-width: 0;
	}

	.title {
		font-family: var(--font-body);
		font-size: var(--text-lg);
		font-weight: var(--font-semibold);
		color: var(--text);
		line-height: var(--leading-snug);
		margin: 0 0 var(--space-xs) 0;
	}

	.time {
		font-family: var(--font-body);
		font-size: var(--text-sm);
		color: var(--text-muted);
		display: block;
	}

	.actions {
		display: flex;
		flex-direction: column;
		align-items: flex-end;
		gap: var(--space-sm);
		flex-shrink: 0;
	}

	.action-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		padding: 0.5rem 1rem;
		font-family: var(--font-body);
		font-size: var(--text-sm);
		font-weight: var(--font-semibold);
		color: white;
		background: var(--action-coral);
		border: none;
		border-radius: var(--radius-sm);
		cursor: pointer;
		transition: all var(--transition-fast);
		white-space: nowrap;
	}

	.action-btn:hover {
		background: var(--action-coral-hover);
		transform: translateY(-1px);
	}

	.action-btn.pulse {
		animation: action-pulse 2.5s ease-in-out infinite;
	}

	@keyframes action-pulse {
		0%, 100% {
			box-shadow: 0 2px 8px rgba(249, 115, 22, 0.25);
		}
		50% {
			box-shadow: 0 2px 8px rgba(249, 115, 22, 0.25),
			            0 0 0 4px rgba(249, 115, 22, 0.1);
		}
	}

	.topic {
		font-family: var(--font-body);
		font-size: var(--text-xs);
		color: var(--text-subtle);
		padding: 0.25rem 0.5rem;
		background: var(--surface-warm);
		border-radius: var(--radius-sm);
	}

	.urgency-badge {
		position: absolute;
		top: var(--space-sm);
		right: var(--space-sm);
		font-family: var(--font-body);
		font-size: var(--text-xs);
		font-weight: var(--font-semibold);
		color: white;
		background: var(--action-coral);
		padding: 0.125rem 0.5rem;
		border-radius: var(--radius-sm);
		text-transform: uppercase;
		letter-spacing: 0.02em;
	}

	.urgency-badge.soon {
		background: var(--urgent-amber);
		color: #1a1a1a;
	}

	@media (max-width: 640px) {
		.card-content {
			flex-direction: column;
			gap: var(--space-md);
		}

		.actions {
			flex-direction: row;
			align-items: center;
			width: 100%;
		}

		.action-btn {
			flex: 1;
		}
	}
</style>
