import { getAnalytics } from '$lib/api/index';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	try {
		const analytics = await getAnalytics();
		return { analytics };
	} catch (error) {
		console.error('Failed to load analytics:', error);
		return { analytics: null };
	}
};
