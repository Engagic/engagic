import type { Handle } from '@sveltejs/kit';

export const handle: Handle = async ({ event, resolve }) => {
	// Capture real client IP from Cloudflare for forwarding to API
	// On Cloudflare Pages, cf-connecting-ip contains the original user's IP
	event.locals.clientIp = event.request.headers.get('cf-connecting-ip');

	// SSR auth secret for authenticating API requests from this frontend
	// Set in Cloudflare Pages dashboard: Settings > Environment Variables > SSR_AUTH_SECRET
	event.locals.ssrAuthSecret = event.platform?.env?.SSR_AUTH_SECRET ?? null;

	return resolve(event, {
		preload: ({ type, path }) => {
			if (type === 'font') return path.includes('ibm-plex-mono');
			return type === 'js' || type === 'css';
		}
	});
};
