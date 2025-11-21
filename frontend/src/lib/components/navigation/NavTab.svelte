<script lang="ts">
	import { page } from '$app/state';
	import type { ComponentType } from 'svelte';

	interface Props {
		path: string;
		title: string;
		icon?: ComponentType | null;
		iconColor?: 'blue' | 'green' | 'purple' | 'orange' | 'magenta' | 'red';
	}

	let { path, title, icon = null, iconColor = 'blue' }: Props = $props();

	let isCurrentRoute = $derived(page.url.pathname === path);
</script>

<a
	href={path}
	class="nav-tab-link"
	class:is-active={isCurrentRoute}
	style="--tab-theme-color: var(--civic-{iconColor})"
>
	<div class="tab-content-left">
		{#if icon}
			<div class="tab-icon-box">
				<icon></icon>
			</div>
		{/if}
		<div class="tab-title-text">
			{title}
		</div>
	</div>
	<div class="tab-chevron-indicator">
		→
	</div>
</a>

<style>
	.nav-tab-link {
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

	.nav-tab-link:hover {
		background: var(--surface-hover);
		border-color: var(--civic-blue);
		box-shadow: 0 2px 8px var(--shadow-md);
	}

	.nav-tab-link.is-active {
		background: var(--tab-theme-color);
		border-color: var(--tab-theme-color);
		color: white;
		box-shadow: 0 0 0 1px var(--tab-theme-color);
	}

	.nav-tab-link.is-active .tab-title-text {
		color: white;
	}

	.nav-tab-link.is-active .tab-icon-box {
		background: rgba(255, 255, 255, 0.25);
		color: white;
	}

	.nav-tab-link.is-active .tab-chevron-indicator {
		color: white;
		opacity: 1;
	}

	.tab-content-left {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}

	.tab-icon-box {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 32px;
		height: 32px;
		background: var(--tab-theme-color);
		color: var(--civic-white);
		border-radius: 6px;
		flex-shrink: 0;
	}

	.tab-icon-box :global(svg) {
		width: 18px;
		height: 18px;
	}

	.tab-title-text {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.95rem;
		font-weight: 500;
		color: var(--civic-dark);
		transition: color 0.2s ease;
	}

	.tab-chevron-indicator {
		color: var(--civic-gray);
		font-size: 1.1rem;
		opacity: 0;
		transition: opacity 0.2s ease;
	}

	.nav-tab-link:hover .tab-chevron-indicator {
		opacity: 1;
	}

	.nav-tab-link.is-active .tab-chevron-indicator {
		opacity: 1;
	}

	/* Mobile adjustments */
	@media (max-width: 768px) {
		.nav-tab-link {
			padding: 0.85rem 1rem;
		}

		.tab-icon-box {
			width: 28px;
			height: 28px;
		}

		.tab-icon-box :global(svg) {
			width: 16px;
			height: 16px;
		}

		.tab-title-text {
			font-size: 0.9rem;
		}

		.tab-chevron-indicator {
			opacity: 1;
			font-size: 1rem;
		}
	}
</style>
