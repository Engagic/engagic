import type { Handle, HandleServerError } from '@sveltejs/kit';
import { COOKIE_NAME, gateVerdict, isLinkPreview, keepPrivate, previewDocument } from '$lib/server/gate';

export const handleError: HandleServerError = async ({ error, event }) => {
	console.error('SSR error:', event.url.pathname, error);
	return {
		message: 'Internal Error'
	};
};

/* A link-preview fetcher cannot solve the challenge: it gets the rendered
   page's preview tags and nothing else ($lib/server/gate previewDocument). */
async function linkPreview(page: Response): Promise<Response> {
	if (page.status >= 300 && page.status < 400) return page;
	return new Response(previewDocument(await page.text()), {
		status: page.status,
		headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' }
	});
}

export const handle: Handle = async ({ event, resolve }) => {
	event.locals.clientIp = event.request.headers.get('cf-connecting-ip');
	event.locals.ssrAuthSecret = event.platform?.env?.SSR_AUTH_SECRET ?? null;
	event.locals.userAgent = event.request.headers.get('user-agent');

	// Content gate (shared policy, $lib/server/gate): open paths and admitted
	// crawlers pass, everyone else needs the Turnstile cookie. Only guards GET
	// navigations -- POST/PUT etc. fall through to their handlers.
	if (event.request.method === 'GET') {
		const verdict = await gateVerdict('engagic', {
			pathname: event.url.pathname,
			ip: event.locals.clientIp,
			userAgent: event.request.headers.get('user-agent'),
			cookie: event.cookies.get(COOKIE_NAME),
			secret: event.platform?.env?.CHALLENGE_COOKIE_SECRET
		});
		if (verdict === 'challenge' && isLinkPreview(event.request.headers.get('user-agent'))) {
			return linkPreview(await resolve(event));
		}
		if (verdict === 'challenge') {
			const returnTo = event.url.pathname + event.url.search;
			return new Response(null, {
				status: 303,
				headers: { Location: `/challenge?return=${encodeURIComponent(returnTo)}` }
			});
		}
		// 'unconfigured' (no CHALLENGE_COOKIE_SECRET) fails open during rollout.
	}

	// A gated page must not land in the adapter's shared cache ($lib/server/gate).
	return keepPrivate('engagic', event.url.pathname, await resolve(event, {
		preload: ({ type, path }) => {
			if (type === 'font') return path.includes('ibm-plex-mono');
			return type === 'js' || type === 'css';
		}
	}));
};
