import type { PageServerLoad } from './$types';
import { apiClient } from '$lib/api/api-client';
import { error } from '@sveltejs/kit';

export const load: PageServerLoad = async ({ params }) => {
	const matterId = params.matter_id;

	try {
		const [timeline, votesResponse] = await Promise.all([
			apiClient.getMatterTimeline(matterId),
			apiClient.getMatterVotes(matterId).catch(() => null)
		]);

		if (!timeline || !timeline.matter) {
			throw error(404, 'Matter not found');
		}

		return {
			matterId,
			timeline,
			votes: votesResponse
		};
	} catch (err) {
		console.error('Failed to load matter timeline:', err);
		throw error(500, 'Failed to load matter data');
	}
};
