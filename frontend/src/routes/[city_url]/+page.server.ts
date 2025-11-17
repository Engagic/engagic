import type { PageServerLoad } from './$types';
import { searchMeetings, type SearchResult } from '$lib/api/index';
import { parseCityUrl } from '$lib/utils/utils';
import { processMeetingDates } from '$lib/utils/meetings';
import { error, redirect } from '@sveltejs/kit';

export const load: PageServerLoad = async ({ params, setHeaders, locals }) => {
	const { city_url } = params;

	// Check if this is a static route
	if (city_url === 'about') {
		throw redirect(307, '/about');
	}

	// Parse city URL
	const parsed = parseCityUrl(city_url);
	if (!parsed) {
		throw error(404, 'Invalid city URL format');
	}

	// Fetch city data server-side (pass client IP for rate limiting)
	const searchQuery = `${parsed.cityName}, ${parsed.state}`;
	const result = await searchMeetings(searchQuery, locals.clientIp);

	if (!result.success) {
		throw error(404, result.message || 'City not found');
	}

	// Cache city meetings for 2 minutes (agendas don't change frequently)
	setHeaders({
		'cache-control': 'public, max-age=120'
	});

	return processMeetingsData(result);
};

function processMeetingsData(result: SearchResult) {
	if (!result.success || !('meetings' in result)) {
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
