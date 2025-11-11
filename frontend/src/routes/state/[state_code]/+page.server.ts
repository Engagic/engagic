import type { PageServerLoad } from './$types';
import { apiClient } from '$lib/api/api-client';
import { error } from '@sveltejs/kit';

export const load: PageServerLoad = async ({ params }) => {
	const stateCode = params.state_code.toUpperCase();

	// Validate state code format
	if (!/^[A-Z]{2}$/.test(stateCode)) {
		throw error(400, 'Invalid state code');
	}

	try {
		const metrics = await apiClient.getStateMatters(stateCode);

		return {
			stateCode,
			metrics
		};
	} catch (err) {
		console.error('Failed to load state metrics:', err);
		throw error(500, 'Failed to load state data');
	}
};
