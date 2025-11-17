import type { PageServerLoad } from './$types';
import { apiClient } from '$lib/api/api-client';
import { getAnalytics } from '$lib/api/index';

export const load: PageServerLoad = async ({ locals, setHeaders }) => {
	// Get client IP from request (set in hooks.server.ts)
	const clientIp = locals.clientIp;

	// Fetch data in parallel BEFORE page renders
	const [analyticsResult, tickerResult] = await Promise.allSettled([
		getAnalytics(clientIp),
		apiClient.getTicker(clientIp)
	]);

	// Cache this data for 5 minutes (analytics and ticker don't change frequently)
	setHeaders({
		'cache-control': 'public, max-age=300'
	});

	return {
		analytics: analyticsResult.status === 'fulfilled' ? analyticsResult.value : null,
		tickerItems: tickerResult.status === 'fulfilled' && tickerResult.value.success
			? tickerResult.value.items
			: []
	};
};
