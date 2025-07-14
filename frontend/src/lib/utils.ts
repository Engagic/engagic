import type { Meeting } from './api';

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
	// Use meeting title or name
	const title = meeting.title || meeting.meeting_name || 'meeting';
	
	// Extract date from meeting date or start
	const dateStr = meeting.meeting_date || meeting.start || '';
	let dateSlug = '';
	
	if (dateStr) {
		// Handle various date formats
		let datePart = dateStr;
		
		// If date contains time separator, extract just the date part
		if (dateStr.includes(' - ')) {
			datePart = dateStr.split(' - ')[0].trim();
		}
		
		// Also handle "on YYYY-MM-DD" format from title
		const titleDateMatch = title.match(/on (\d{4}-\d{2}-\d{2})/);
		if (titleDateMatch) {
			datePart = titleDateMatch[1];
		}
		
		// Try to parse date and format as YYYY_MM_DD
		const date = new Date(datePart);
		if (!isNaN(date.getTime())) {
			const year = date.getFullYear();
			const month = String(date.getMonth() + 1).padStart(2, '0');
			const day = String(date.getDate()).padStart(2, '0');
			dateSlug = `${year}_${month}_${day}`;
		}
	}
	
	// Clean title: remove date suffix if present, lowercase, remove special chars
	let cleanTitle = title
		.replace(/ on \d{4}-\d{2}-\d{2}.*$/, '') // Remove "on YYYY-MM-DD" suffix
		.toLowerCase()
		.replace(/[^a-z0-9\s]/g, '')
		.replace(/\s+/g, '_')
		.substring(0, 50); // Limit length
	
	// Always include date in slug to avoid ambiguity
	if (!dateSlug) {
		// If we couldn't parse a date, use a fallback
		console.warn('Could not parse date for meeting:', meeting);
		dateSlug = 'undated';
	}
	
	// Combine title and date
	return `${cleanTitle}_${dateSlug}`;
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