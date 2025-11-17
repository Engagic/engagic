import type { Handle } from '@sveltejs/kit';

export const handle: Handle = async ({ event, resolve }) => {
	// Get real client IP from Cloudflare
	// On Cloudflare Workers/Pages, client IP is in platform.cf or via getClientAddress()
	const clientIp =
		(event.platform as any)?.cf?.connectingIp ||  // Cloudflare Workers platform
		event.request.headers.get('CF-Connecting-IP') ||
		event.request.headers.get('X-Real-IP') ||
		event.request.headers.get('X-Forwarded-For')?.split(',')[0].trim() ||
		event.getClientAddress();

	// Store in locals so it's available to all server load functions
	event.locals.clientIp = clientIp;

	return resolve(event);
};
