import { createServerApiClient } from '$lib/api/server';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals }) => {
	const apiClient = createServerApiClient(locals.clientIp, locals.ssrAuthSecret);
	try {
		const [analytics, platformMetrics, cityCoverage] = await Promise.all([
			apiClient.getAnalytics(),
			apiClient.getPlatformMetrics(),
			apiClient.getCityCoverage()
		]);
		return { analytics, platformMetrics, cityCoverage };
	} catch (error) {
		console.error('Failed to load metrics:', error);
		return { analytics: null, platformMetrics: null, cityCoverage: null };
	}
};
