import type { PageServerLoad } from './$types';
import { configureApiForRequest, apiClient } from '$lib/api/server';
import { error } from '@sveltejs/kit';

export const load: PageServerLoad = async ({ locals, setHeaders }) => {
	configureApiForRequest(locals.clientIp, locals.ssrAuthSecret);

	try {
		const data = await apiClient.getCivicInfrastructure();

		// Filter to cities with committees only
		const cities = data.cities.filter(c => c.committee_count > 0);

		setHeaders({
			'cache-control': 'public, max-age=600'
		});

		return {
			cities,
			totals: data.totals
		};
	} catch (err) {
		console.error('Failed to load civic infrastructure:', err);
		throw error(500, 'Failed to load committee data');
	}
};
