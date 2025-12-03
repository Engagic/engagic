<script lang="ts">
	import type { MatterStatus } from '$lib/api/types';

	interface Props {
		status: MatterStatus | undefined;
		size?: 'small' | 'medium';
	}

	let { status, size = 'medium' }: Props = $props();

	const statusConfig: Record<MatterStatus, { label: string; variant: string }> = {
		passed: { label: 'Passed', variant: 'success' },
		enacted: { label: 'Enacted', variant: 'success' },
		failed: { label: 'Failed', variant: 'danger' },
		vetoed: { label: 'Vetoed', variant: 'danger' },
		active: { label: 'Active', variant: 'info' },
		tabled: { label: 'Tabled', variant: 'warning' },
		referred: { label: 'Referred', variant: 'warning' },
		withdrawn: { label: 'Withdrawn', variant: 'neutral' },
		amended: { label: 'Amended', variant: 'info' }
	};

	const config = $derived(status ? statusConfig[status] : null);
</script>

{#if config}
	<span class="status-badge {config.variant} {size}">
		{config.label}
	</span>
{/if}

<style>
	.status-badge {
		font-family: 'IBM Plex Mono', monospace;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.5px;
		border-radius: 6px;
		border: 1px solid;
		display: inline-flex;
		align-items: center;
		white-space: nowrap;
	}

	.medium {
		font-size: 0.75rem;
		padding: 0.35rem 0.7rem;
	}

	.small {
		font-size: 0.65rem;
		padding: 0.2rem 0.5rem;
	}

	/* Success: passed, enacted */
	.success {
		background: var(--badge-green-bg);
		border-color: var(--badge-green-border);
		color: var(--badge-green-text);
	}

	/* Danger: failed, vetoed */
	.danger {
		background: #fee2e2;
		border-color: #fca5a5;
		color: #991b1b;
	}

	:global(.dark) .danger {
		background: #7f1d1d;
		border-color: #ef4444;
		color: #fca5a5;
	}

	/* Info: active, amended */
	.info {
		background: var(--badge-blue-bg);
		border-color: var(--badge-blue-border);
		color: var(--badge-blue-text);
	}

	/* Warning: tabled, referred */
	.warning {
		background: var(--badge-procedural-bg);
		border-color: var(--badge-procedural-border);
		color: var(--badge-procedural-text);
	}

	/* Neutral: withdrawn */
	.neutral {
		background: var(--surface-secondary);
		border-color: var(--border-primary);
		color: var(--text-secondary);
	}
</style>
