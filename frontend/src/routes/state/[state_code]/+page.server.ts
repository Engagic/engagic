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
		// Fetch metrics and meetings in parallel
		const [metrics, meetings] = await Promise.all([
			apiClient.getStateMatters(stateCode, undefined, 100),
			apiClient.getStateMeetings(stateCode, 50).catch(err => {
				// Meetings are non-critical, log and continue
				console.error('Failed to load state meetings:', err);
				return null;
			})
		]);

		setHeaders({
			'cache-control': 'public, max-age=600'
		});

		return {
			stateCode,
			metrics,
			meetings
		};
	} catch (err) {
		console.error('Failed to load state metrics:', err);
		throw error(500, 'Failed to load state data');
	}
};
