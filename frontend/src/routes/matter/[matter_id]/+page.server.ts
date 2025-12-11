import type { PageServerLoad } from './$types';
import { configureApiForRequest, apiClient } from '$lib/api/server';
import { error } from '@sveltejs/kit';

export const load: PageServerLoad = async ({ params, locals, setHeaders }) => {
	configureApiForRequest(locals.clientIp, locals.ssrAuthSecret);
	const matterId = params.matter_id;

	try {
		const [timeline, votesResponse] = await Promise.all([
			apiClient.getMatterTimeline(matterId),
			apiClient.getMatterVotes(matterId).catch(() => null)
		]);

		if (!timeline || !timeline.matter) {
			throw error(404, 'Matter not found');
		}

		setHeaders({
			'cache-control': 'public, max-age=300'
		});

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
