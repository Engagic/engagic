import type { PageServerLoad } from './$types';
import { getAnalytics } from '$lib/api/index';

export const load: PageServerLoad = async ({ locals, setHeaders }) => {
	// Get client IP from request (set in hooks.server.ts)
	const clientIp = locals.clientIp;

	// Fetch analytics data BEFORE page renders
	const analytics = await getAnalytics(clientIp);

	// Cache this data for 5 minutes (analytics don't change frequently)
	setHeaders({
		'cache-control': 'public, max-age=300'
	});

	return {
		analytics
	};
};
