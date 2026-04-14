/**
 * POST /challenge
 *
 * Frontend challenge endpoint:
 *   1. Receives a Turnstile token from the browser
 *   2. Forwards it to the backend /api/turnstile/verify for siteverify
 *   3. On success, sets an HMAC-signed cookie that gates SSR content
 *      via hooks.server.ts
 *
 * Runs on the Cloudflare Pages worker. Requires env var:
 *   CHALLENGE_COOKIE_SECRET    (any random 32+ char string)
 *
 * Note: TURNSTILE_SECRET_KEY is NOT needed here -- siteverify happens
 * on the backend which already has it.
 */

import type { RequestHandler } from './$types';
import { COOKIE_NAME, COOKIE_TTL_SECONDS, signCookie } from '$lib/server/challenge-cookie';
import { config } from '$lib/api/config';

export const POST: RequestHandler = async ({ request, cookies, platform }) => {
	const cookieSecret = platform?.env?.CHALLENGE_COOKIE_SECRET;
	if (!cookieSecret) {
		return new Response(JSON.stringify({ error: 'not_configured' }), {
			status: 503,
			headers: { 'Content-Type': 'application/json' }
		});
	}

	let body: unknown;
	try {
		body = await request.json();
	} catch {
		return new Response(JSON.stringify({ error: 'invalid_body' }), {
			status: 400,
			headers: { 'Content-Type': 'application/json' }
		});
	}

	const token = typeof body === 'object' && body && 'token' in body ? (body as { token: unknown }).token : null;
	if (typeof token !== 'string' || !token || token.length > 2048) {
		return new Response(JSON.stringify({ error: 'invalid_token' }), {
			status: 400,
			headers: { 'Content-Type': 'application/json' }
		});
	}

	// Proxy to backend for siteverify. Backend /api/turnstile/verify is already
	// exempt from its own Turnstile middleware, so no auth needed here.
	let verifySuccess = false;
	try {
		const resp = await fetch(`${config.apiBaseUrl}/api/turnstile/verify`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ token })
		});
		const data = (await resp.json()) as { success?: boolean };
		verifySuccess = resp.ok && !!data.success;
	} catch {
		return new Response(JSON.stringify({ error: 'backend_unreachable' }), {
			status: 502,
			headers: { 'Content-Type': 'application/json' }
		});
	}

	if (!verifySuccess) {
		return new Response(JSON.stringify({ error: 'turnstile_failed' }), {
			status: 403,
			headers: { 'Content-Type': 'application/json' }
		});
	}

	const now = Math.floor(Date.now() / 1000);
	const value = await signCookie(cookieSecret, now);
	cookies.set(COOKIE_NAME, value, {
		path: '/',
		httpOnly: true,
		secure: true,
		sameSite: 'lax',
		maxAge: COOKIE_TTL_SECONDS
	});

	return new Response(JSON.stringify({ success: true }), {
		headers: { 'Content-Type': 'application/json' }
	});
};
