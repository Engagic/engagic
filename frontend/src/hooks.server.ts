import type { Handle } from '@sveltejs/kit';

export const handle: Handle = async ({ event, resolve }) => {
	// Capture real client IP from Cloudflare for forwarding to API
	// On Cloudflare Pages, cf-connecting-ip contains the original user's IP
	event.locals.clientIp = event.request.headers.get('cf-connecting-ip');

	return resolve(event, {
		preload: ({ type, path }) => {
			if (type === 'font') return path.includes('ibm-plex-mono');
			return type === 'js' || type === 'css';
		}
	});
};
