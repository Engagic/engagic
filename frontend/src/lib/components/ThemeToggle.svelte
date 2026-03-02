<script lang="ts">
	import { themeState } from '$lib/stores/theme.svelte';

	function getThemeLabel(theme: 'light' | 'dark' | 'system') {
		switch (theme) {
			case 'light':
				return 'Light';
			case 'dark':
				return 'Dark';
			case 'system':
				return 'System';
		}
	}
</script>

<button
	class="theme-toggle"
	onclick={() => themeState.cycleTheme()}
	aria-label={`Current theme: ${getThemeLabel(themeState.theme)}. Click to cycle.`}
	title={`Theme: ${getThemeLabel(themeState.theme)} (click to change)`}
>
	<span class="theme-icon">
		{#if themeState.theme === 'light'}
			<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
				<circle cx="12" cy="12" r="5"/>
				<line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/>
				<line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
				<line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/>
				<line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
			</svg>
		{:else if themeState.theme === 'dark'}
			<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
				<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
			</svg>
		{:else}
			<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
				<rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>
			</svg>
		{/if}
	</span>
	<span class="theme-label">{getThemeLabel(themeState.theme)}</span>
</button>

<style>
	.theme-toggle {
		position: fixed;
		bottom: 2rem;
		right: 2rem;
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.75rem 1.25rem;
		background: var(--surface-primary);
		border: 2px solid var(--border-primary);
		border-radius: var(--radius-pill);
		cursor: pointer;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
		font-weight: 500;
		color: var(--text-primary);
		box-shadow: 0 4px 12px var(--shadow-sm);
		transition: all var(--transition-normal);
		z-index: 999;
	}

	.theme-toggle:hover {
		border-color: var(--border-hover);
	}

	.theme-icon {
		display: flex;
		align-items: center;
	}

	.theme-label {
		font-weight: 600;
		letter-spacing: 0.02em;
	}

	@media (max-width: 640px) {
		.theme-toggle {
			bottom: max(1rem, calc(env(safe-area-inset-bottom) + 0.5rem));
			right: max(1rem, env(safe-area-inset-right));
			padding: 0.6rem 1rem;
		}

		.theme-label {
			display: none;
		}
	}
</style>
