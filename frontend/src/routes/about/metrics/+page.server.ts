import { getAnalytics } from '$lib/api/index';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals }) => {
	try {
		const analytics = await getAnalytics(locals.clientIp);
		return { analytics };
	} catch (error) {
		console.error('Failed to load analytics:', error);
		return { analytics: null };
	}
};
