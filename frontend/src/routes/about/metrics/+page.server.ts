import { getAnalytics, getPlatformMetrics } from '$lib/api/index';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	try {
		const [analytics, platformMetrics] = await Promise.all([
			getAnalytics(),
			getPlatformMetrics()
		]);
		return { analytics, platformMetrics };
	} catch (error) {
		console.error('Failed to load metrics:', error);
		return { analytics: null, platformMetrics: null };
	}
};
