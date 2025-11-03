import type { Meeting } from '$lib/api/types';

/**
 * Sorts meetings by date (soonest first).
 * Meetings without valid dates are placed at the end.
 */
export function sortMeetingsByDate(meetings: Meeting[]): Meeting[] {
	return meetings.sort((a, b) => {
		const dateA = a.date ? new Date(a.date) : new Date(9999, 11, 31);
		const dateB = b.date ? new Date(b.date) : new Date(9999, 11, 31);
		return dateA.getTime() - dateB.getTime();
	});
}

/**
 * Splits meetings into upcoming and past based on current date.
 * Meetings with invalid/missing dates are considered upcoming.
 */
export function splitMeetingsByDate(meetings: Meeting[]): {
	upcoming: Meeting[];
	past: Meeting[];
} {
	const now = new Date();
	const upcoming: Meeting[] = [];
	const past: Meeting[] = [];

	for (const meeting of meetings) {
		if (!meeting.date || meeting.date === 'null' || meeting.date === '') {
			// Meetings with no date go to upcoming
			upcoming.push(meeting);
			continue;
		}

		const meetingDate = new Date(meeting.date);

		// Skip invalid dates (NaN or epoch 0)
		if (isNaN(meetingDate.getTime()) || meetingDate.getTime() === 0) {
			upcoming.push(meeting);
			continue;
		}

		if (meetingDate >= now) {
			upcoming.push(meeting);
		} else {
			past.push(meeting);
		}
	}

	return { upcoming, past };
}

/**
 * Sorts and splits meetings in a single operation.
 * Convenience function that combines sortMeetingsByDate and splitMeetingsByDate.
 */
export function processMeetingDates(meetings: Meeting[]): {
	upcoming: Meeting[];
	past: Meeting[];
} {
	const sorted = sortMeetingsByDate(meetings);
	return splitMeetingsByDate(sorted);
}
