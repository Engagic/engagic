import { getAnalytics, getPlatformMetrics, getCityCoverage } from '$lib/api/index';
import { configureApiForRequest } from '$lib/api/server';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals }) => {
	configureApiForRequest(locals.clientIp, locals.ssrAuthSecret);
	try {
		const [analytics, platformMetrics, cityCoverage] = await Promise.all([
			getAnalytics(),
			getPlatformMetrics(),
			getCityCoverage()
		]);
		return { analytics, platformMetrics, cityCoverage };
	} catch (error) {
		console.error('Failed to load metrics:', error);
		return { analytics: null, platformMetrics: null, cityCoverage: null };
	}
};
