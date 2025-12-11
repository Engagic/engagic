/**
 * Server-side API utilities
 * Use this in +page.server.ts to forward the real client IP to the API
 */

import { setExtraHeaders, apiClient, createServerApiClient, buildRequestHeaders } from './api-client';

/**
 * Configure the API client with the real client IP for server-side requests.
 * @deprecated Use createServerApiClient(clientIp) instead to avoid race conditions.
 * This function mutates global state which is unsafe in concurrent SSR environments.
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

/**
 * Get headers object for a request without mutating global state.
 * Use with manual fetch calls that need client IP forwarding.
 *
 * @param clientIp - The real client IP from event.locals.clientIp
 * @returns Headers object to spread into fetch options
 */
export function getRequestHeaders(clientIp: string | null): Record<string, string> {
	return buildRequestHeaders({ clientIp });
}

// Re-export for convenience
export { apiClient, createServerApiClient };
