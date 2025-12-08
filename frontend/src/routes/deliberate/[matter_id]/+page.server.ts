import type { PageServerLoad } from './$types';
import { apiClient } from '$lib/api/api-client';
import { error } from '@sveltejs/kit';
import {
	getDeliberationForMatter,
	getDeliberation,
	type Deliberation,
	type DeliberationComment,
	type DeliberationStats
} from '$lib/api/deliberation';

interface DeliberationData {
	deliberation: Deliberation | null;
	comments: DeliberationComment[];
	stats: DeliberationStats | null;
}

async function fetchDeliberationForMatter(matterId: string): Promise<DeliberationData> {
	try {
		const { deliberation } = await getDeliberationForMatter(matterId);
		if (!deliberation) {
			return { deliberation: null, comments: [], stats: null };
		}

		const data = await getDeliberation(deliberation.id);
		return {
			deliberation: data.deliberation,
			comments: data.comments || [],
			stats: data.stats || null
		};
	} catch {
		return { deliberation: null, comments: [], stats: null };
	}
}

export const load: PageServerLoad = async ({ params }) => {
	const matterId = params.matter_id;

	try {
		const [timeline, deliberationData] = await Promise.all([
			apiClient.getMatterTimeline(matterId),
			fetchDeliberationForMatter(matterId)
		]);

		if (!timeline || !timeline.matter) {
			throw error(404, 'Matter not found');
		}

		return {
			matterId,
			matter: timeline.matter,
			deliberation: deliberationData
		};
	} catch (err) {
		console.error('Failed to load deliberation page:', err);
		throw error(500, 'Failed to load matter data');
	}
};
