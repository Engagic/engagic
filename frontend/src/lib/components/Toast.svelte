<script lang="ts">
	import { toastStore } from '$lib/stores/toast.svelte';
</script>

{#if toastStore.toasts.length > 0}
	<div class="toast-container">
		{#each toastStore.toasts as toast (toast.id)}
			<div class="toast toast-{toast.type}" role="alert">
				<span class="toast-message">{toast.message}</span>
				<button
					class="toast-dismiss"
					onclick={() => toastStore.dismiss(toast.id)}
					aria-label="Dismiss"
				>
					&times;
				</button>
			</div>
		{/each}
	</div>
{/if}

<style>
	.toast-container {
		position: fixed;
		bottom: 1.5rem;
		right: 1.5rem;
		z-index: 9999;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		max-width: 360px;
	}

	.toast {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		padding: 0.875rem 1rem;
		border-radius: var(--radius-md);
		font-size: 0.9375rem;
		font-weight: 500;
		box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
		animation: slide-in 0.2s ease-out;
		will-change: transform, opacity;
	}

	.toast-success {
		background: var(--civic-green);
		color: white;
	}

	.toast-error {
		background: var(--civic-red);
		color: white;
	}

	.toast-info {
		background: var(--civic-blue);
		color: white;
	}

	.toast-message {
		flex: 1;
	}

	.toast-dismiss {
		background: transparent;
		border: none;
		color: inherit;
		font-size: 1.25rem;
		line-height: 1;
		padding: 0;
		cursor: pointer;
		opacity: 0.8;
		transition: opacity var(--transition-fast);
	}

	.toast-dismiss:hover {
		opacity: 1;
	}

	@keyframes slide-in {
		from {
			transform: translateX(100%);
			opacity: 0;
		}
		to {
			transform: translateX(0);
			opacity: 1;
		}
	}

	@media (max-width: 480px) {
		.toast-container {
			left: 1rem;
			right: 1rem;
			bottom: 1rem;
			max-width: none;
		}
	}
</style>
