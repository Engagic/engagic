/**
 * Server-side API utilities
 * Use this in +page.server.ts to forward the real client IP to the API
 */

import { setExtraHeaders, apiClient, createServerApiClient, buildRequestHeaders } from './api-client';

/**
 * Configure the API client with the real client IP for server-side requests.
 * @deprecated Use createServerApiClient(clientIp, ssrAuthSecret) instead to avoid race conditions.
 * This function mutates global state which is unsafe in concurrent SSR environments.
 *
 * @param clientIp - The real client IP from event.locals.clientIp
 * @param ssrAuthSecret - The SSR auth secret from event.locals.ssrAuthSecret
 */
export function configureApiForRequest(clientIp: string | null, ssrAuthSecret?: string | null) {
	if (clientIp) {
		const headers: Record<string, string> = { 'X-Forwarded-Client-IP': clientIp };
		if (ssrAuthSecret) {
			headers['X-SSR-Auth'] = ssrAuthSecret;
		}
		setExtraHeaders(headers);
	} else {
		setExtraHeaders({});
	}
}

/**
 * Get headers object for a request without mutating global state.
 * Use with manual fetch calls that need client IP forwarding.
 *
 * @param clientIp - The real client IP from event.locals.clientIp
 * @param ssrAuthSecret - SSR auth secret to authenticate SSR requests
 * @returns Headers object to spread into fetch options
 */
export function getRequestHeaders(clientIp: string | null, ssrAuthSecret?: string | null): Record<string, string> {
	return buildRequestHeaders({ clientIp, ssrAuthSecret });
}

// Re-export for convenience
export { apiClient, createServerApiClient };
