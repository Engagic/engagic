import type { PageLoad } from './$types';
import { parseCityUrl } from '$lib/utils/utils';
import { error, redirect } from '@sveltejs/kit';

export const load: PageLoad = async ({ params }) => {
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

	// Return minimal data - component will handle fetching with state cache
	return {
		cityUrl: city_url,
		cityName: parsed.cityName,
		state: parsed.state
	};
};

