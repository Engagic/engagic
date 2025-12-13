<script lang="ts">
	import type { Meeting, CityParticipation } from '$lib/api/types';

	interface Props {
		participation: NonNullable<Meeting['participation']>;
		cityParticipation?: CityParticipation;  // City-level config (replaces meeting-level for testimony)
	}

	let { participation: p, cityParticipation: cp }: Props = $props();

	// City-level participation takes priority for testimony/contact
	const hasCityParticipation = $derived(cp?.testimony_url || cp?.testimony_email);

	// Meeting-level contact info (used as fallback when no city config)
	const hasMeetingContact = $derived(p.virtual_url || p.email || p.phone);

	// Always show something if we have any participation data
	const hasParticipation = $derived(hasCityParticipation || hasMeetingContact);
	const hasStreaming = $derived(p.streaming_urls && p.streaming_urls.length > 0);
	let showStreamingOnMobile = $state(false);
</script>

{#if hasParticipation || hasStreaming}
	<div class="info-row">
		{#if hasParticipation}
			<div class="participation-box">
				<div class="participation-header">
					<div class="participation-header-left">
						<span class="participation-label">How to Participate</span>
						{#if p.is_hybrid}
							<span class="participation-badge badge-hybrid">Hybrid Meeting</span>
						{:else if p.is_virtual_only}
							<span class="participation-badge badge-virtual">Virtual Only</span>
						{/if}
					</div>
					{#if hasStreaming}
						<button
							class="streaming-toggle-mobile"
							onclick={() => showStreamingOnMobile = !showStreamingOnMobile}
							aria-label="Toggle streaming links"
						>
							{showStreamingOnMobile ? '−' : '+'}
						</button>
					{/if}
				</div>
				<div class="participation-content">
					{#if hasCityParticipation}
						<!-- City-level participation (official testimony process) -->
						{#if cp?.testimony_url}
							<div class="participation-item">
								<span class="participation-icon">📝</span>
								<a href={cp.testimony_url} target="_blank" rel="noopener noreferrer" class="participation-link">
									Submit Testimony
								</a>
							</div>
						{/if}
						{#if cp?.testimony_email}
							<div class="participation-item">
								<span class="participation-icon">✉️</span>
								<a href="mailto:{cp.testimony_email}" class="participation-link">
									{cp.testimony_email}
								</a>
							</div>
						{/if}
						{#if cp?.process_url && cp.process_url !== cp.testimony_url}
							<div class="participation-item">
								<span class="participation-icon">📖</span>
								<a href={cp.process_url} target="_blank" rel="noopener noreferrer" class="participation-link">
									How to Testify
								</a>
							</div>
						{/if}
					{:else}
						<!-- Fallback: meeting-level contact info -->
						{#if p.email}
							<div class="participation-item">
								<span class="participation-icon">✉️</span>
								<a href="mailto:{p.email}" class="participation-link">
									{p.email}
								</a>
							</div>
						{/if}
						{#if p.phone}
							<div class="participation-item">
								<span class="participation-icon">📞</span>
								<a href="tel:{p.phone}" class="participation-link">
									{p.phone}
								</a>
							</div>
						{/if}
					{/if}
					<!-- Always show meeting-specific virtual link (Zoom, etc.) -->
					{#if p.virtual_url}
						<div class="participation-item">
							<span class="participation-icon">📹</span>
							<a href={p.virtual_url} target="_blank" rel="noopener noreferrer" class="participation-link">
								Join Virtual Meeting
							</a>
							{#if p.meeting_id}
								<span class="meeting-id">Meeting ID: {p.meeting_id}</span>
							{/if}
						</div>
					{/if}
				</div>

				{#if hasStreaming && showStreamingOnMobile}
					<div class="streaming-section-mobile">
						<div class="streaming-divider"></div>
						<div class="streaming-header-mobile">
							<span class="streaming-label-mobile">Watch Live</span>
						</div>
						<div class="streaming-content-mobile">
							{#each p.streaming_urls ?? [] as stream}
								<div class="streaming-item">
									<span class="viewing-icon">📺</span>
									{#if stream.url}
										<a href={stream.url} target="_blank" rel="noopener noreferrer" class="participation-link">
											Watch on {stream.platform}
										</a>
									{:else if stream.channel}
										<span class="participation-text">
											{stream.platform} Channel {stream.channel}
										</span>
									{/if}
								</div>
							{/each}
						</div>
					</div>
				{/if}
			</div>
		{/if}

		{#if hasStreaming}
			<div class="viewing-box viewing-box-desktop">
				<div class="viewing-header">
					<span class="viewing-label">Watch Live</span>
				</div>
				<div class="viewing-content">
					{#each p.streaming_urls ?? [] as stream}
						<div class="streaming-item">
							<span class="viewing-icon">📺</span>
							{#if stream.url}
								<a href={stream.url} target="_blank" rel="noopener noreferrer" class="viewing-link">
									Watch on {stream.platform}
								</a>
							{:else if stream.channel}
								<span class="viewing-text">
									{stream.platform} Channel {stream.channel}
								</span>
							{/if}
						</div>
					{/each}
				</div>
			</div>
		{/if}
	</div>
{/if}

<style>
	.info-row {
		display: flex;
		gap: 0;
		margin: 1.5rem 0;
		align-items: stretch;
		border-radius: 6px;
		overflow: hidden;
		box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
	}

	.participation-box {
		flex: 1;
		padding: 1.25rem 1.5rem;
		background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
		border: 2px solid #22c55e;
		border-right: 1px solid #22c55e;
		border-radius: 6px 0 0 6px;
		box-shadow: none;
		transition: all 0.3s ease;
	}

	:global(.dark) .participation-box {
		background: linear-gradient(135deg, #3b0764 0%, #581c87 100%);
		border: 2px solid #c084fc;
		border-right: 1px solid #c084fc;
		box-shadow: none;
	}

	.viewing-box {
		flex: 1;
		padding: 0.85rem 1.25rem;
		background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
		border: 2px solid #93c5fd;
		border-left: 1px solid #93c5fd;
		border-radius: 0 6px 6px 0;
		box-shadow: none;
		transition: all 0.3s ease;
	}

	:global(.dark) .viewing-box {
		background: linear-gradient(135deg, #3b0764 0%, #581c87 100%);
		border: 2px solid #c084fc;
		border-left: 1px solid #c084fc;
		box-shadow: none;
	}

	.viewing-header {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-bottom: 0.5rem;
	}

	.viewing-label {
		font-family: 'IBM Plex Mono', monospace;
		font-weight: 600;
		color: #1e40af;
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.5px;
		transition: color 0.3s ease;
	}

	:global(.dark) .viewing-label {
		color: #e9d5ff;
	}

	.viewing-content {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
	}

	.streaming-item {
		display: flex;
		align-items: center;
		gap: 0.4rem;
	}

	.viewing-link {
		color: #1e40af;
		text-decoration: none;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8rem;
		font-weight: 500;
		transition: color 0.2s;
	}

	:global(.dark) .viewing-link {
		color: #f5d0fe;
	}

	.viewing-link:hover {
		color: #1e3a8a;
		text-decoration: underline;
	}

	:global(.dark) .viewing-link:hover {
		color: #fae8ff;
	}

	.viewing-text {
		color: #1e40af;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8rem;
		font-weight: 500;
		transition: color 0.3s ease;
	}

	:global(.dark) .viewing-text {
		color: #f5d0fe;
	}

	.viewing-icon {
		font-size: 0.9rem;
		flex-shrink: 0;
	}

	@media (max-width: 640px) {
		.info-row {
			flex-direction: column;
			gap: 1rem;
			border-radius: 0;
			overflow: visible;
			box-shadow: none;
		}

		.participation-box {
			border: 2px solid #22c55e;
			border-radius: 6px;
			box-shadow: 0 4px 12px rgba(34, 197, 94, 0.15);
		}

		:global(.dark) .participation-box {
			border: 2px solid #c084fc;
			box-shadow: 0 4px 12px rgba(192, 132, 252, 0.3);
		}

		.streaming-toggle-mobile {
			display: flex;
			align-items: center;
			justify-content: center;
		}

		.viewing-box-desktop {
			display: none;
		}
	}

	.participation-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		margin-bottom: 0.75rem;
	}

	.participation-header-left {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		flex-wrap: wrap;
	}

	.participation-label {
		font-family: 'IBM Plex Mono', monospace;
		font-weight: 600;
		color: #15803d;
		font-size: 0.85rem;
		text-transform: uppercase;
		letter-spacing: 0.5px;
		transition: color 0.3s ease;
	}

	:global(.dark) .participation-label {
		color: #e9d5ff;
	}

	.streaming-toggle-mobile {
		display: none;
		flex-shrink: 0;
		width: 1.75rem;
		height: 1.75rem;
		background: transparent;
		border: 1.5px solid #15803d;
		border-radius: 6px;
		color: #15803d;
		font-size: 1.1rem;
		font-weight: 400;
		cursor: pointer;
		transition: all 0.2s ease;
	}

	:global(.dark) .streaming-toggle-mobile {
		border-color: #86efac;
		color: #86efac;
	}

	.streaming-toggle-mobile:hover {
		background: #15803d;
		color: white;
	}

	:global(.dark) .streaming-toggle-mobile:hover {
		background: #86efac;
		color: #000;
	}

	.streaming-section-mobile {
		display: none;
		margin-top: 1rem;
		padding-top: 1rem;
	}

	.streaming-divider {
		height: 1px;
		background: #86efac;
		margin-bottom: 0.75rem;
		opacity: 0.3;
	}

	.streaming-header-mobile {
		margin-bottom: 0.5rem;
	}

	.streaming-label-mobile {
		font-family: 'IBM Plex Mono', monospace;
		font-weight: 600;
		color: #15803d;
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.5px;
	}

	:global(.dark) .streaming-label-mobile {
		color: #86efac;
	}

	.streaming-content-mobile {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.viewing-box-desktop {
		display: flex;
		flex-direction: column;
	}

	.participation-badge {
		padding: 0.2rem 0.6rem;
		border-radius: 12px;
		font-size: 0.75rem;
		font-weight: 500;
		font-family: 'IBM Plex Mono', monospace;
	}

	.badge-hybrid {
		background: #fef3c7;
		color: #92400e;
		border: 1px solid #fbbf24;
	}

	.badge-virtual {
		background: #dbeafe;
		color: #1e40af;
		border: 1px solid #60a5fa;
	}

	:global(.dark) .badge-hybrid {
		background: #78350f;
		color: #fef3c7;
		border-color: #b45309;
	}

	:global(.dark) .badge-virtual {
		background: #1e3a5f;
		color: #93c5fd;
		border-color: #3b82f6;
	}

	.participation-content {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.participation-item {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		flex-wrap: wrap;
	}

	.participation-icon {
		font-size: 1rem;
		flex-shrink: 0;
	}

	.participation-link {
		color: #15803d;
		text-decoration: none;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
		font-weight: 500;
		transition: color 0.2s;
	}

	:global(.dark) .participation-link {
		color: #f5d0fe;
	}

	.participation-link:hover {
		color: #166534;
		text-decoration: underline;
	}

	:global(.dark) .participation-link:hover {
		color: #fae8ff;
	}

	.meeting-id {
		color: #6b7280;
		font-size: 0.8rem;
		font-family: 'IBM Plex Mono', monospace;
		margin-left: 0.5rem;
		transition: color 0.3s ease;
	}

	:global(.dark) .meeting-id {
		color: #e9d5ff;
	}

	.participation-text {
		color: #15803d;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
		font-weight: 500;
		transition: color 0.3s ease;
	}

	:global(.dark) .participation-text {
		color: #f5d0fe;
	}
</style>
