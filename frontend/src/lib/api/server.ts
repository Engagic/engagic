/**
 * Server-side API utilities
 * Use this in +page.server.ts to forward the real client IP to the API
 */

import { setExtraHeaders, apiClient } from './api-client';

/**
 * Configure the API client with the real client IP for server-side requests.
 * Call this at the start of your load function.
 *
 * @param clientIp - The real client IP from event.locals.clientIp
 */
export function configureApiForRequest(clientIp: string | null) {
	if (clientIp) {
		setExtraHeaders({ 'X-Forwarded-Client-IP': clientIp });
	} else {
		setExtraHeaders({});
	}
}

// Re-export apiClient for convenience
export { apiClient };
