import type { PageLoad } from './$types';
import { apiClient } from '$lib/api/api-client';
import { getAnalytics } from '$lib/api/index';

export const load: PageLoad = async ({ setHeaders }) => {
	// Fetch data in parallel BEFORE page renders
	const [analyticsResult, tickerResult] = await Promise.allSettled([
		getAnalytics(),
		apiClient.getTicker()
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
