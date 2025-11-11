import type { Meeting } from '../api/types';

export function generateCityUrl(cityName: string, state: string): string {
	// Clean city name: remove spaces, periods, apostrophes, make lowercase
	const cleanCity = cityName
		.toLowerCase()
		.replace(/['\s\.]/g, '')
		.replace(/[^a-z0-9]/g, '');
	
	// Clean state: uppercase, remove spaces
	const cleanState = state.toUpperCase().replace(/\s/g, '');
	
	return `${cleanCity}${cleanState}`;
}

export function generateMeetingSlug(meeting: Meeting): string {
	// Extract date from meeting date
	const dateStr = meeting.date || '';
	let dateSlug = '';

	if (dateStr) {
		// Handle various date formats
		let datePart = dateStr;

		// If date contains time separator, extract just the date part
		if (dateStr.includes(' - ')) {
			datePart = dateStr.split(' - ')[0].trim();
		}

		// Try to parse date and format as YYYY-MM-DD
		const date = new Date(datePart);
		if (!isNaN(date.getTime())) {
			const year = date.getFullYear();
			const month = String(date.getMonth() + 1).padStart(2, '0');
			const day = String(date.getDate()).padStart(2, '0');
			dateSlug = `${year}-${month}-${day}`;
		}
	}

	if (!dateSlug) {
		// If we couldn't parse a date, use a fallback
		console.warn('Could not parse date for meeting:', meeting);
		dateSlug = 'undated';
	}

	// Simple slug: date-id (backend looks up by ID anyway)
	return `${dateSlug}-${meeting.id}`;
}

export function extractMeetingIdFromSlug(slug: string): string | null {
	// Extract the ID from the end of the slug (format: date-id)
	const parts = slug.split('-');
	const lastPart = parts[parts.length - 1];
	// IDs are now strings, just return the last part
	return lastPart || null;
}

export function parseCityUrl(cityUrl: string): { cityName: string; state: string } | null {
	// Extract state (last 2 uppercase letters)
	const stateMatch = cityUrl.match(/([A-Z]{2})$/);
	if (!stateMatch) return null;
	
	const state = stateMatch[1];
	const cityPart = cityUrl.substring(0, cityUrl.length - 2);
	
	// This is basic - we'll need to look up the actual city name from the API
	// For now, just return what we can parse
	return {
		cityName: cityPart,
		state: state
	};
}