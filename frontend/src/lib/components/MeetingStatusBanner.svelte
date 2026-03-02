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
		background: var(--alert-bg);
		border: 1px solid var(--alert-border);
		border-radius: 6px;
		padding: 0.75rem 1rem;
		margin-bottom: 1.5rem;
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.meeting-info-banner {
		background: var(--info-bg);
		border: 1px solid var(--info-border);
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
		background: var(--alert-icon);
		color: white;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		font-weight: 700;
		font-size: 0.9rem;
	}

	.meeting-info-banner .alert-icon {
		background: var(--info-icon);
	}

	.alert-text {
		color: var(--alert-text);
		font-weight: 600;
		font-size: 0.95rem;
		text-transform: capitalize;
	}

	.meeting-info-banner .alert-text {
		color: var(--info-text);
	}
</style>
