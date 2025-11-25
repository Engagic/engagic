import { browser } from '$app/environment';

type Theme = 'light' | 'dark' | 'system';

function getSystemTheme(): 'light' | 'dark' {
	if (!browser) return 'light';
	return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function getStoredTheme(): Theme {
	if (!browser) return 'system';
	return (localStorage.getItem('theme') as Theme) || 'system';
}

function getEffectiveTheme(theme: Theme): 'light' | 'dark' {
	if (theme === 'system') {
		return getSystemTheme();
	}
	return theme;
}

class ThemeState {
	theme = $state<Theme>(getStoredTheme());
	effectiveTheme = $derived<'light' | 'dark'>(getEffectiveTheme(this.theme));

	constructor() {
		if (browser) {
			this.applyTheme();
			this.watchSystemTheme();
		}
	}

	setTheme(newTheme: Theme) {
		this.theme = newTheme;
		if (browser) {
			localStorage.setItem('theme', newTheme);
			this.applyTheme();
		}
	}

	private applyTheme() {
		const root = document.documentElement;
		const effective = this.effectiveTheme;

		root.classList.remove('light', 'dark');
		root.classList.add(effective);
		root.setAttribute('data-theme', effective);
	}

	private watchSystemTheme() {
		const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');

		// Modern API
		mediaQuery.addEventListener('change', () => {
			if (this.theme === 'system') {
				this.applyTheme();
			}
		});

		// Legacy fallback for older mobile browsers
		if (mediaQuery.addListener) {
			mediaQuery.addListener(() => {
				if (this.theme === 'system') {
					this.applyTheme();
				}
			});
		}

		// Also watch for page visibility changes (mobile switches apps)
		document.addEventListener('visibilitychange', () => {
			if (!document.hidden && this.theme === 'system') {
				this.applyTheme();
			}
		});
	}

	cycleTheme() {
		const cycle: Record<Theme, Theme> = {
			light: 'dark',
			dark: 'system',
			system: 'light'
		};
		this.setTheme(cycle[this.theme]);
	}
}

export const themeState = new ThemeState();
