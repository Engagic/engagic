<script lang="ts">
	import { generateMeetingSlug } from '$lib/utils/utils';
	import Footer from '$lib/components/Footer.svelte';
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

	const stateName = $derived(STATE_NAMES[data.stateCode] || data.stateCode);

	function formatMeetingDate(dateStr: string | null): string {
		if (!dateStr) return 'TBD';
		const date = new Date(dateStr);
		const now = new Date();
		const diffDays = Math.floor((date.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));

		if (diffDays === 0) return 'Today';
		if (diffDays === 1) return 'Tomorrow';
		return date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
	}

	function formatMeetingTime(dateStr: string | null): string {
		if (!dateStr) return '';
		const date = new Date(dateStr);
		const hours = date.getHours();
		const minutes = date.getMinutes();
		if (hours === 0 && minutes === 0) return '';
		return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
	}

	// Group meetings by date for better organization
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

<svelte:head>
	<title>Upcoming Meetings in {stateName} - engagic</title>
	<meta name="description" content="View all upcoming city council and government meetings across {stateName}" />
	<link rel="canonical" href="https://engagic.org/state/{data.stateCode}/meetings" />

	<meta property="og:title" content="Upcoming Meetings in {stateName} - engagic" />
	<meta property="og:description" content="View all upcoming city council and government meetings across {stateName}" />
	<meta property="og:type" content="website" />
	<meta property="og:url" content="https://engagic.org/state/{data.stateCode}/meetings" />
	<meta property="og:image" content="https://engagic.org/icon-512.png" />
	<meta property="og:site_name" content="engagic" />
	<meta name="twitter:card" content="summary" />
	<meta name="twitter:title" content="Upcoming Meetings in {stateName} - engagic" />
	<meta name="twitter:description" content="View all upcoming city council and government meetings across {stateName}" />
	<meta name="twitter:image" content="https://engagic.org/icon-512.png" />
</svelte:head>

<div class="meetings-page">
	<div class="meetings-container">
		<div class="breadcrumb">
			<a href="/state/{data.stateCode.toLowerCase()}" class="breadcrumb-link">← Back to {stateName}</a>
		</div>

		<div class="page-header">
			<h1 class="page-title">Upcoming Meetings in {stateName}</h1>
			<p class="page-subtitle">
				{data.meetings?.total || 0} upcoming meetings across all cities
			</p>
		</div>

		{#if data.meetings && data.meetings.meetings.length > 0}
			<div class="meetings-timeline">
				{#each [...meetingsByDate.entries()] as [dateLabel, meetings] (dateLabel)}
					<div class="date-group">
						<div class="date-header">
							<span class="date-label">{dateLabel}</span>
							<span class="meeting-count">{meetings.length} meeting{meetings.length !== 1 ? 's' : ''}</span>
						</div>
						<div class="meetings-list">
							{#each meetings as meeting (meeting.id)}
								{@const meetingSlug = generateMeetingSlug(meeting)}
								<a href="/{meeting.city_banana}/{meetingSlug}" class="meeting-card">
									<div class="meeting-card-header">
										<span class="city-badge">{meeting.city_name}</span>
										<span class="meeting-time-badge">
											{#if formatMeetingTime(meeting.date)}
												{formatMeetingTime(meeting.date)}
											{:else}
												Time TBD
											{/if}
										</span>
									</div>
									<div class="meeting-title">{meeting.title}</div>
									<div class="meeting-footer">
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
													<span class="topic-tag">{topic}</span>
												{/each}
											</div>
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
				<div class="empty-title">No upcoming meetings</div>
				<div class="empty-subtitle">There are no scheduled meetings across {stateName} at this time.</div>
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
		padding: 2rem 1rem;
	}

	.meetings-container {
		width: 100%;
		max-width: 900px;
		margin: 0 auto;
	}

	.breadcrumb {
		margin-bottom: 1.5rem;
	}

	.breadcrumb-link {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
		color: var(--text-link);
		text-decoration: none;
		transition: color 0.2s ease;
		font-weight: 500;
	}

	.breadcrumb-link:hover {
		color: var(--civic-accent);
		text-decoration: underline;
	}

	.page-header {
		margin-bottom: 2rem;
		padding-bottom: 1.5rem;
		border-bottom: 2px solid var(--border-primary);
	}

	.page-title {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 2rem;
		font-weight: 700;
		color: var(--text-primary);
		margin: 0 0 0.5rem 0;
	}

	.page-subtitle {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
		color: var(--civic-gray);
		margin: 0;
	}

	.meetings-timeline {
		display: flex;
		flex-direction: column;
		gap: 2rem;
	}

	.date-group {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.date-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 0.75rem 1rem;
		background: var(--surface-secondary);
		border-radius: 8px;
		border-left: 4px solid var(--civic-blue);
	}

	.date-label {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.95rem;
		font-weight: 600;
		color: var(--text-primary);
	}

	.meeting-count {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8rem;
		color: var(--civic-gray);
	}

	.meetings-list {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		padding-left: 1rem;
	}

	.meeting-card {
		display: block;
		background: var(--surface-primary);
		border: 1px solid var(--border-primary);
		border-radius: 8px;
		padding: 1rem 1.25rem;
		text-decoration: none;
		transition: all 0.2s ease;
	}

	.meeting-card:hover {
		border-color: var(--civic-blue);
		box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
		transform: translateX(4px);
	}

	.meeting-card-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.5rem;
		gap: 0.75rem;
		flex-wrap: wrap;
	}

	.city-badge {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		font-weight: 700;
		color: var(--badge-purple-text, var(--civic-blue));
		background: var(--badge-purple-bg, rgba(139, 92, 246, 0.1));
		padding: 0.25rem 0.6rem;
		border-radius: 6px;
		border: 1px solid var(--badge-purple-border, rgba(139, 92, 246, 0.3));
	}

	.meeting-time-badge {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--civic-gray);
	}

	.meeting-title {
		font-family: Georgia, 'Times New Roman', Times, serif;
		font-size: 1rem;
		line-height: 1.4;
		color: var(--text-primary);
		margin-bottom: 0.75rem;
	}

	.meeting-footer {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		flex-wrap: wrap;
	}

	.status-badge {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.65rem;
		font-weight: 600;
		padding: 0.2rem 0.5rem;
		border-radius: 4px;
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}

	.status-badge.status-ai {
		background: var(--badge-green-bg);
		color: var(--badge-green-text);
		border: 1px solid var(--badge-green-border);
	}

	.status-badge.status-agenda {
		background: var(--badge-yellow-bg, rgba(234, 179, 8, 0.1));
		color: var(--badge-yellow-text, #a16207);
		border: 1px solid var(--badge-yellow-border, rgba(234, 179, 8, 0.3));
	}

	.status-badge.status-packet {
		background: var(--badge-orange-bg, rgba(249, 115, 22, 0.1));
		color: var(--badge-orange-text, #c2410c);
		border: 1px solid var(--badge-orange-border, rgba(249, 115, 22, 0.3));
	}

	.status-badge.status-pending {
		background: var(--surface-secondary);
		color: var(--civic-gray);
		border: 1px solid var(--border-primary);
	}

	.meeting-topics {
		display: flex;
		gap: 0.3rem;
		flex-wrap: wrap;
	}

	.topic-tag {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.65rem;
		padding: 0.2rem 0.5rem;
		background: var(--surface-secondary);
		color: var(--civic-gray);
		border-radius: 4px;
		font-weight: 500;
	}

	.empty-state {
		text-align: center;
		padding: 4rem 2rem;
		background: var(--surface-secondary);
		border: 1px solid var(--border-primary);
		border-radius: 12px;
	}

	.empty-title {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.25rem;
		font-weight: 600;
		color: var(--text-primary);
		margin-bottom: 0.5rem;
	}

	.empty-subtitle {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
		color: var(--civic-gray);
		margin-bottom: 1.5rem;
	}

	.back-link {
		font-family: 'IBM Plex Mono', monospace;
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
			padding: 1rem 0.5rem;
		}

		.page-title {
			font-size: 1.5rem;
		}

		.meetings-list {
			padding-left: 0;
		}

		.meeting-card {
			padding: 0.875rem 1rem;
		}

		.meeting-card-header {
			flex-direction: column;
			align-items: flex-start;
			gap: 0.5rem;
		}

		.date-header {
			flex-direction: column;
			align-items: flex-start;
			gap: 0.25rem;
		}
	}
</style>
