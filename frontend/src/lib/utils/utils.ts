import type { Meeting, AgendaItem } from '../api/types';
import { generateAnchorId } from './anchor';

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
	// Extract the ID from the end of the slug
	// Format: YYYY-MM-DD-{meeting_id} or undated-{meeting_id}
	//
	// CRITICAL: Meeting IDs can contain dashes (Chicago UUIDs: 71CAEB7D-4BC6-F011-BBD2-001DD8020E93)
	// So we can't just take the last part after split('-')!
	//
	// Strategy: Remove the date prefix, return the rest
	const parts = slug.split('-');

	if (parts.length < 4) {
		// Format: undated-{id} (2 parts minimum)
		// Or malformed, return last part as fallback
		return parts.length >= 2 ? parts.slice(1).join('-') : null;
	}

	// Format: YYYY-MM-DD-{id} (4+ parts)
	// Date is first 3 parts (YYYY, MM, DD), rest is meeting ID
	return parts.slice(3).join('-');
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

export function buildItemShareLink(banana: string, meeting: Meeting, item: AgendaItem): string {
	const meetingSlug = generateMeetingSlug(meeting);
	const anchor = generateAnchorId(item);
	return `https://engagic.org/${banana}/${meetingSlug}?item=${anchor}`;
}

// Truncate text for OG meta description (strips markdown formatting)
export function truncateForMeta(text: string | undefined | null, maxLength: number = 200): string {
	if (!text) return '';
	const cleaned = text.replace(/[#*_`]/g, '').trim();
	if (cleaned.length <= maxLength) return cleaned;
	return cleaned.slice(0, maxLength - 3) + '...';
}