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
		// Fetch metrics, meetings, and happening items in parallel
		const [metrics, meetings, happening] = await Promise.all([
			apiClient.getStateMatters(stateCode, undefined, 100),
			apiClient.getStateMeetings(stateCode, 50).catch(err => {
				console.error('Failed to load state meetings:', err);
				return null;
			}),
			apiClient.getGlobalHappening(30).catch(err => {
				console.error('Failed to load happening items:', err);
				return null;
			})
		]);

		setHeaders({
			'cache-control': 'public, max-age=600'
		});

		return {
			stateCode,
			metrics,
			meetings,
			happening
		};
	} catch (err) {
		console.error('Failed to load state metrics:', err);
		throw error(500, 'Failed to load state data');
	}
};
