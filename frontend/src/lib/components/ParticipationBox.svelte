<script lang="ts">
	import type { Meeting } from '$lib/api/types';

	interface Props {
		participation: NonNullable<Meeting['participation']>;
	}

	let { participation: p }: Props = $props();

	const hasParticipation = $derived(p.virtual_url || p.email || p.phone);
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
				</div>

				{#if hasStreaming && showStreamingOnMobile}
					<div class="streaming-section-mobile">
						<div class="streaming-divider"></div>
						<div class="streaming-header-mobile">
							<span class="streaming-label-mobile">Watch Live</span>
						</div>
						<div class="streaming-content-mobile">
							{#each p.streaming_urls as stream}
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
					{#each p.streaming_urls as stream}
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
		margin: var(--space-lg) 0;
		align-items: stretch;
		border-radius: var(--radius-lg);
		overflow: hidden;
	}

	.participation-box {
		flex: 1;
		padding: var(--space-lg);
		background: var(--surface-warm);
		border: 2px solid var(--action-coral);
		border-right: 1px solid var(--action-coral);
		border-radius: var(--radius-lg) 0 0 var(--radius-lg);
		transition: all var(--transition-normal);
	}

	:global(.dark) .participation-box {
		background: rgba(249, 115, 22, 0.1);
		border-color: var(--action-coral);
	}

	.viewing-box {
		flex: 1;
		padding: var(--space-md) var(--space-lg);
		background: var(--surface-secondary);
		border: 2px solid var(--border-primary);
		border-left: 1px solid var(--border-primary);
		border-radius: 0 var(--radius-lg) var(--radius-lg) 0;
		transition: all var(--transition-normal);
	}

	:global(.dark) .viewing-box {
		background: var(--surface-secondary);
		border-color: var(--border-primary);
	}

	.viewing-header {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		margin-bottom: var(--space-sm);
	}

	.viewing-label {
		font-family: var(--font-body);
		font-weight: var(--font-semibold);
		color: var(--text-muted);
		font-size: var(--text-xs);
		text-transform: uppercase;
		letter-spacing: 0.03em;
		transition: color var(--transition-fast);
	}

	:global(.dark) .viewing-label {
		color: var(--text-muted);
	}

	.viewing-content {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
	}

	.streaming-item {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
	}

	.viewing-link {
		color: var(--text);
		text-decoration: none;
		font-family: var(--font-body);
		font-size: var(--text-sm);
		font-weight: var(--font-medium);
		transition: color var(--transition-fast);
	}

	:global(.dark) .viewing-link {
		color: var(--text);
	}

	.viewing-link:hover {
		color: var(--action-coral);
		text-decoration: underline;
	}

	.viewing-text {
		color: var(--text);
		font-family: var(--font-body);
		font-size: var(--text-sm);
		font-weight: var(--font-medium);
	}

	.viewing-icon {
		font-size: 0.9rem;
		flex-shrink: 0;
	}

	@media (max-width: 768px) {
		.info-row {
			flex-direction: column;
			gap: var(--space-md);
			border-radius: 0;
			overflow: visible;
		}

		.participation-box {
			border: 2px solid var(--action-coral);
			border-radius: var(--radius-lg);
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
		gap: var(--space-sm);
		margin-bottom: var(--space-sm);
	}

	.participation-header-left {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		flex-wrap: wrap;
	}

	.participation-label {
		font-family: var(--font-body);
		font-weight: var(--font-bold);
		color: var(--action-coral);
		font-size: var(--text-sm);
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}

	:global(.dark) .participation-label {
		color: var(--action-coral);
	}

	.streaming-toggle-mobile {
		display: none;
		flex-shrink: 0;
		width: 1.75rem;
		height: 1.75rem;
		background: transparent;
		border: 1.5px solid var(--action-coral);
		border-radius: var(--radius-sm);
		color: var(--action-coral);
		font-size: 1.1rem;
		font-weight: 400;
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	:global(.dark) .streaming-toggle-mobile {
		border-color: var(--action-coral);
		color: var(--action-coral);
	}

	.streaming-toggle-mobile:hover {
		background: var(--action-coral);
		color: white;
	}

	.streaming-section-mobile {
		display: none;
		margin-top: var(--space-md);
		padding-top: var(--space-md);
	}

	.streaming-divider {
		height: 1px;
		background: var(--action-coral);
		margin-bottom: var(--space-sm);
		opacity: 0.3;
	}

	.streaming-header-mobile {
		margin-bottom: var(--space-sm);
	}

	.streaming-label-mobile {
		font-family: var(--font-body);
		font-weight: var(--font-semibold);
		color: var(--action-coral);
		font-size: var(--text-xs);
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}

	:global(.dark) .streaming-label-mobile {
		color: var(--action-coral);
	}

	.streaming-content-mobile {
		display: flex;
		flex-direction: column;
		gap: var(--space-sm);
	}

	.viewing-box-desktop {
		display: flex;
		flex-direction: column;
	}

	.participation-badge {
		padding: 0.2rem 0.6rem;
		border-radius: var(--radius-full);
		font-size: var(--text-xs);
		font-weight: var(--font-medium);
		font-family: var(--font-body);
	}

	.badge-hybrid {
		background: var(--surface-warm);
		color: var(--action-coral);
		border: 1px solid var(--action-coral);
	}

	.badge-virtual {
		background: var(--surface-secondary);
		color: var(--text-muted);
		border: 1px solid var(--border-primary);
	}

	.participation-content {
		display: flex;
		flex-direction: column;
		gap: var(--space-sm);
	}

	.participation-item {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		flex-wrap: wrap;
	}

	.participation-icon {
		font-size: 1rem;
		flex-shrink: 0;
	}

	.participation-link {
		color: var(--text);
		text-decoration: none;
		font-family: var(--font-body);
		font-size: var(--text-sm);
		font-weight: var(--font-medium);
		transition: color var(--transition-fast);
	}

	:global(.dark) .participation-link {
		color: var(--text);
	}

	.participation-link:hover {
		color: var(--action-coral);
		text-decoration: underline;
	}

	.meeting-id {
		color: var(--text-muted);
		font-size: var(--text-xs);
		font-family: var(--font-mono);
		margin-left: var(--space-sm);
	}

	:global(.dark) .meeting-id {
		color: var(--text-muted);
	}

	.participation-text {
		color: var(--text);
		font-family: var(--font-body);
		font-size: var(--text-sm);
		font-weight: var(--font-medium);
	}

	:global(.dark) .participation-text {
		color: var(--text);
	}
</style>
