/**
 * Turnstile bot verification manager.
 *
 * Loads the Turnstile script on demand, renders an invisible widget,
 * exchanges the challenge token for a signed session token via the API,
 * and exposes the session token for the API client to include in headers.
 *
 * Session tokens last 30 minutes. On expiry (detected via 403 from API),
 * the manager automatically re-verifies.
 */

import { setExtraHeaders, getExtraHeaders } from './api/api-client';

declare global {
	interface Window {
		turnstile?: {
			render: (container: string | HTMLElement, options: Record<string, unknown>) => string;
			reset: (widgetId: string) => void;
			remove: (widgetId: string) => void;
			ready: (callback: () => void) => void;
		};
	}
}

const SITE_KEY = '0x4AAAAAAC8k9WNTYMFPIDOj';

let widgetId: string | null = null;
let currentToken: string | null = null;
let sessionToken: string | null = null;
let resolveToken: ((token: string) => void) | null = null;
let scriptLoaded = false;
let initialized = false;

function loadScript(): Promise<void> {
	if (scriptLoaded) return Promise.resolve();
	return new Promise((resolve) => {
		const script = document.createElement('script');
		script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
		script.async = false;
		script.onload = () => {
			scriptLoaded = true;
			resolve();
		};
		document.head.appendChild(script);
	});
}

function renderWidget(): void {
	if (!window.turnstile || !SITE_KEY) return;

	// Create a hidden container for the invisible widget
	let container = document.getElementById('turnstile-container');
	if (!container) {
		container = document.createElement('div');
		container.id = 'turnstile-container';
		container.style.position = 'fixed';
		container.style.bottom = '0';
		container.style.right = '0';
		container.style.zIndex = '-1';
		document.body.appendChild(container);
	}

	if (widgetId) {
		window.turnstile.remove(widgetId);
	}

	widgetId = window.turnstile.render(container, {
		sitekey: SITE_KEY,
		size: 'compact',
		appearance: 'interaction-only',
		callback: (token: string) => {
			currentToken = token;
			if (resolveToken) {
				resolveToken(token);
				resolveToken = null;
			}
		},
		'error-callback': () => {
			currentToken = null;
		},
		'expired-callback': () => {
			currentToken = null;
		},
	});
}

function waitForToken(): Promise<string> {
	if (currentToken) {
		const token = currentToken;
		currentToken = null;
		return Promise.resolve(token);
	}
	return new Promise((resolve) => {
		resolveToken = resolve;
	});
}

async function exchangeForSession(turnstileToken: string): Promise<string | null> {
	// Single siteverify round-trip: /challenge sets the SSR gate cookie AND
	// returns the API session_token. Cloudflare's siteverify only accepts each
	// token once, so we cannot call both /challenge and /api/turnstile/verify
	// from the browser -- one would always fail with timeout-or-duplicate.
	try {
		const resp = await fetch('/challenge', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ token: turnstileToken }),
			credentials: 'same-origin',
		});
		if (!resp.ok) return null;
		const data = await resp.json();
		return data.session_token || null;
	} catch {
		return null;
	}
}

/**
 * Initialize Turnstile: load script, render widget, get session token.
 * Call once on app startup. Safe to call multiple times (idempotent).
 */
export async function initTurnstile(): Promise<void> {
	if (initialized || !SITE_KEY) return;
	if (typeof window === 'undefined') return;
	initialized = true;

	await loadScript();
	renderWidget();

	// Get initial session token
	const token = await waitForToken();
	const session = await exchangeForSession(token);
	if (session) {
		sessionToken = session;
		setExtraHeaders({ ...getExtraHeaders(), 'X-Turnstile-Token': session });
	}
}

/**
 * Re-verify: reset widget, get new challenge token, exchange for session.
 * Called automatically when API returns 403 turnstile_required.
 */
export async function reverify(): Promise<boolean> {
	if (!window.turnstile || !widgetId) {
		// Turnstile not loaded -- try full init
		initialized = false;
		await initTurnstile();
		return !!sessionToken;
	}

	window.turnstile.reset(widgetId);
	const token = await waitForToken();
	const session = await exchangeForSession(token);
	if (session) {
		sessionToken = session;
		setExtraHeaders({ ...getExtraHeaders(), 'X-Turnstile-Token': session });
		return true;
	}
	return false;
}

/**
 * Returns true if we currently have a session token set.
 */
export function hasSession(): boolean {
	return !!sessionToken;
}
