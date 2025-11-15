import { error } from '@sveltejs/kit';
import type { PageLoad } from './$types';

const API_BASE = 'https://api.engagic.org';

export const load: PageLoad = async ({ fetch }) => {
	try {
		// Fetch all dashboard data in parallel
		const [overview, geographic, topicTrends, matterTrends, funding, processing] = await Promise.all([
			fetch(`${API_BASE}/api/dashboard/overview`).then(r => r.ok ? r.json() : null),
			fetch(`${API_BASE}/api/dashboard/geographic`).then(r => r.ok ? r.json() : null),
			fetch(`${API_BASE}/api/dashboard/topics/trends`).then(r => r.ok ? r.json() : null),
			fetch(`${API_BASE}/api/dashboard/matters/trending`).then(r => r.ok ? r.json() : null),
			fetch(`${API_BASE}/api/dashboard/funding`).then(r => r.ok ? r.json() : null),
			fetch(`${API_BASE}/api/dashboard/processing`).then(r => r.ok ? r.json() : null),
		]);

		return {
			overview,
			geographic,
			topicTrends,
			matterTrends,
			funding,
			processing,
		};
	} catch (e) {
		console.error('Dashboard load error:', e);
		throw error(500, 'Failed to load dashboard data');
	}
};
