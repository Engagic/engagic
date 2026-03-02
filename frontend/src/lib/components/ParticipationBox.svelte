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
		border-radius: var(--radius-sm);
		overflow: hidden;
		box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
	}

	.participation-box {
		flex: 1;
		padding: 1.25rem 1.5rem;
		background: var(--participation-box-bg);
		border: 2px solid var(--participation-box-border);
		border-right: 1px solid var(--participation-box-border);
		border-radius: var(--radius-sm) 0 0 var(--radius-sm);
		box-shadow: none;
		transition: all var(--transition-slow);
	}

	.viewing-box {
		flex: 1;
		padding: 0.85rem 1.25rem;
		background: var(--viewing-box-bg);
		border: 2px solid var(--viewing-box-border);
		border-left: 1px solid var(--viewing-box-border);
		border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
		box-shadow: none;
		transition: all var(--transition-slow);
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
		color: var(--viewing-label-color);
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.5px;
		transition: color var(--transition-slow);
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
		color: var(--viewing-link-color);
		text-decoration: none;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8rem;
		font-weight: 500;
		transition: color var(--transition-normal);
	}

	.viewing-link:hover {
		color: var(--viewing-link-hover);
		text-decoration: underline;
	}

	.viewing-text {
		color: var(--viewing-link-color);
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.8rem;
		font-weight: 500;
		transition: color var(--transition-slow);
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
			border: 2px solid var(--participation-box-border);
			border-radius: var(--radius-sm);
			box-shadow: 0 4px 12px rgba(34, 197, 94, 0.15);
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
		color: var(--participation-label);
		font-size: 0.85rem;
		text-transform: uppercase;
		letter-spacing: 0.5px;
		transition: color var(--transition-slow);
	}

	.streaming-toggle-mobile {
		display: none;
		flex-shrink: 0;
		width: 1.75rem;
		height: 1.75rem;
		background: transparent;
		border: 1.5px solid var(--participation-label);
		border-radius: var(--radius-sm);
		color: var(--participation-label);
		font-size: 1.1rem;
		font-weight: 400;
		cursor: pointer;
		transition: all var(--transition-normal);
	}

	.streaming-toggle-mobile:hover {
		background: var(--participation-label);
		color: white;
	}

	.streaming-section-mobile {
		display: none;
		margin-top: 1rem;
		padding-top: 1rem;
	}

	.streaming-divider {
		height: 1px;
		background: var(--participation-box-border);
		margin-bottom: 0.75rem;
		opacity: 0.3;
	}

	.streaming-header-mobile {
		margin-bottom: 0.5rem;
	}

	.streaming-label-mobile {
		font-family: 'IBM Plex Mono', monospace;
		font-weight: 600;
		color: var(--participation-label);
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.5px;
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
		border-radius: var(--radius-lg);
		font-size: 0.75rem;
		font-weight: 500;
		font-family: 'IBM Plex Mono', monospace;
	}

	.badge-hybrid {
		background: var(--badge-hybrid-bg);
		color: var(--badge-hybrid-text);
		border: 1px solid var(--badge-hybrid-border);
	}

	.badge-virtual {
		background: var(--badge-virtual-bg);
		color: var(--badge-virtual-text);
		border: 1px solid var(--badge-virtual-border);
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
		color: var(--participation-link-color);
		text-decoration: none;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
		font-weight: 500;
		transition: color var(--transition-normal);
	}

	.participation-link:hover {
		color: var(--participation-link-hover);
		text-decoration: underline;
	}

	.meeting-id {
		color: var(--text-secondary);
		font-size: 0.8rem;
		font-family: 'IBM Plex Mono', monospace;
		margin-left: 0.5rem;
		transition: color var(--transition-slow);
	}

	.participation-text {
		color: var(--participation-link-color);
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
		font-weight: 500;
		transition: color var(--transition-slow);
	}
</style>
