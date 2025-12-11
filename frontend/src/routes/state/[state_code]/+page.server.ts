import type { PageServerLoad } from './$types';
import { configureApiForRequest, apiClient } from '$lib/api/server';
import { error } from '@sveltejs/kit';

export const load: PageServerLoad = async ({ params, locals, setHeaders }) => {
	configureApiForRequest(locals.clientIp, locals.ssrAuthSecret);
	const stateCode = params.state_code.toUpperCase();

	if (!/^[A-Z]{2}$/.test(stateCode)) {
		throw error(400, 'Invalid state code');
	}

	try {
		const metrics = await apiClient.getStateMatters(stateCode, undefined, 100);

		setHeaders({
			'cache-control': 'public, max-age=600'
		});

		return {
			stateCode,
			metrics
		};
	} catch (err) {
		console.error('Failed to load state metrics:', err);
		throw error(500, 'Failed to load state data');
	}
};
