<script lang="ts">
	import { page } from '$app/stores';
	import type { ComponentType } from 'svelte';

	export let path: string;
	export let title: string;
	export let icon: ComponentType | null = null;
	export let iconColor: 'blue' | 'green' | 'purple' | 'orange' | 'magenta' | 'red' = 'blue';

	$: isActive = $page.url.pathname === path;
</script>

<a href={path} class="page-nav-tab" class:active={isActive}>
	<div class="tab-left" style="--tab-icon-color: var(--civic-{iconColor})">
		{#if icon}
			<div class="tab-icon">
				<svelte:component this={icon} />
			</div>
		{/if}
		<div class="tab-title">
			{title}
		</div>
	</div>
	<div class="tab-chevron">
		→
	</div>
</a>

<style>
	.page-nav-tab {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.75rem 1rem;
		background: var(--surface-primary);
		border: 1px solid var(--border-primary);
		border-radius: 8px;
		text-decoration: none;
		transition: all 0.2s ease;
		cursor: pointer;
	}

	.page-nav-tab:hover {
		background: var(--surface-hover);
		border-color: var(--civic-blue);
		transform: translateX(4px);
	}

	.page-nav-tab.active {
		background: var(--tab-icon-color);
		border-color: var(--tab-icon-color);
		color: white;
		box-shadow: 0 0 0 1px var(--tab-icon-color);
	}

	.page-nav-tab.active .tab-title {
		color: white;
	}

	.page-nav-tab.active .tab-icon {
		background: rgba(255, 255, 255, 0.25);
		color: white;
	}

	.page-nav-tab.active .tab-chevron {
		color: white;
		opacity: 1;
	}

	.tab-left {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}

	.tab-icon {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 32px;
		height: 32px;
		background: var(--tab-icon-color);
		color: var(--civic-white);
		border-radius: 6px;
		flex-shrink: 0;
	}

	.tab-icon :global(svg) {
		width: 18px;
		height: 18px;
	}

	.tab-title {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.95rem;
		font-weight: 500;
		color: var(--civic-dark);
		transition: color 0.2s ease;
	}

	.tab-chevron {
		color: var(--civic-gray);
		font-size: 1.1rem;
		opacity: 0;
		transition: opacity 0.2s ease;
	}

	.page-nav-tab:hover .tab-chevron {
		opacity: 1;
	}

	.page-nav-tab.active .tab-chevron {
		opacity: 1;
	}

	/* Mobile styles */
	@media (max-width: 750px) {
		.page-nav-tab {
			padding: 0.85rem 1rem;
		}

		.tab-icon {
			width: 28px;
			height: 28px;
		}

		.tab-icon :global(svg) {
			width: 16px;
			height: 16px;
		}

		.tab-title {
			font-size: 0.9rem;
		}

		.tab-chevron {
			opacity: 1;
			font-size: 1rem;
		}
	}
</style>
