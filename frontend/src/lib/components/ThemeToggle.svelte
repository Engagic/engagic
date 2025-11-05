<script lang="ts">
	import { themeState } from '$lib/stores/theme.svelte';

	function getThemeIcon(theme: 'light' | 'dark' | 'system') {
		switch (theme) {
			case 'light':
				return '☀️';
			case 'dark':
				return '🌙';
			case 'system':
				return '💻';
		}
	}

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
	<span class="theme-icon">{getThemeIcon(themeState.theme)}</span>
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
		border-radius: 50px;
		cursor: pointer;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.9rem;
		font-weight: 500;
		color: var(--text-primary);
		box-shadow: 0 4px 12px var(--shadow-sm);
		transition: all 0.3s ease;
		z-index: 999;
	}

	.theme-toggle:hover {
		transform: translateY(-2px);
		box-shadow: 0 6px 20px var(--shadow-md);
		border-color: var(--border-hover);
	}

	.theme-icon {
		font-size: 1.2rem;
		display: flex;
		align-items: center;
	}

	.theme-label {
		font-weight: 600;
		letter-spacing: 0.02em;
	}

	@media (max-width: 640px) {
		.theme-toggle {
			bottom: 1rem;
			right: 1rem;
			padding: 0.6rem 1rem;
		}

		.theme-label {
			display: none;
		}

		.theme-icon {
			font-size: 1.4rem;
		}
	}
</style>
