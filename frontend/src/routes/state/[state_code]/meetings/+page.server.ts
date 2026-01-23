import type { PageServerLoad } from './$types';
import { createServerApiClient } from '$lib/api/server';
import { error } from '@sveltejs/kit';

export const load: PageServerLoad = async ({ params, locals, setHeaders }) => {
	const apiClient = createServerApiClient(locals.clientIp, locals.ssrAuthSecret);
	const stateCode = params.state_code.toUpperCase();

	if (!/^[A-Z]{2}$/.test(stateCode)) {
		throw error(400, 'Invalid state code');
	}

	try {
		// Fetch more meetings for the full list view
		const meetings = await apiClient.getStateMeetings(stateCode, 100);

		setHeaders({
			'cache-control': 'public, max-age=300'
		});

		return {
			stateCode,
			meetings
		};
	} catch (err) {
		console.error('Failed to load state meetings:', err);
		throw error(500, 'Failed to load state meetings');
	}
};
