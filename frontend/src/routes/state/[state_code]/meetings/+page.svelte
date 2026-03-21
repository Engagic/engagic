<script lang="ts">
	import { generateMeetingSlug } from '$lib/utils/utils';
	import Footer from '$lib/components/Footer.svelte';
	import SeoHead from '$lib/components/SeoHead.svelte';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	const STATE_NAMES: Record<string, string> = {
		AL: 'Alabama', AK: 'Alaska', AZ: 'Arizona', AR: 'Arkansas', CA: 'California',
		CO: 'Colorado', CT: 'Connecticut', DE: 'Delaware', FL: 'Florida', GA: 'Georgia',
		HI: 'Hawaii', ID: 'Idaho', IL: 'Illinois', IN: 'Indiana', IA: 'Iowa',
		KS: 'Kansas', KY: 'Kentucky', LA: 'Louisiana', ME: 'Maine', MD: 'Maryland',
		MA: 'Massachusetts', MI: 'Michigan', MN: 'Minnesota', MS: 'Mississippi', MO: 'Missouri',
		MT: 'Montana', NE: 'Nebraska', NV: 'Nevada', NH: 'New Hampshire', NJ: 'New Jersey',
		NM: 'New Mexico', NY: 'New York', NC: 'North Carolina', ND: 'North Dakota', OH: 'Ohio',
		OK: 'Oklahoma', OR: 'Oregon', PA: 'Pennsylvania', RI: 'Rhode Island', SC: 'South Carolina',
		SD: 'South Dakota', TN: 'Tennessee', TX: 'Texas', UT: 'Utah', VT: 'Vermont',
		VA: 'Virginia', WA: 'Washington', WV: 'West Virginia', WI: 'Wisconsin', WY: 'Wyoming'
	};

	const TOPIC_COLORS: Record<string, string> = {
		'Housing': 'var(--topic-housing)',
		'Transportation': 'var(--topic-transportation)',
		'Public Safety': 'var(--topic-public-safety)',
		'Budget': 'var(--topic-budget)',
		'Environment': 'var(--topic-environment)',
		'Zoning': 'var(--topic-zoning)',
		'Education': 'var(--topic-education)',
		'Infrastructure': 'var(--topic-infrastructure)',
		'Health': 'var(--topic-health)',
		'Business': 'var(--topic-business)',
		'Parks': 'var(--topic-parks)',
		'Utilities': 'var(--topic-utilities)',
		'Labor': 'var(--topic-labor)',
		'Technology': 'var(--topic-technology)',
		'Culture': 'var(--topic-culture)',
		'Governance': 'var(--topic-governance)',
	};

	function topicColor(topic: string): string {
		return TOPIC_COLORS[topic] || 'var(--topic-default)';
	}

	const stateName = $derived(STATE_NAMES[data.stateCode] || data.stateCode);

	function formatMeetingTime(dateStr: string | null): string {
		if (!dateStr) return '';
		const date = new Date(dateStr);
		const hours = date.getHours();
		const minutes = date.getMinutes();
		if (hours === 0 && minutes === 0) return '';
		return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
	}

	// Group meetings by date
	const meetingsByDate = $derived.by(() => {
		if (!data.meetings?.meetings) return new Map();

		const grouped = new Map<string, typeof data.meetings.meetings>();

		for (const meeting of data.meetings.meetings) {
			const dateKey = meeting.date
				? new Date(meeting.date).toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })
				: 'Date TBD';

			if (!grouped.has(dateKey)) {
				grouped.set(dateKey, []);
			}
			grouped.get(dateKey)!.push(meeting);
		}

		return grouped;
	});
</script>

<SeoHead
	title="Upcoming Meetings in {stateName} - engagic"
	description="View all upcoming city council and government meetings across {stateName}"
	url="https://engagic.org/state/{data.stateCode}/meetings"
/>

<div class="meetings-page">
	<div class="meetings-container">
		<div class="breadcrumb">
			<a href="/state/{data.stateCode.toLowerCase()}" class="breadcrumb-link">← Back to {stateName}</a>
		</div>

		<header class="page-header">
			<div class="header-label">All Meetings</div>
			<h1 class="page-title">{stateName}</h1>
			<p class="page-subtitle">
				{data.meetings?.total || 0} upcoming meetings across all cities
			</p>
		</header>

		{#if data.meetings && data.meetings.meetings.length > 0}
			<div class="meetings-timeline">
				{#each [...meetingsByDate.entries()] as [dateLabel, meetings] (dateLabel)}
					<div class="date-group">
						<div class="section-rule">
							<span>{dateLabel}</span>
							<span class="section-rule-count">{meetings.length} meeting{meetings.length !== 1 ? 's' : ''}</span>
						</div>
						<div class="meetings-list">
							{#each meetings as meeting (meeting.id)}
								{@const meetingSlug = generateMeetingSlug(meeting)}
								<a href="/{meeting.city_banana}/{meetingSlug}" class="meeting-item hover-indent">
									<div class="meeting-item-meta">
										<div class="meeting-item-meta-left">
											<span class="meeting-item-city">{meeting.city_name}</span>
											<span class="meeting-item-body">{meeting.title}</span>
										</div>
										<span class="meeting-item-time">
											{#if formatMeetingTime(meeting.date)}
												{formatMeetingTime(meeting.date)}
											{:else}
												Time TBD
											{/if}
										</span>
									</div>
									<div class="meeting-item-footer">
										{#if meeting.has_items || meeting.summary}
											<span class="status-badge status-ai">AI Summary</span>
										{:else if meeting.agenda_url}
											<span class="status-badge status-agenda">Agenda</span>
										{:else if meeting.packet_url}
											<span class="status-badge status-packet">Packet</span>
										{:else}
											<span class="status-badge status-pending">Pending</span>
										{/if}
										{#if meeting.topics && meeting.topics.length > 0}
											<div class="meeting-topics">
												{#each meeting.topics.slice(0, 3) as topic}
													<span class="topic-label" style="color: {topicColor(topic)}">{topic}</span>
												{/each}
											</div>
										{/if}
										{#if meeting.participation?.email || meeting.participation?.virtual_url}
											<span class="comment-badge">Public comment</span>
										{/if}
									</div>
								</a>
							{/each}
						</div>
					</div>
				{/each}
			</div>
		{:else}
			<div class="empty-state">
				<p class="empty-title">No upcoming meetings</p>
				<p class="empty-subtitle">There are no scheduled meetings across {stateName} at this time.</p>
				<a href="/state/{data.stateCode.toLowerCase()}" class="back-link">← Back to {stateName} overview</a>
			</div>
		{/if}
	</div>

	<Footer />
</div>

<style>
	.meetings-page {
		width: 100%;
		min-height: 100vh;
		display: flex;
		flex-direction: column;
		padding: 40px 24px 100px;
	}

	.meetings-container {
		width: 100%;
		max-width: var(--width-state);
		margin: 0 auto;
	}

	.breadcrumb {
		margin-bottom: 2rem;
	}

	.breadcrumb-link {
		font-family: var(--font-mono);
		font-size: 0.9rem;
		font-weight: 500;
		color: var(--text-link);
		text-decoration: none;
		transition: color var(--transition-normal);
	}

	.breadcrumb-link:hover {
		color: var(--civic-accent);
		text-decoration: underline;
	}

	.page-header {
		margin-bottom: 2.5rem;
	}

	.header-label {
		font-family: var(--font-body);
		font-size: 0.7rem;
		font-weight: 700;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--civic-gray);
		margin-bottom: 0.5rem;
	}

	.page-title {
		font-family: var(--font-display);
		font-size: clamp(2rem, 5vw, 2.75rem);
		font-weight: 400;
		color: var(--text-primary);
		margin: 0;
		letter-spacing: -0.02em;
		line-height: 1.05;
	}

	.page-subtitle {
		font-family: var(--font-body);
		font-size: 0.875rem;
		color: var(--civic-gray);
		margin-top: 0.625rem;
	}

	.meetings-timeline {
		display: flex;
		flex-direction: column;
		gap: 2.5rem;
	}

	.section-rule {
		font-family: var(--font-body);
		font-size: 0.7rem;
		font-weight: 700;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--civic-gray);
		padding-bottom: 0.5rem;
		border-bottom: 2px solid var(--text-primary);
		margin-bottom: 0;
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.section-rule-count {
		font-weight: 400;
	}

	.meetings-list {
		display: flex;
		flex-direction: column;
	}

	.hover-indent {
		transition: padding-left 0.15s ease;
	}

	.hover-indent:hover {
		padding-left: 6px;
	}

	.meeting-item {
		display: block;
		padding: 1rem 0;
		border-bottom: 1px solid var(--border-primary);
		text-decoration: none;
		color: inherit;
		cursor: pointer;
	}

	.meeting-item-meta {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.5rem;
		gap: 0.75rem;
	}

	.meeting-item-meta-left {
		display: flex;
		align-items: center;
		gap: 0.625rem;
		flex: 1;
		min-width: 0;
	}

	.meeting-item-city {
		font-family: var(--font-mono);
		font-size: 0.75rem;
		font-weight: 700;
		color: var(--civic-blue);
		flex-shrink: 0;
	}

	.meeting-item-body {
		font-family: var(--font-display);
		font-size: 1.05rem;
		font-weight: 400;
		color: var(--text-primary);
		line-height: 1.3;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.meeting-item-time {
		font-family: var(--font-mono);
		font-size: 0.7rem;
		color: var(--civic-gray);
		white-space: nowrap;
		flex-shrink: 0;
	}

	.meeting-item-footer {
		display: flex;
		align-items: center;
		gap: 0.625rem;
		flex-wrap: wrap;
	}

	.status-badge {
		font-family: var(--font-mono);
		font-size: 0.55rem;
		font-weight: 700;
		padding: 0.125rem 0.375rem;
		border-radius: var(--radius-xs);
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	.status-ai {
		background: var(--badge-green-bg);
		color: var(--badge-green-text);
		border: 1px solid var(--badge-green-border);
	}

	.status-agenda {
		background: var(--badge-yellow-bg, rgba(234, 179, 8, 0.1));
		color: var(--badge-yellow-text, #a16207);
		border: 1px solid var(--badge-yellow-border, rgba(234, 179, 8, 0.3));
	}

	.status-packet {
		background: var(--badge-orange-bg, rgba(249, 115, 22, 0.1));
		color: var(--badge-orange-text, #c2410c);
		border: 1px solid var(--badge-orange-border, rgba(249, 115, 22, 0.3));
	}

	.status-pending {
		background: var(--surface-secondary);
		color: var(--text-tertiary, var(--civic-gray));
		border: 1px solid var(--border-primary);
	}

	.meeting-topics {
		display: flex;
		gap: 0.375rem;
		flex-wrap: wrap;
	}

	.topic-label {
		font-size: 0.55rem;
		font-family: var(--font-body);
		font-weight: 700;
		letter-spacing: 0.04em;
		text-transform: uppercase;
	}

	.comment-badge {
		font-size: 0.625rem;
		font-family: var(--font-mono);
		font-weight: 600;
		color: var(--civic-blue);
	}

	.empty-state {
		text-align: center;
		padding: 4rem 2rem;
		background: var(--surface-secondary);
		border: 1px solid var(--border-primary);
		border-radius: var(--radius-md);
	}

	.empty-title {
		font-family: var(--font-mono);
		font-size: 1.25rem;
		font-weight: 600;
		color: var(--text-primary);
		margin-bottom: 0.5rem;
	}

	.empty-subtitle {
		font-family: var(--font-mono);
		font-size: 0.9rem;
		color: var(--civic-gray);
		margin-bottom: 1.5rem;
	}

	.back-link {
		font-family: var(--font-mono);
		font-size: 0.9rem;
		font-weight: 600;
		color: var(--civic-blue);
		text-decoration: none;
	}

	.back-link:hover {
		text-decoration: underline;
	}

	@media (max-width: 640px) {
		.meetings-page {
			padding: 1rem 0.75rem 3rem;
		}

		.page-title {
			font-size: clamp(1.5rem, 7vw, 2rem);
		}

		.meeting-item-meta {
			flex-direction: column;
			align-items: flex-start;
			gap: 0.25rem;
		}

		.meeting-item-body {
			white-space: normal;
			font-size: 0.95rem;
		}
	}
</style>
