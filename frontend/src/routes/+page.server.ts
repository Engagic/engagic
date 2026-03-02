import { getAnalytics, getGlobalHappening } from '$lib/api/index';
import { configureApiForRequest } from '$lib/api/server';
import type { AnalyticsData, GlobalHappeningResponse } from '$lib/api/types';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ setHeaders, locals }) => {
	// Cache this page for 5 minutes
	setHeaders({
		'cache-control': 'public, max-age=300'
	});

	configureApiForRequest(locals.clientIp, locals.ssrAuthSecret);

	let analytics: AnalyticsData | null = null;
	let happening: GlobalHappeningResponse | null = null;

	try {
		[analytics, happening] = await Promise.all([
			getAnalytics(),
			getGlobalHappening(5)
		]);
	} catch (error) {
		console.error('Failed to load homepage data:', error);
	}

	return { analytics, happening };
};
