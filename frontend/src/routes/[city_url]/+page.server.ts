import type { PageServerLoad } from './$types';
import { searchMeetings, type SearchResult } from '$lib/api/index';
import { parseCityUrl } from '$lib/utils/utils';
import { processMeetingDates } from '$lib/utils/meetings';
import { error, redirect } from '@sveltejs/kit';

export const load: PageServerLoad = async ({ params, setHeaders }) => {
	const { city_url } = params;

	if (city_url === 'about') {
		throw redirect(307, '/about');
	}

	const parsed = parseCityUrl(city_url);
	if (!parsed) {
		throw error(404, 'Invalid city URL format');
	}

	const searchQuery = `${parsed.cityName}, ${parsed.state}`;
	const result = await searchMeetings(searchQuery);

	if (!result.success) {
		throw error(404, result.message || 'City not found');
	}

	setHeaders({
		'cache-control': 'public, max-age=120'
	});

	return processMeetingsData(result);
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
