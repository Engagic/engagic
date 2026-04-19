/**
 * Turnstile bot verification manager.
 *
 * Loads the Turnstile script on demand, renders an invisible widget,
 * exchanges the challenge token for a signed session token via the API,
 * and exposes the session token for the API client to include in headers.
 *
 * Session tokens last 30 minutes. On expiry (detected via 403 from API),
 * the manager automatically re-verifies.
 *
 * Concurrency contract:
 *   - Each Turnstile callback token is single-use at siteverify. Handing the
 *     same token to two consumers would always fail with timeout-or-duplicate,
 *     so waiters form an FIFO queue and each arriving token is delivered to
 *     exactly one consumer (either a waiter or the parked slot, never both).
 *   - reverify() is serialized via an inflight promise so that concurrent 403
 *     responses share a single widget reset rather than racing on it.
 *   - Any token parked before reset() is treated as stale and discarded; only
 *     the post-reset callback delivers a fresh token.
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
let parkedToken: string | null = null;
let sessionToken: string | null = null;
let scriptLoaded = false;
let initialized = false;

// FIFO queue of token waiters. A value of '' is used to wake waiters on
// error-callback so exchangeForSession can fail fast rather than hang.
const tokenWaiters: Array<(token: string) => void> = [];

// Single inflight reverify promise; concurrent callers share it.
let reverifyInflight: Promise<boolean> | null = null;

// Resolves when initTurnstile has either set a session token or finished
// failing. The api-client awaits this before the first gated request so it
// doesn't race ahead of the initial siteverify round-trip.
let initReadyResolve: (() => void) | null = null;
const initReady: Promise<void> = new Promise((r) => {
	initReadyResolve = r;
});

function loadScript(): Promise<void> {
	if (scriptLoaded) return Promise.resolve();
	return new Promise((resolve, reject) => {
		const script = document.createElement('script');
		script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
		script.async = false;
		script.onload = () => {
			scriptLoaded = true;
			resolve();
		};
		script.onerror = () => reject(new Error('turnstile script load failed'));
		document.head.appendChild(script);
	});
}

function handOutToken(token: string): void {
	const next = tokenWaiters.shift();
	if (next) {
		next(token);
	} else {
		parkedToken = token;
	}
}

function failAllWaiters(): void {
	parkedToken = null;
	while (tokenWaiters.length) {
		const w = tokenWaiters.shift();
		w?.('');
	}
}

function renderWidget(): void {
	if (!window.turnstile || !SITE_KEY) return;

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
			handOutToken(token);
		},
		'error-callback': () => {
			failAllWaiters();
		},
		'expired-callback': () => {
			parkedToken = null;
		},
	});
}

function resetWidget(): void {
	if (!window.turnstile || !widgetId) return;
	// Tokens parked before a reset may already have been consumed by a prior
	// siteverify; discard them so the next waitForToken receives only the
	// fresh post-reset token.
	parkedToken = null;
	window.turnstile.reset(widgetId);
}

function waitForToken(): Promise<string> {
	if (parkedToken) {
		const t = parkedToken;
		parkedToken = null;
		return Promise.resolve(t);
	}
	return new Promise((resolve) => {
		tokenWaiters.push(resolve);
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

function applySession(session: string): void {
	sessionToken = session;
	setExtraHeaders({ ...getExtraHeaders(), 'X-Turnstile-Token': session });
}

/**
 * Initialize Turnstile: load script, render widget, get session token.
 * Call once on app startup. Safe to call multiple times (idempotent).
 */
export async function initTurnstile(): Promise<void> {
	if (initialized || !SITE_KEY) return;
	if (typeof window === 'undefined') return;
	initialized = true;

	try {
		await loadScript();
		renderWidget();

		const token = await waitForToken();
		if (!token) return;
		const session = await exchangeForSession(token);
		if (session) applySession(session);
	} catch {
		// Script load or render failure -- fall through. API calls will 403
		// and trigger reverify, which will retry initTurnstile.
		initialized = false;
	} finally {
		initReadyResolve?.();
		initReadyResolve = null;
	}
}

/**
 * Resolves when initTurnstile has settled (success or give-up). The api-client
 * awaits this before the first gated request so the initial /api/search
 * doesn't fire before a session token is attached.
 */
export function waitForInit(): Promise<void> {
	return initReady;
}

/**
 * Re-verify: reset widget, get new challenge token, exchange for session.
 * Called automatically when API returns 403 turnstile_required.
 * Serialized: concurrent callers share one inflight reset.
 */
export function reverify(): Promise<boolean> {
	if (reverifyInflight) return reverifyInflight;
	reverifyInflight = (async () => {
		try {
			if (!window.turnstile || !widgetId) {
				// Widget never came up; try a full re-init.
				initialized = false;
				await initTurnstile();
				return !!sessionToken;
			}
			resetWidget();
			const token = await waitForToken();
			if (!token) return false;
			const session = await exchangeForSession(token);
			if (!session) return false;
			applySession(session);
			return true;
		} finally {
			reverifyInflight = null;
		}
	})();
	return reverifyInflight;
}

/**
 * Returns true if we currently have a session token set.
 */
export function hasSession(): boolean {
	return !!sessionToken;
}
