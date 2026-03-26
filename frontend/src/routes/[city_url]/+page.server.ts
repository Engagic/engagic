import type { PageServerLoad } from './$types';
import type { SearchResult } from '$lib/api/index';
import { createServerApiClient } from '$lib/api/server';
import { parseCityUrl } from '$lib/utils/utils';
import { processMeetingDates } from '$lib/utils/meetings';
import { error, redirect } from '@sveltejs/kit';

export const load: PageServerLoad = async ({ params, setHeaders, locals }) => {
	const apiClient = createServerApiClient(locals.clientIp, locals.ssrAuthSecret);
	const { city_url } = params;

	if (city_url === 'about') {
		throw redirect(307, '/about');
	}

	const parsed = parseCityUrl(city_url);
	if (!parsed) {
		throw error(404, 'Invalid city URL format');
	}

	try {
		const searchQuery = `${parsed.cityName}, ${parsed.state}`;
		const result = await apiClient.searchMeetings(searchQuery);

		if (!result.success) {
			throw error(404, result.message || 'City not found');
		}

		setHeaders({
			'cache-control': 'public, max-age=120'
		});

		return processMeetingsData(result);
	} catch (err) {
		// Re-throw SvelteKit errors (redirects, error responses)
		if (err && typeof err === 'object' && 'status' in err) throw err;
		console.error('City page load error:', city_url, err);
		throw error(500, `Load failed: ${err instanceof Error ? err.message : String(err)}`);
	}
};

function processMeetingsData(result: SearchResult) {
	if (!result.success || !('meetings' in result) || !result.meetings) {
		return {
			searchResults: result,
			upcomingMeetings: [],
			pastMeetings: []
		};
	}

	const { upcoming, past } = processMeetingDates(result.meetings);

	return {
		searchResults: result,
		upcomingMeetings: upcoming,
		pastMeetings: past
	};
}
