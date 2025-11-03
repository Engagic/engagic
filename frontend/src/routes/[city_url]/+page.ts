import type { PageLoad } from './$types';
import { searchMeetings, type SearchResult } from '$lib/api/index';
import { parseCityUrl } from '$lib/utils/utils';
import { processMeetingDates } from '$lib/utils/meetings';
import { error, redirect } from '@sveltejs/kit';
import type { Meeting } from '$lib/api/types';

export const load: PageLoad = async ({ params, url, setHeaders }) => {
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

	// Check if we came from homepage search with fresh data
	// This eliminates the double-fetch when user searches and navigates
	if (url.searchParams.get('from') === 'search') {
		// Only access window in browser context
		if (typeof window !== 'undefined') {
			const navigationState = window.history.state?.searchResults as SearchResult | undefined;
			if (navigationState?.success && navigationState.city_name && navigationState.meetings) {
				// Use fresh data from homepage, skip redundant API call
				return processMeetingsData(navigationState);
			}
		}
	}

	// Otherwise fetch fresh data (direct navigation or no cached data)
	const searchQuery = `${parsed.cityName}, ${parsed.state}`;
	const result = await searchMeetings(searchQuery);

	if (!result.success) {
		throw error(404, result.message || 'City not found');
	}

	// Cache city meetings for 2 minutes (agendas don't change frequently)
	setHeaders({
		'cache-control': 'public, max-age=120'
	});

	return processMeetingsData(result);
};

// Helper function to process meetings data (used for both fresh fetch and cached data)
function processMeetingsData(result: SearchResult) {
	if (!result.meetings) {
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
