import { getMeeting, searchMeetings } from '$lib/api/index';
import { extractMeetingIdFromSlug, parseCityUrl, generateMeetingSlug } from '$lib/utils/utils';
import type { PageServerLoad } from './$types';
import type { Meeting } from '$lib/api/types';

export const load: PageServerLoad = async ({ params }) => {
	const { city_url, meeting_slug } = params;

	try {
		// Try optimized path: extract meeting ID from slug
		const meetingId = extractMeetingIdFromSlug(meeting_slug);

		if (meetingId) {
			const result = await getMeeting(meetingId);

			if (result.success && result.meeting) {
				return {
					selectedMeeting: result.meeting,
					searchResults: {
						success: true,
						city_name: result.city_name,
						state: result.state,
						banana: result.banana,
						meetings: [result.meeting],
						cached: true,
						query: city_url,
						type: 'city' as const
					}
				};
			}
		}

		// Fallback: fetch all city meetings
		const parsed = parseCityUrl(city_url);
		if (!parsed) {
			return {
				error: 'Invalid city URL format'
			};
		}

		const searchQuery = `${parsed.cityName}, ${parsed.state}`;
		const searchResults = await searchMeetings(searchQuery);

		if (searchResults.success && searchResults.meetings) {
			// Find meeting by slug
			const meeting = searchResults.meetings.find((m: Meeting) => {
				return generateMeetingSlug(m) === meeting_slug;
			});

			if (meeting) {
				return {
					selectedMeeting: meeting,
					searchResults
				};
			}

			return {
				error: 'Meeting not found'
			};
		}

		return {
			error: 'message' in searchResults ? searchResults.message : 'Failed to load city meetings'
		};
	} catch (err) {
		console.error('Failed to load meeting:', err);
		return {
			error: 'Unable to load meeting data. The agenda packet may not be posted yet, or there may be a temporary issue accessing city records. Please try again later.'
		};
	}
};
