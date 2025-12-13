<script lang="ts">
	import type { Meeting } from '$lib/api/types';

	interface Props {
		status: Meeting['meeting_status'];
	}

	let { status }: Props = $props();

	const statusClass = $derived(status === 'revised' ? 'meeting-info-banner' : 'meeting-alert-banner');
	const iconSymbol = $derived(status === 'revised' ? 'i' : '!');
</script>

{#if status}
	<div class={statusClass}>
		<span class="alert-icon">{iconSymbol}</span>
		<span class="alert-text">This meeting has been {status}</span>
	</div>
{/if}

<style>
	.meeting-alert-banner {
		background: #fef2f2;
		border: 1px solid #fecaca;
		border-radius: 6px;
		padding: 0.75rem 1rem;
		margin-bottom: 1.5rem;
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.meeting-info-banner {
		background: #eff6ff;
		border: 1px solid #bfdbfe;
		border-radius: 6px;
		padding: 0.75rem 1rem;
		margin-bottom: 1.5rem;
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.alert-icon {
		flex-shrink: 0;
		width: 24px;
		height: 24px;
		background: #dc2626;
		color: white;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		font-weight: 700;
		font-size: 0.9rem;
	}

	.meeting-info-banner .alert-icon {
		background: #2563eb;
	}

	.alert-text {
		color: #991b1b;
		font-weight: 600;
		font-size: 0.95rem;
		text-transform: capitalize;
	}

	.meeting-info-banner .alert-text {
		color: #1e40af;
	}

	:global(.dark) .meeting-alert-banner {
		background: #450a0a;
		border-color: #991b1b;
	}

	:global(.dark) .meeting-info-banner {
		background: #1e3a5f;
		border-color: #3b82f6;
	}

	:global(.dark) .alert-icon {
		background: #ef4444;
	}

	:global(.dark) .meeting-info-banner .alert-icon {
		background: #3b82f6;
	}

	:global(.dark) .alert-text {
		color: #fca5a5;
	}

	:global(.dark) .meeting-info-banner .alert-text {
		color: #93c5fd;
	}
</style>
